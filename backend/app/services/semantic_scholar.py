"""
Semantic Scholar API client.

Used to fetch citation counts and full citing-paper lists.
Docs: https://api.semanticscholar.org/api-docs/
"""

import asyncio
import io
import logging
import re
from typing import Any

import httpx
import pypdf

from app.services.cache import AsyncTTLCache

logger = logging.getLogger(__name__)

# Cache author search results for 5 minutes.
_author_search_cache: AsyncTTLCache = AsyncTTLCache(maxsize=500, ttl=300)

# Cache paper-with-authors lookups for 1 hour — DOIs are immutable.
_paper_authors_cache: AsyncTTLCache = AsyncTTLCache(maxsize=500, ttl=3600)

# Cache full works lists for 1 hour — offset-paginated and expensive.
_works_by_author_cache: AsyncTTLCache = AsyncTTLCache(maxsize=100, ttl=3600)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.app)"}
_CITATION_FIELDS = "paperId,title,year,authors,externalIds,publicationDate,url"
_PAGE_LIMIT = 1000
_MAX_RETRIES = 4


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    context: str = "",
) -> httpx.Response | None:
    """
    GET *url* with automatic retry on HTTP 429 (rate-limit) responses.

    Waits for the duration given in the ``Retry-After`` header, falling back
    to exponential back-off (2^attempt seconds) when the header is absent.
    Returns ``None`` on network errors or when all retries are exhausted.
    All other status codes are returned immediately so the caller can decide.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("S2 request error [%s]: %s", context, exc)
            return None
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(
            "S2 rate limited (429) [%s]; waiting %ds (attempt %d/%d)",
            context, wait, attempt + 1, _MAX_RETRIES,
        )
        await asyncio.sleep(wait)
    logger.error("S2 rate limit not resolved after %d attempts [%s]", _MAX_RETRIES, context)
    return None


def _clean_doi(doi: str) -> str:
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if doi.lower().startswith(prefix):
            return doi[len(prefix):]
    return doi


def _candidate_ids(doi: str) -> list[str]:
    """
    Build S2 paper ID candidates to try for a given DOI.

    For arXiv preprints (10.48550/arxiv.*) S2 indexes them under ARXIV:{id},
    so we try that first.

    For ACL Anthology DOIs (10.18653/v1/*) S2 indexes them under ACL:{id}
    (e.g. ACL:2024.acl-long.206).  Passing these as DOI:{full-doi} causes a
    400 from S2's batch endpoint because of the multiple path segments.

    All papers also get a DOI:{doi} attempt as a final fallback.
    """
    clean = _clean_doi(doi)
    ids: list[str] = []
    if clean.lower().startswith("10.48550/arxiv."):
        arxiv_id = clean[clean.lower().index("/arxiv.") + len("/arxiv."):]
        ids.append(f"ARXIV:{arxiv_id}")
    if clean.lower().startswith("10.18653/v1/"):
        acl_id = clean[len("10.18653/v1/"):]
        ids.append(f"ACL:{acl_id}")
        # ACL Anthology DOIs have multiple slashes that cause S2's batch
        # endpoint to return 400 when passed as DOI:{doi}.  The ACL: prefix
        # is the authoritative lookup for these papers, so skip the DOI form.
        return ids
    ids.append(f"DOI:{clean}")
    return ids


async def _resolve_s2_paper_id(doi: str) -> str | None:
    """
    Resolve a DOI to a native S2 paperId using the batch POST endpoint.

    Returns the paperId string (e.g. "649def34f8be52c8b66281af98ae884c09aef38b")
    or None if the paper is not in S2.
    """
    candidates = _candidate_ids(doi)
    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        try:
            response = await client.post(
                f"{_BASE_URL}/paper/batch",
                params={"fields": "paperId"},
                json={"ids": candidates},
            )
        except httpx.RequestError as exc:
            logger.error("S2 batch resolve request error for DOI %s: %s", doi, exc)
            return None

    if response.status_code != 200:
        logger.warning("S2 batch resolve returned %s for DOI %s", response.status_code, doi)
        return None

    for item in response.json():
        if item and item.get("paperId"):
            return item["paperId"]

    return None


async def get_citing_papers(doi: str, since_date: str | None = None) -> list[dict]:
    """
    Fetch all papers that cite *doi* from Semantic Scholar.

    Parameters
    ----------
    doi:
        The DOI of the paper to find citations for.
    since_date:
        Optional ISO date string (``YYYY-MM-DD``).  When provided, only citing
        papers with a ``publicationDate`` on or after this date are kept, and
        the expensive affiliation-enrichment steps are skipped for papers that
        don't pass the filter.

    Strategy:
      1. Resolve the DOI to a native S2 paperId via the batch endpoint.
         This handles arXiv DOIs, ACL Anthology DOIs, and any encoding
         quirks without hitting path-based URL issues.
      2. Page through /paper/{paperId}/citations using the numeric S2 ID.
      3. Filter by since_date (if provided) BEFORE affiliation enrichment.

    Returns a list of raw S2 citingPaper dicts.
    """
    s2_id = await _resolve_s2_paper_id(doi)
    if not s2_id:
        logger.info("S2: paper not found for DOI %s — skipping citation fetch", doi)
        return []

    logger.info("S2: resolved DOI %s → paperId=%s", doi, s2_id)

    results: list[dict] = []
    offset = 0

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        while True:
            params = {
                "fields": _CITATION_FIELDS,
                "offset": offset,
                "limit": _PAGE_LIMIT,
            }
            response = await _get_with_retry(
                client,
                f"{_BASE_URL}/paper/{s2_id}/citations",
                params,
                context=f"citations:{s2_id}",
            )
            if response is None:
                break
            if response.status_code != 200:
                logger.warning(
                    "S2 citations returned %s for paperId=%s (DOI %s)",
                    response.status_code, s2_id, doi,
                )
                break

            data = response.json()
            page = data.get("data", [])
            for item in page:
                citing = item.get("citingPaper")
                if citing:
                    results.append(citing)

            if len(page) < _PAGE_LIMIT:
                break
            offset += _PAGE_LIMIT

    logger.info("S2: found %d citing paper(s) for DOI %s (paperId=%s)", len(results), doi, s2_id)

    # Filter by publication date BEFORE enrichment to avoid downloading author
    # profiles and arXiv PDFs for papers we'll discard anyway.
    if since_date:
        before = len(results)
        _cutoff_year = int(since_date[:4])
        results = [
            p for p in results
            if (p.get("publicationDate") or "") >= since_date
            or (not p.get("publicationDate") and (p.get("year") or 0) >= _cutoff_year)
        ]
        logger.info(
            "S2: %d/%d citing paper(s) kept after date filter (since %s) for DOI %s",
            len(results), before, since_date, doi,
        )

    if results:
        await _enrich_author_affiliations(results)
        await _enrich_affiliations_from_pdfs(results)

    return results


_AFFIL_KEYWORDS = frozenset([
    # Academic
    "university", "université", "universität", "universidade", "universidad",
    "institute", "institution", "laboratory", "laboratories",
    "department", "dept", "school", "college", "faculty",
    "research", "center", "centre", "foundation",
    "technology", "technologies", "national", "academy",
    "sciences", "science", "campus", "hospital", "clinic",
    # Corporate tech labs commonly affiliated with NLP/ML papers
    "microsoft", "google", "meta", "facebook", "amazon", "apple", "ibm",
    "openai", "anthropic", "nvidia", "intel", "qualcomm", "adobe",
    "deepmind", "baidu", "tencent", "alibaba", "bytedance", "huawei",
    "salesforce", "ai2", "allen institute",
])

# Geographic noise — segments that are purely location strings and should be
# stripped when extracting the organisation name from comma-separated affiliation
# strings like "Microsoft, Beijing, China".
_GEO_TERMS: frozenset[str] = frozenset({
    # Countries
    "afghanistan", "albania", "algeria", "argentina", "australia", "austria",
    "bangladesh", "belgium", "brazil", "bulgaria", "canada", "chile", "china",
    "colombia", "croatia", "czech republic", "czechia", "denmark", "egypt",
    "ethiopia", "finland", "france", "germany", "ghana", "greece", "hungary",
    "india", "indonesia", "iran", "iraq", "ireland", "israel", "italy",
    "japan", "jordan", "kenya", "south korea", "korea", "latvia", "lebanon",
    "malaysia", "mexico", "morocco", "netherlands", "new zealand", "nigeria",
    "norway", "pakistan", "peru", "philippines", "poland", "portugal",
    "romania", "russia", "saudi arabia", "singapore", "slovakia",
    "south africa", "spain", "sri lanka", "sweden", "switzerland", "taiwan",
    "thailand", "turkey", "ukraine", "united arab emirates", "uae",
    "united kingdom", "uk", "united states", "usa", "u.s.a.", "us", "vietnam",
    # Common cities in academic affiliation strings
    "beijing", "shanghai", "shenzhen", "guangzhou", "wuhan", "chengdu",
    "nanjing", "hangzhou", "xi'an", "xian", "harbin",
    "tokyo", "osaka", "kyoto", "seoul", "busan",
    "london", "oxford", "edinburgh", "manchester",
    "paris", "berlin", "munich", "heidelberg", "zurich", "geneva",
    "amsterdam", "brussels", "stockholm", "copenhagen", "oslo", "helsinki",
    "toronto", "montreal", "vancouver",
    "new york", "san francisco", "los angeles", "chicago", "boston",
    "seattle", "austin", "atlanta", "palo alto", "menlo park",
    "cambridge",  # kept generic — filtered only when not part of a larger org string
    "sydney", "melbourne",
    "hong kong", "tel aviv", "dubai",
    # US state abbreviations (two-letter)
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "d.c.", "dc",
})

# Canonical name map: (lowercase pattern, canonical display name).
# More-specific entries MUST come before broader ones (e.g. "google deepmind"
# before "google") so that the first match wins.
_CANONICAL_MAP: list[tuple[str, str]] = [
    # Specific labs / joint institutes first
    ("mit-ibm watson ai lab", "MIT-IBM Watson AI Lab"),
    ("watson ai lab", "MIT-IBM Watson AI Lab"),
    ("allen institute for ai", "Allen Institute for AI"),
    ("allen institute for artificial intelligence", "Allen Institute for AI"),
    ("ai2", "AI2"),
    ("google deepmind", "Google DeepMind"),
    ("google brain", "Google Brain"),
    ("google research", "Google Research"),
    ("microsoft research", "Microsoft Research"),
    ("meta ai", "Meta AI"),
    ("fair,", "Meta AI"),   # Facebook AI Research legacy name
    ("facebook ai research", "Meta AI"),
    ("amazon web services", "AWS"),
    ("amazon alexa", "Amazon Alexa"),
    ("apple machine learning", "Apple"),
    ("nvidia research", "NVIDIA Research"),
    ("ibm research", "IBM Research"),
    ("salesforce research", "Salesforce Research"),
    # Universities — long form → abbreviation
    ("massachusetts institute of technology", "MIT"),
    ("carnegie mellon university", "CMU"),
    ("carnegie mellon", "CMU"),
    ("stanford university", "Stanford"),
    ("stanford", "Stanford"),
    ("university of california, berkeley", "UC Berkeley"),
    ("uc berkeley", "UC Berkeley"),
    ("university of california berkeley", "UC Berkeley"),
    ("university of california, los angeles", "UCLA"),
    ("uc los angeles", "UCLA"),
    ("university of california, san diego", "UCSD"),
    ("harvard university", "Harvard"),
    ("harvard", "Harvard"),
    ("yale university", "Yale"),
    ("princeton university", "Princeton"),
    ("columbia university", "Columbia"),
    ("new york university", "NYU"),
    ("cornell university", "Cornell"),
    ("cornell", "Cornell"),
    ("johns hopkins university", "Johns Hopkins"),
    ("johns hopkins", "Johns Hopkins"),
    ("jhu", "Johns Hopkins"),
    ("duke university", "Duke"),
    ("duke", "Duke"),
    ("dartmouth college", "Dartmouth"),
    ("dartmouth", "Dartmouth"),
    ("northwestern university", "Northwestern"),
    ("northwestern", "Northwestern"),
    ("notre dame", "Notre Dame"),
    ("university of notre dame", "Notre Dame"),
    ("vanderbilt university", "Vanderbilt"),
    ("vanderbilt", "Vanderbilt"),
    ("emory university", "Emory"),
    ("emory", "Emory"),
    ("tufts university", "Tufts"),
    ("tufts", "Tufts"),
    ("brown university", "Brown"),
    ("rice university", "Rice"),
    ("georgetown university", "Georgetown"),
    ("purdue university", "Purdue"),
    ("purdue", "Purdue"),
    ("pennsylvania state university", "Penn State"),
    ("penn state", "Penn State"),
    ("university of north carolina", "UNC"),
    ("university of maryland", "UMD"),
    ("umd", "UMD"),
    ("university of florida", "U. Florida"),
    ("university of virginia", "UVA"),
    ("virginia polytechnic", "Virginia Tech"),
    ("virginia tech", "Virginia Tech"),
    ("university of southern california", "USC"),
    ("boston university", "Boston University"),
    ("northeastern university", "Northeastern"),
    ("university of california, santa barbara", "UCSB"),
    ("uc santa barbara", "UCSB"),
    ("university of california, davis", "UC Davis"),
    ("uc davis", "UC Davis"),
    ("university of california, irvine", "UC Irvine"),
    ("uc irvine", "UC Irvine"),
    ("university of california, san francisco", "UCSF"),
    ("university of pennsylvania", "UPenn"),
    ("upenn", "UPenn"),
    ("university of michigan", "U. Michigan"),
    ("umich", "U. Michigan"),
    ("university of washington", "UW"),
    ("university of chicago", "U. Chicago"),
    ("uchicago", "U. Chicago"),
    ("university of texas", "UT Austin"),
    ("ut austin", "UT Austin"),
    ("georgia institute of technology", "Georgia Tech"),
    ("georgia tech", "Georgia Tech"),
    ("university of toronto", "U. Toronto"),
    ("university of montreal", "UdeM"),
    ("université de montréal", "UdeM"),
    ("mila", "Mila"),
    ("vector institute", "Vector Institute"),
    ("university of oxford", "Oxford"),
    ("oxford university", "Oxford"),
    ("university of cambridge", "Cambridge"),
    ("cambridge university", "Cambridge"),
    ("imperial college london", "Imperial College"),
    ("imperial college", "Imperial College"),
    ("university college london", "UCL"),
    ("university of edinburgh", "Edinburgh"),
    ("technical university of munich", "TU Munich"),
    ("technische universität münchen", "TU Munich"),
    ("tum", "TU Munich"),
    ("rwth aachen", "RWTH Aachen"),
    ("ku leuven", "KU Leuven"),
    ("university of british columbia", "UBC"),
    ("ubc", "UBC"),
    ("mcgill university", "McGill"),
    ("mcgill", "McGill"),
    ("eth zurich", "ETH Zürich"),
    ("eth zürich", "ETH Zürich"),
    ("epfl", "EPFL"),
    ("national university of singapore", "NUS"),
    ("singapore university of technology and design", "SUTD"),
    ("nanyang technological university", "NTU"),
    ("tsinghua university", "Tsinghua"),
    ("peking university", "PKU"),
    ("chinese academy of sciences", "CAS"),
    ("fudan university", "Fudan"),
    ("zhejiang university", "ZJU"),
    ("shanghai jiao tong university", "SJTU"),
    ("university of science and technology of china", "USTC"),
    ("beihang university", "Beihang"),
    ("renmin university", "RUC"),
    ("wuhan university", "WHU"),
    ("sun yat-sen university", "SYSU"),
    ("harbin institute of technology", "HIT"),
    ("korea advanced institute of science and technology", "KAIST"),
    ("kaist", "KAIST"),
    ("seoul national university", "SNU"),
    ("postech", "POSTECH"),
    ("hong kong university of science and technology", "HKUST"),
    ("hkust", "HKUST"),
    ("university of hong kong", "HKU"),
    ("chinese university of hong kong", "CUHK"),
    ("australian national university", "ANU"),
    ("university of melbourne", "U. Melbourne"),
    ("monash university", "Monash"),
    ("hebrew university", "Hebrew University"),
    ("technion", "Technion"),
    ("weizmann institute", "Weizmann Institute"),
    ("max planck institute", "Max Planck Institute"),
    ("inria", "INRIA"),
    ("cnrs", "CNRS"),
    ("sorbonne", "Sorbonne"),
    # More US universities
    ("california institute of technology", "Caltech"),
    ("caltech", "Caltech"),
    ("university of illinois", "UIUC"),
    ("illinois urbana-champaign", "UIUC"),
    ("uiuc", "UIUC"),
    ("university of wisconsin", "U. Wisconsin"),
    ("university of minnesota", "U. Minnesota"),
    ("university of arizona", "U. Arizona"),
    ("arizona state university", "Arizona State"),
    ("asu", "Arizona State"),
    ("ohio state university", "Ohio State"),
    ("michigan state university", "Michigan State"),
    ("pennsylvania state", "Penn State"),
    ("rutgers university", "Rutgers"),
    ("rutgers", "Rutgers"),
    ("indiana university", "Indiana University"),
    ("iowa state university", "Iowa State"),
    ("university of iowa", "U. Iowa"),
    ("university of pittsburgh", "U. Pittsburgh"),
    ("university of utah", "U. Utah"),
    ("university of colorado", "U. Colorado"),
    ("colorado state university", "Colorado State"),
    ("university of oregon", "U. Oregon"),
    ("oregon state university", "Oregon State"),
    ("university of tennessee", "U. Tennessee"),
    ("university of alabama", "U. Alabama"),
    ("university of georgia", "U. Georgia"),
    ("georgia state university", "Georgia State"),
    ("clemson university", "Clemson"),
    ("virginia tech", "Virginia Tech"),  # already above but keep fallback
    ("university of virginia", "UVA"),
    ("george mason university", "George Mason"),
    ("george washington university", "GWU"),
    ("american university", "American University"),
    ("university of miami", "U. Miami"),
    ("florida state university", "Florida State"),
    ("university of central florida", "UCF"),
    ("ucf", "UCF"),
    ("university of south florida", "USF"),
    ("florida international university", "FIU"),
    ("texas a&m", "Texas A&M"),
    ("texas a&amp;m", "Texas A&M"),
    ("university of texas at austin", "UT Austin"),
    ("university of houston", "U. Houston"),
    ("university of new mexico", "U. New Mexico"),
    ("university of nebraska", "U. Nebraska"),
    ("university of kansas", "U. Kansas"),
    ("university of oklahoma", "U. Oklahoma"),
    ("washington university in st. louis", "WashU"),
    ("washington university in st louis", "WashU"),
    ("washu", "WashU"),
    ("university of rochester", "U. Rochester"),
    ("stony brook university", "Stony Brook"),
    ("suny stony brook", "Stony Brook"),
    ("university at buffalo", "SUNY Buffalo"),
    ("suny buffalo", "SUNY Buffalo"),
    ("university of connecticut", "UConn"),
    ("uconn", "UConn"),
    ("university of delaware", "U. Delaware"),
    ("university of massachusetts", "UMass"),
    ("umass", "UMass"),
    ("university of new hampshire", "UNH"),
    ("university of vermont", "UVM"),
    ("university of rhode island", "URI"),
    ("rensselaer polytechnic", "RPI"),
    ("rpi", "RPI"),
    ("worcester polytechnic", "WPI"),
    ("wpi", "WPI"),
    ("lehigh university", "Lehigh"),
    ("drexel university", "Drexel"),
    ("temple university", "Temple"),
    ("carnegie mellon", "CMU"),  # already above but short form
    ("illinois institute of technology", "IIT Illinois"),
    ("new jersey institute of technology", "NJIT"),
    ("njit", "NJIT"),
    ("rochester institute of technology", "RIT"),
    ("rit", "RIT"),
    ("stevens institute", "Stevens Institute"),
    ("university of kentucky", "U. Kentucky"),
    ("louisiana state university", "LSU"),
    ("lsu", "LSU"),
    ("tulane university", "Tulane"),
    ("case western reserve", "Case Western"),
    ("university of cincinnati", "U. Cincinnati"),
    ("university of missouri", "U. Missouri"),
    ("university of arkansas", "U. Arkansas"),
    ("university of mississippi", "U. Mississippi"),
    ("mississippi state university", "Mississippi State"),
    ("university of louisville", "U. Louisville"),
    ("university of nevada", "U. Nevada"),
    ("university of idaho", "U. Idaho"),
    ("boise state university", "Boise State"),
    ("montana state university", "Montana State"),
    ("university of wyoming", "U. Wyoming"),
    ("university of north dakota", "U. North Dakota"),
    ("university of south dakota", "U. South Dakota"),
    ("south dakota state university", "South Dakota State"),
    ("north dakota state university", "North Dakota State"),
    ("university of denver", "U. Denver"),
    ("colorado school of mines", "Colorado Mines"),
    ("wake forest university", "Wake Forest"),
    ("baylor university", "Baylor"),
    ("texas christian university", "TCU"),
    ("tcu", "TCU"),
    ("rice university", "Rice"),
    ("santa clara university", "Santa Clara"),
    ("university of san diego", "USD"),
    ("san diego state university", "SDSU"),
    ("sdsu", "SDSU"),
    ("cal poly", "Cal Poly"),
    ("university of hawaii", "U. Hawaii"),
    ("loyola university", "Loyola"),
    ("marquette university", "Marquette"),
    ("villanova university", "Villanova"),
    ("fordham university", "Fordham"),
    ("boston college", "Boston College"),
    ("tufts university", "Tufts"),
    ("brandeis university", "Brandeis"),
    ("university of notre dame", "Notre Dame"),
    ("fordham", "Fordham"),
    ("depaul university", "DePaul"),
    ("howard university", "Howard"),
    ("spelman college", "Spelman"),
    ("morehouse college", "Morehouse"),
    ("hbcu", "HBCU"),
    # US National Labs & Government Research
    ("argonne national laboratory", "Argonne National Lab"),
    ("argonne national lab", "Argonne National Lab"),
    ("argonne", "Argonne National Lab"),
    ("lawrence berkeley national laboratory", "Lawrence Berkeley Lab"),
    ("lawrence berkeley national lab", "Lawrence Berkeley Lab"),
    ("lbnl", "Lawrence Berkeley Lab"),
    ("berkeley lab", "Lawrence Berkeley Lab"),
    ("lawrence livermore national laboratory", "Lawrence Livermore Lab"),
    ("lawrence livermore national lab", "Lawrence Livermore Lab"),
    ("llnl", "Lawrence Livermore Lab"),
    ("los alamos national laboratory", "Los Alamos National Lab"),
    ("los alamos national lab", "Los Alamos National Lab"),
    ("lanl", "Los Alamos National Lab"),
    ("oak ridge national laboratory", "Oak Ridge National Lab"),
    ("oak ridge national lab", "Oak Ridge National Lab"),
    ("ornl", "Oak Ridge National Lab"),
    ("pacific northwest national laboratory", "PNNL"),
    ("pacific northwest national lab", "PNNL"),
    ("pnnl", "PNNL"),
    ("sandia national laboratories", "Sandia National Labs"),
    ("sandia national labs", "Sandia National Labs"),
    ("sandia", "Sandia National Labs"),
    ("brookhaven national laboratory", "Brookhaven National Lab"),
    ("brookhaven national lab", "Brookhaven National Lab"),
    ("fermi national accelerator", "Fermilab"),
    ("fermilab", "Fermilab"),
    ("national institute of standards and technology", "NIST"),
    ("nist", "NIST"),
    ("national institutes of health", "NIH"),
    ("national cancer institute", "NCI"),
    ("national science foundation", "NSF"),
    ("defense advanced research projects", "DARPA"),
    ("darpa", "DARPA"),
    ("national aeronautics and space administration", "NASA"),
    ("nasa", "NASA"),
    ("jet propulsion laboratory", "JPL"),
    ("jpl", "JPL"),
    ("army research laboratory", "Army Research Lab"),
    ("air force research laboratory", "Air Force Research Lab"),
    ("naval research laboratory", "Naval Research Lab"),
    ("sri international", "SRI International"),
    ("sri", "SRI International"),
    ("mitre corporation", "MITRE"),
    ("mitre", "MITRE"),
    ("rand corporation", "RAND"),
    ("rand", "RAND"),
    # Canada
    ("university of waterloo", "U. Waterloo"),
    ("uwaterloo", "U. Waterloo"),
    ("university of alberta", "U. Alberta"),
    ("simon fraser university", "SFU"),
    ("sfu", "SFU"),
    ("university of calgary", "U. Calgary"),
    ("university of ottawa", "U. Ottawa"),
    ("york university", "York University"),
    ("western university", "Western University"),
    ("university of western ontario", "Western University"),
    ("queen's university", "Queen's University"),
    ("dalhousie university", "Dalhousie"),
    ("university of victoria", "UVic"),
    ("université laval", "Laval"),
    ("concordia university", "Concordia"),
    ("université du québec", "UQAM"),
    ("uqam", "UQAM"),
    # UK universities
    ("university of manchester", "U. Manchester"),
    ("university of bristol", "U. Bristol"),
    ("king's college london", "King's College London"),
    ("kcl", "King's College London"),
    ("university of warwick", "U. Warwick"),
    ("university of leeds", "U. Leeds"),
    ("university of sheffield", "U. Sheffield"),
    ("university of nottingham", "U. Nottingham"),
    ("university of birmingham", "U. Birmingham"),
    ("university of southampton", "U. Southampton"),
    ("durham university", "Durham"),
    ("queen mary university of london", "QMUL"),
    ("qmul", "QMUL"),
    ("london school of economics", "LSE"),
    ("lse", "LSE"),
    ("university of bath", "U. Bath"),
    ("university of liverpool", "U. Liverpool"),
    ("cardiff university", "Cardiff"),
    ("university of glasgow", "U. Glasgow"),
    ("university of st andrews", "St Andrews"),
    ("university of exeter", "U. Exeter"),
    ("university of york", "U. York"),
    ("lancaster university", "Lancaster"),
    ("university of surrey", "U. Surrey"),
    ("university of reading", "U. Reading"),
    ("university of leicester", "U. Leicester"),
    ("university of east anglia", "UEA"),
    ("university of sussex", "U. Sussex"),
    ("swansea university", "Swansea"),
    ("university of aberdeen", "U. Aberdeen"),
    ("heriot-watt university", "Heriot-Watt"),
    ("university of strathclyde", "U. Strathclyde"),
    ("university of dundee", "U. Dundee"),
    # Netherlands
    ("university of amsterdam", "U. Amsterdam"),
    ("uva", "U. Amsterdam"),
    ("vrije universiteit amsterdam", "VU Amsterdam"),
    ("vu amsterdam", "VU Amsterdam"),
    ("delft university of technology", "TU Delft"),
    ("tu delft", "TU Delft"),
    ("eindhoven university of technology", "TU Eindhoven"),
    ("tu eindhoven", "TU Eindhoven"),
    ("utrecht university", "Utrecht"),
    ("leiden university", "Leiden"),
    ("university of groningen", "U. Groningen"),
    ("radboud university", "Radboud"),
    ("tilburg university", "Tilburg"),
    ("erasmus university", "Erasmus"),
    # Germany
    ("humboldt university", "Humboldt University"),
    ("humboldt-universität", "Humboldt University"),
    ("freie universität berlin", "FU Berlin"),
    ("fu berlin", "FU Berlin"),
    ("tu berlin", "TU Berlin"),
    ("technische universität berlin", "TU Berlin"),
    ("university of bonn", "U. Bonn"),
    ("universität bonn", "U. Bonn"),
    ("heidelberg university", "Heidelberg"),
    ("ruprecht-karls-universität", "Heidelberg"),
    ("university of freiburg", "U. Freiburg"),
    ("university of göttingen", "U. Göttingen"),
    ("university of hamburg", "U. Hamburg"),
    ("goethe university", "Goethe University"),
    ("university of frankfurt", "Goethe University"),
    ("university of stuttgart", "U. Stuttgart"),
    ("university of mannheim", "U. Mannheim"),
    ("saarland university", "Saarland"),
    ("universität des saarlandes", "Saarland"),
    ("tu darmstadt", "TU Darmstadt"),
    ("technische universität darmstadt", "TU Darmstadt"),
    ("tu dresden", "TU Dresden"),
    ("technische universität dresden", "TU Dresden"),
    ("karlsruhe institute of technology", "KIT"),
    ("kit", "KIT"),
    ("university of cologne", "U. Cologne"),
    ("university of düsseldorf", "U. Düsseldorf"),
    ("ruhr university", "Ruhr University"),
    ("ruhr-universität bochum", "Ruhr University"),
    ("university of münster", "U. Münster"),
    ("university of erlangen", "U. Erlangen"),
    ("leibniz university", "Leibniz University"),
    ("fraunhofer", "Fraunhofer"),
    ("helmholtz", "Helmholtz"),
    # Switzerland (non-ETH/EPFL)
    ("university of zurich", "U. Zürich"),
    ("uzh", "U. Zürich"),
    ("university of bern", "U. Bern"),
    ("university of basel", "U. Basel"),
    ("university of geneva", "U. Geneva"),
    ("university of lausanne", "UNIL"),
    ("unil", "UNIL"),
    # France
    ("école polytechnique", "École Polytechnique"),
    ("ecole polytechnique", "École Polytechnique"),
    ("école normale supérieure", "ENS Paris"),
    ("ecole normale superieure", "ENS Paris"),
    ("ens paris", "ENS Paris"),
    ("ens lyon", "ENS Lyon"),
    ("université paris-saclay", "Paris-Saclay"),
    ("paris-saclay", "Paris-Saclay"),
    ("university of paris", "U. Paris"),
    ("sorbonne université", "Sorbonne"),
    ("université de lyon", "U. Lyon"),
    ("université grenoble", "U. Grenoble"),
    ("université de bordeaux", "U. Bordeaux"),
    ("université de toulouse", "U. Toulouse"),
    ("université de strasbourg", "U. Strasbourg"),
    ("université de montpellier", "U. Montpellier"),
    ("université paris-dauphine", "Paris-Dauphine"),
    ("sciences po", "Sciences Po"),
    # Nordic countries
    ("university of copenhagen", "U. Copenhagen"),
    ("technical university of denmark", "DTU"),
    ("dtu", "DTU"),
    ("aarhus university", "Aarhus"),
    ("lund university", "Lund"),
    ("uppsala university", "Uppsala"),
    ("stockholm university", "Stockholm"),
    ("kth royal institute of technology", "KTH"),
    ("kth", "KTH"),
    ("chalmers university", "Chalmers"),
    ("university of oslo", "U. Oslo"),
    ("norwegian university of science and technology", "NTNU"),
    ("ntnu", "NTNU"),
    ("aalto university", "Aalto"),
    ("university of helsinki", "U. Helsinki"),
    ("university of turku", "U. Turku"),
    # Belgium
    ("ghent university", "Ghent"),
    ("university of leuven", "KU Leuven"),
    ("vrije universiteit brussel", "VUB"),
    ("université libre de bruxelles", "ULB"),
    ("ulb", "ULB"),
    ("university of antwerp", "U. Antwerp"),
    # Austria
    ("university of vienna", "U. Vienna"),
    ("tu wien", "TU Wien"),
    ("vienna university of technology", "TU Wien"),
    ("austrian institute of technology", "AIT"),
    # Italy
    ("politecnico di milano", "Politecnico di Milano"),
    ("university of bologna", "U. Bologna"),
    ("sapienza university", "Sapienza"),
    ("università la sapienza", "Sapienza"),
    ("university of padua", "U. Padua"),
    ("university of florence", "U. Florence"),
    ("politecnico di torino", "Politecnico di Torino"),
    ("university of trento", "U. Trento"),
    ("university of milan", "U. Milan"),
    ("university of genoa", "U. Genoa"),
    ("university of pisa", "U. Pisa"),
    ("university of rome", "U. Rome"),
    ("scuola normale superiore", "SNS Pisa"),
    # Spain
    ("university of barcelona", "U. Barcelona"),
    ("universitat politècnica de catalunya", "UPC"),
    ("upc barcelona", "UPC"),
    ("universidad politécnica de madrid", "UPM"),
    ("complutense university", "UCM"),
    ("universidad autónoma de madrid", "UAM"),
    ("university of valencia", "U. Valencia"),
    ("university of seville", "U. Seville"),
    ("university of granada", "U. Granada"),
    ("universidad de zaragoza", "U. Zaragoza"),
    # Portugal
    ("university of lisbon", "U. Lisbon"),
    ("instituto superior técnico", "IST Lisbon"),
    ("universidade nova de lisboa", "NOVA Lisbon"),
    # Poland
    ("warsaw university of technology", "Warsaw Tech"),
    ("university of warsaw", "U. Warsaw"),
    ("agh university", "AGH University"),
    ("jagiellonian university", "Jagiellonian"),
    # Czech Republic
    ("charles university", "Charles University"),
    ("czech technical university", "CTU Prague"),
    # Russia
    ("moscow state university", "MSU Moscow"),
    ("lomonosov moscow state", "MSU Moscow"),
    ("skoltech", "Skoltech"),
    ("skolkovo institute", "Skoltech"),
    ("higher school of economics", "HSE Moscow"),
    ("yandex", "Yandex"),
    # Japan
    ("university of tokyo", "U. Tokyo"),
    ("tokyo institute of technology", "Tokyo Tech"),
    ("titech", "Tokyo Tech"),
    ("osaka university", "Osaka"),
    ("kyoto university", "Kyoto"),
    ("tohoku university", "Tohoku"),
    ("nagoya university", "Nagoya"),
    ("kyushu university", "Kyushu"),
    ("hokkaido university", "Hokkaido"),
    ("waseda university", "Waseda"),
    ("keio university", "Keio"),
    ("university of tsukuba", "Tsukuba"),
    ("nara institute of science and technology", "NAIST"),
    ("naist", "NAIST"),
    ("japan advanced institute of science and technology", "JAIST"),
    ("jaist", "JAIST"),
    ("riken", "RIKEN"),
    ("national institute of informatics", "NII Japan"),
    ("nii", "NII Japan"),
    ("aist", "AIST Japan"),
    ("national institute of advanced industrial science", "AIST Japan"),
    ("tokyo university of science", "TUS"),
    ("meiji university", "Meiji"),
    ("hitotsubashi university", "Hitotsubashi"),
    # South Korea
    ("korea university", "Korea University"),
    ("yonsei university", "Yonsei"),
    ("sungkyunkwan university", "SKKU"),
    ("skku", "SKKU"),
    ("hanyang university", "Hanyang"),
    ("ulsan national institute", "UNIST"),
    ("unist", "UNIST"),
    ("dgist", "DGIST"),
    ("etri", "ETRI"),
    ("electronics and telecommunications research institute", "ETRI"),
    ("lg ai research", "LG AI Research"),
    ("kakao", "Kakao"),
    ("naver", "Naver"),
    # China (additional)
    ("university of science and technology of china", "USTC"),  # already above but reorder safe
    ("nanjing university", "NJU"),
    ("nju", "NJU"),
    ("xi'an jiaotong university", "XJTU"),
    ("xian jiaotong university", "XJTU"),
    ("xjtu", "XJTU"),
    ("southeast university", "SEU"),
    ("sun yat-sen university", "SYSU"),  # already above
    ("wuhan university", "WHU"),  # already above
    ("tianjin university", "TJU"),
    ("northwestern polytechnical university", "NPU"),
    ("national university of defense technology", "NUDT"),
    ("nudt", "NUDT"),
    ("university of electronic science and technology", "UESTC"),
    ("uestc", "UESTC"),
    ("beijing university of posts and telecommunications", "BUPT"),
    ("bupt", "BUPT"),
    ("tongji university", "Tongji"),
    ("beijing institute of technology", "BIT"),
    ("central south university", "CSU"),
    ("xiamen university", "Xiamen"),
    ("jilin university", "Jilin"),
    ("dalian university of technology", "DUT"),
    ("huazhong university of science and technology", "HUST"),
    ("hust", "HUST"),
    ("shandong university", "SDU"),
    ("lanzhou university", "Lanzhou"),
    ("ocean university of china", "OUC"),
    ("didi", "Didi"),
    ("jd.com", "JD.com"),
    ("netease", "NetEase"),
    ("meituan", "Meituan"),
    ("sensetime", "SenseTime"),
    ("megvii", "Megvii"),
    ("iflytek", "iFLYTEK"),
    ("baidu research", "Baidu Research"),
    ("alibaba damo", "Alibaba DAMO"),
    # Taiwan
    ("national taiwan university", "NTU Taiwan"),
    ("national tsing hua university", "NTHU"),
    ("nthu", "NTHU"),
    ("national cheng kung university", "NCKU"),
    ("ncku", "NCKU"),
    ("academia sinica", "Academia Sinica"),
    ("national yang ming chiao tung university", "NYCU"),
    ("nycu", "NYCU"),
    # Southeast Asia
    ("singapore management university", "SMU Singapore"),
    ("nanyang technological university", "NTU Singapore"),  # already as NTU
    ("national university of singapore", "NUS"),  # already above
    ("sutd", "SUTD"),
    ("university of malaya", "U. Malaya"),
    ("universiti malaya", "U. Malaya"),
    ("universiti teknologi malaysia", "UTM"),
    ("chulalongkorn university", "Chulalongkorn"),
    ("king mongkut", "KMUTT"),
    # India
    ("indian institute of technology bombay", "IIT Bombay"),
    ("iit bombay", "IIT Bombay"),
    ("indian institute of technology delhi", "IIT Delhi"),
    ("iit delhi", "IIT Delhi"),
    ("indian institute of technology madras", "IIT Madras"),
    ("iit madras", "IIT Madras"),
    ("indian institute of technology kharagpur", "IIT Kharagpur"),
    ("iit kharagpur", "IIT Kharagpur"),
    ("indian institute of technology kanpur", "IIT Kanpur"),
    ("iit kanpur", "IIT Kanpur"),
    ("indian institute of technology roorkee", "IIT Roorkee"),
    ("iit roorkee", "IIT Roorkee"),
    ("indian institute of technology hyderabad", "IIT Hyderabad"),
    ("iit hyderabad", "IIT Hyderabad"),
    ("indian institute of technology bangalore", "IISc"),  # sometimes confused
    ("indian institute of science", "IISc"),
    ("iisc", "IISc"),
    ("tata institute of fundamental research", "TIFR"),
    ("tifr", "TIFR"),
    ("institute of mathematical sciences", "IMSc"),
    ("bits pilani", "BITS Pilani"),
    ("vit university", "VIT"),
    ("jadavpur university", "Jadavpur"),
    ("anna university", "Anna University"),
    ("jawaharlal nehru university", "JNU"),
    ("jnu", "JNU"),
    ("university of delhi", "U. Delhi"),
    ("iiser", "IISER"),
    ("indian institute of science education and research", "IISER"),
    ("international institute of information technology", "IIIT Hyderabad"),
    ("iiit hyderabad", "IIIT Hyderabad"),
    ("iiit", "IIIT"),
    # Australia & New Zealand
    ("university of sydney", "U. Sydney"),
    ("university of queensland", "UQ"),
    ("uq", "UQ"),
    ("university of new south wales", "UNSW"),
    ("unsw", "UNSW"),
    ("university of adelaide", "U. Adelaide"),
    ("university of western australia", "UWA"),
    ("uwa", "UWA"),
    ("deakin university", "Deakin"),
    ("rmit university", "RMIT"),
    ("rmit", "RMIT"),
    ("macquarie university", "Macquarie"),
    ("curtin university", "Curtin"),
    ("university of auckland", "U. Auckland"),
    ("victoria university of wellington", "Victoria Wellington"),
    ("csiro", "CSIRO"),
    # Middle East
    ("king abdullah university of science and technology", "KAUST"),
    ("kaust", "KAUST"),
    ("king fahd university", "KFUPM"),
    ("american university of beirut", "AUB"),
    ("aub", "AUB"),
    ("bilkent university", "Bilkent"),
    ("middle east technical university", "METU"),
    ("metu", "METU"),
    ("koç university", "Koç University"),
    ("koc university", "Koç University"),
    ("sabancı university", "Sabancı"),
    ("sabanci university", "Sabancı"),
    ("university of tehran", "U. Tehran"),
    ("sharif university", "Sharif"),
    ("qatar computing research institute", "QCRI"),
    ("qcri", "QCRI"),
    ("qatar university", "Qatar University"),
    # Africa
    ("university of cape town", "UCT"),
    ("uct", "UCT"),
    ("university of johannesburg", "UJ"),
    ("university of pretoria", "UP"),
    ("university of the witwatersrand", "Wits"),
    ("wits university", "Wits"),
    ("cairo university", "Cairo University"),
    ("american university in cairo", "AUC"),
    ("stellenbosch university", "Stellenbosch"),
    # Latin America
    ("university of são paulo", "USP"),
    ("universidade de são paulo", "USP"),
    ("usp", "USP"),
    ("university of campinas", "Unicamp"),
    ("unicamp", "Unicamp"),
    ("puc-rio", "PUC-Rio"),
    ("pontificia universidade católica", "PUC"),
    ("impa", "IMPA"),
    ("universidad nacional autónoma de méxico", "UNAM"),
    ("unam", "UNAM"),
    ("tecnológico de monterrey", "Tec de Monterrey"),
    ("universidad de chile", "U. Chile"),
    ("universidad de buenos aires", "UBA"),
    # International Research Institutes & CERN-like
    ("cern", "CERN"),
    ("european molecular biology laboratory", "EMBL"),
    ("embl", "EMBL"),
    ("broad institute", "Broad Institute"),
    ("flatiron institute", "Flatiron Institute"),
    ("simons foundation", "Simons Foundation"),
    ("janelia research campus", "Janelia"),
    ("hhmi", "HHMI"),
    ("howard hughes medical institute", "HHMI"),
    ("santa fe institute", "Santa Fe Institute"),
    ("perimeter institute", "Perimeter Institute"),
    ("institute for advanced study", "IAS Princeton"),
    ("toyota research institute", "Toyota Research"),
    ("honda research institute", "Honda Research"),
    ("bosch research", "Bosch Research"),
    ("robert bosch", "Bosch"),
    ("siemens research", "Siemens Research"),
    ("ntt research", "NTT Research"),
    ("nokia bell labs", "Nokia Bell Labs"),
    ("bell labs", "Bell Labs"),
    ("xerox research", "Xerox PARC"),
    ("parc", "Xerox PARC"),
    ("ericsson research", "Ericsson Research"),
    ("hugging face", "Hugging Face"),
    ("huggingface", "Hugging Face"),
    ("eleutherai", "EleutherAI"),
    ("stability ai", "Stability AI"),
    ("mistral", "Mistral AI"),
    ("cohere", "Cohere"),
    ("together ai", "Together AI"),
    ("together.ai", "Together AI"),
    ("scale ai", "Scale AI"),
    ("waymo", "Waymo"),
    ("tesla ai", "Tesla AI"),
    ("tesla", "Tesla"),
    ("two sigma", "Two Sigma"),
    ("d.e. shaw", "D.E. Shaw"),
    ("renaissance technologies", "Renaissance Technologies"),
    ("jane street", "Jane Street"),
    ("openstreetmap", "OpenStreetMap"),
    ("wikimedia", "Wikimedia"),
    # Companies (broad match — place after specific lab variants)
    ("microsoft", "Microsoft"),
    ("google", "Google"),
    ("meta", "Meta"),
    ("facebook", "Meta"),
    ("amazon", "Amazon"),
    ("apple", "Apple"),
    ("ibm", "IBM"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("nvidia", "NVIDIA"),
    ("intel", "Intel"),
    ("qualcomm", "Qualcomm"),
    ("adobe", "Adobe"),
    ("deepmind", "DeepMind"),
    ("baidu", "Baidu"),
    ("tencent", "Tencent"),
    ("alibaba", "Alibaba"),
    ("bytedance", "ByteDance"),
    ("huawei", "Huawei"),
    ("salesforce", "Salesforce"),
    ("samsung", "Samsung"),
    ("lg", "LG"),
    ("nec", "NEC"),
    ("fujitsu", "Fujitsu"),
    ("hitachi", "Hitachi"),
    ("sony", "Sony"),
    ("rakuten", "Rakuten"),
    ("twitter", "X (Twitter)"),
    ("linkedin", "LinkedIn"),
    ("uber", "Uber"),
    ("airbnb", "Airbnb"),
    ("netflix", "Netflix"),
    ("snap", "Snap"),
    ("pinterest", "Pinterest"),
]


def _normalize_affiliation(raw: str) -> str | None:
    """
    Convert a raw affiliation string to a short, display-friendly canonical name.

    Strategy:
      1. Try a direct canonical match on the full string.
      2. Split by comma; drop pure geographic segments.
      3. Try a canonical match on each remaining segment (most-institution-like
         segment wins — prefer the last non-department segment).
      4. Fall back to the last non-geographic segment as-is.

    Returns None when the string is unusable (empty after cleaning).
    """
    raw = raw.strip()
    if not raw:
        return None

    # --- Step 1: canonical lookup on the full string ---
    hit = _match_canonical(raw)
    if hit:
        return hit

    # --- Step 2: split by comma and remove geographic noise ---
    segments = [s.strip() for s in raw.split(",")]
    org_segments: list[str] = []
    for seg in segments:
        if not seg:
            continue
        seg_low = seg.lower().strip(".")
        # Keep if it contains an org keyword; drop if it's a pure geo term.
        has_kw = any(kw in seg_low for kw in _AFFIL_KEYWORDS)
        is_geo = seg_low in _GEO_TERMS
        if has_kw or not is_geo:
            org_segments.append(seg)

    if not org_segments:
        return None

    # --- Step 3: canonical match on individual segments ---
    # Iterate from last to first: the institution usually trails the department.
    for seg in reversed(org_segments):
        hit = _match_canonical(seg)
        if hit:
            return hit

    # No canonical match found — return None so callers default to "Independent"
    # rather than surfacing a raw, unverified text fragment as an affiliation pill.
    return None


def _match_canonical(text: str) -> str | None:
    """
    Return the canonical display name if *text* contains a known pattern,
    or None if no pattern matches.

    All patterns use boundary-aware matching so that, e.g., "intel" does not
    fire on "artificial intelligence" and "meta" does not fire on "metadata".
    Boundaries are defined as transitions from/to a non-alphanumeric character
    (space, comma, hyphen, start/end of string).
    """
    low = text.lower().strip()
    for pattern, canonical in _CANONICAL_MAP:
        if re.search(r"(?<![a-z\d])" + re.escape(pattern) + r"(?![a-z\d])", low):
            return canonical
    return None

_EMAIL_RE = re.compile(r"[\w.+{},\s]+@[\w.]+")
_EMAIL_DOMAIN_RE = re.compile(r"@([\w][\w.-]*\.[a-z]{2,})", re.IGNORECASE)
_MARKER_LEADING = re.compile(r"^[\d\s*†‡§¶#◦○●,;:\-]+")
_MARKER_TRAILING = re.compile(r"[,;:\-\s]+$")


def _infer_from_email_domains(text: str) -> list[str]:
    """Return canonical institution names inferred from email domains in *text*.

    Only processes academic TLDs (.edu and .ac.xx).  The domain segment that
    identifies the institution (e.g. "dartmouth" in dartmouth.edu, or "ox" in
    ox.ac.uk) is passed through ``_match_canonical`` so results are already in
    display-friendly form.
    """
    results: list[str] = []
    seen: set[str] = set()
    for m in _EMAIL_DOMAIN_RE.finditer(text):
        domain = m.group(1).lower()
        parts = [p for p in domain.split(".") if p]
        if len(parts) < 2:
            continue
        tld = parts[-1]
        second_tld = parts[-2] if len(parts) >= 2 else ""
        if tld == "edu":
            # dartmouth.edu → "dartmouth";  cs.dartmouth.edu → "dartmouth"
            candidate = parts[-2]
        elif second_tld == "ac":
            # ox.ac.uk → "ox";  dcs.ox.ac.uk → "ox"
            candidate = parts[-3] if len(parts) >= 3 else ""
        else:
            continue
        if not candidate:
            continue
        hit = _match_canonical(candidate)
        if hit and hit not in seen:
            results.append(hit)
            seen.add(hit)
    return results


def _parse_affiliations_from_first_page(text: str) -> list[str]:
    """
    Extract institution names from the first-page text of an academic paper.

    Strategy:
      1. Truncate to everything before the "Abstract" heading.
      2. Infer institutions from email domains in the header (e.g. @dartmouth.edu).
      3. Pre-split combined lines where mid-line superscript numbers mark a
         new affiliation (e.g. "Watson AI Lab 3IBM Research").
      4. Strip leading markers and email addresses from each candidate line.
      5. Keep lines that contain an academic or corporate keyword, start with
         an uppercase letter or digit, and are short enough to be a name (not
         a prose sentence).
    """
    abstract_match = re.search(r"\bAbstract\b", text, re.IGNORECASE)
    header = text[: abstract_match.start()] if abstract_match else text[:3000]

    affiliations: list[str] = []
    seen: set[str] = set()

    # --- Step 1: email-domain inference (runs on raw header before any stripping) ---
    for inst in _infer_from_email_domains(header):
        if inst.lower() not in seen:
            affiliations.append(inst)
            seen.add(inst.lower())

    # Split mid-line affiliation markers so "Lab 3IBM" → "Lab\nIBM"
    header = re.sub(r"(\w)\s+(\d+)(?=[A-Z])", r"\1\n\2", header)

    for line in header.splitlines():
        line = line.strip()
        if not line or len(line) < 5 or len(line) > 200:
            continue

        # Remove email addresses from line before checking keywords
        no_email = _EMAIL_RE.sub("", line).strip().strip("{}, ")
        if len(no_email) < 5:
            continue  # line was entirely emails

        if not any(kw in no_email.lower() for kw in _AFFIL_KEYWORDS):
            continue

        # Strip leading superscript markers from the de-emailed text
        clean = _MARKER_LEADING.sub("", no_email).strip()
        clean = _MARKER_TRAILING.sub("", clean).strip()

        if not clean or len(clean) < 5 or clean.lower() in seen:
            continue

        # Reject prose sentences: institution names start with an uppercase
        # letter or digit, never with a lowercase word like "who", "the", "a".
        if not (clean[0].isupper() or clean[0].isdigit()):
            continue

        # Reject lines that are too long to be an institution name.
        if len(clean.split()) > 7:
            continue

        # Only keep lines that resolve to a known canonical institution.
        # Unrecognized text (e.g. a title phrase that contains "research")
        # is silently dropped here rather than surfaced as a garbage pill.
        canonical = _normalize_affiliation(clean)
        if not canonical or canonical.lower() in seen:
            continue

        affiliations.append(canonical)
        seen.add(canonical.lower())

    return affiliations[:6]


async def _extract_affiliations_from_arxiv_pdf(arxiv_id: str) -> list[str]:
    """
    Download an arXiv PDF and extract institution affiliations from page 1.
    Only the first page is read to keep latency low.
    """
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=30.0, follow_redirects=True
    ) as client:
        try:
            response = await client.get(pdf_url)
        except httpx.RequestError as exc:
            logger.warning("PDF download failed for arXiv %s: %s", arxiv_id, exc)
            return []

    if response.status_code != 200:
        logger.warning(
            "arXiv PDF returned %s for %s", response.status_code, arxiv_id
        )
        return []

    try:
        reader = pypdf.PdfReader(io.BytesIO(response.content))
        page_text = reader.pages[0].extract_text() if reader.pages else ""
    except Exception as exc:
        logger.warning("PDF parse error for arXiv %s: %s", arxiv_id, exc)
        return []

    affiliations = _parse_affiliations_from_first_page(page_text or "")
    logger.info(
        "PDF affiliation extraction for arXiv %s: %d institution(s) found",
        arxiv_id, len(affiliations),
    )
    return affiliations


async def _enrich_affiliations_from_pdfs(papers: list[dict]) -> None:
    """
    For papers that still have no affiliation data after S2 author-profile
    enrichment, attempt to extract affiliations from the arXiv PDF (if the
    paper has an ArXiv ID in its externalIds).

    Results are stored in a ``_pdf_affiliations`` key on each paper dict so
    that ``normalize_citing_work`` can fall back to them.
    """
    targets: list[tuple[dict, str]] = []  # (paper, arxiv_id)
    for paper in papers:
        has_affils = any(
            a.get("affiliations")
            for a in (paper.get("authors") or [])
        )
        if has_affils:
            continue
        arxiv_id = (paper.get("externalIds") or {}).get("ArXiv") or ""
        if arxiv_id:
            targets.append((paper, str(arxiv_id)))

    if not targets:
        return

    results = await asyncio.gather(
        *[_extract_affiliations_from_arxiv_pdf(arxiv_id) for _, arxiv_id in targets],
        return_exceptions=True,
    )

    matched = 0
    for (paper, arxiv_id), result in zip(targets, results):
        if isinstance(result, Exception) or not result:
            continue
        paper["_pdf_affiliations"] = result
        matched += 1

    logger.info(
        "PDF enrichment: %d/%d papers gained affiliation data from arXiv PDFs",
        matched, len(targets),
    )


async def _enrich_author_affiliations(papers: list[dict]) -> None:
    """
    Fetch author affiliations from S2 author profiles and inject them
    into each paper's authors list in-place.

    Uses POST /author/batch to fetch all unique authors in one round-trip.
    Author-level affiliations are more reliably populated than paper-level ones.
    """
    author_ids: list[str] = []
    seen: set[str] = set()
    for paper in papers:
        for author in (paper.get("authors") or []):
            aid = str(author.get("authorId") or "").strip()
            if aid and aid not in seen:
                author_ids.append(aid)
                seen.add(aid)

    if not author_ids:
        return

    async with httpx.AsyncClient(headers=_HEADERS, timeout=20.0) as client:
        try:
            response = await client.post(
                f"{_BASE_URL}/author/batch",
                params={"fields": "affiliations"},
                json={"ids": author_ids},
            )
        except httpx.RequestError as exc:
            logger.warning("S2 author/batch request error: %s", exc)
            return

    if response.status_code != 200:
        logger.warning(
            "S2 author/batch returned %s — skipping affiliation enrichment",
            response.status_code,
        )
        return

    affil_map: dict[str, list[str]] = {}
    for item in (response.json() or []):
        if not item:
            continue
        aid = str(item.get("authorId") or "").strip()
        affils = [str(a).strip() for a in (item.get("affiliations") or []) if str(a).strip()]
        if aid and affils:
            affil_map[aid] = affils

    for paper in papers:
        for author in (paper.get("authors") or []):
            aid = str(author.get("authorId") or "").strip()
            if aid in affil_map:
                author["affiliations"] = affil_map[aid]

    logger.info(
        "S2 affiliation enrichment: %d/%d author(s) have institution data",
        len(affil_map), len(author_ids),
    )


def normalize_citing_work(raw: dict) -> dict[str, Any]:
    """
    Convert a raw S2 citingPaper dict to the normalised shape used throughout
    the application (same keys as openalex.normalize_citing_work).
    """
    paper_id: str = raw.get("paperId") or ""
    external: dict = raw.get("externalIds") or {}

    doi: str | None = external.get("DOI") or external.get("doi")
    if doi:
        doi = _clean_doi(doi)

    title: str = raw.get("title") or "Untitled"
    authors: list[str] = []
    affiliations: list[str] = []
    seen_affiliations: set[str] = set()  # keyed on canonical lower-case form

    def _add_affil(raw_affil: str) -> None:
        norm = _normalize_affiliation(raw_affil)
        if norm and norm.lower() not in seen_affiliations:
            affiliations.append(norm)
            seen_affiliations.add(norm.lower())

    for a in (raw.get("authors") or []):
        name = (a.get("name") or "").strip()
        if name:
            authors.append(name)
        for affil in (a.get("affiliations") or []):
            _add_affil(affil)

    # Fall back to PDF-extracted affiliations when S2 profiles had none.
    if not affiliations:
        for affil in (raw.get("_pdf_affiliations") or []):
            _add_affil(str(affil))

    year: int | None = raw.get("year")
    publication_date: str | None = raw.get("publicationDate")

    if doi:
        url = f"https://doi.org/{doi}"
    elif raw.get("url"):
        url = raw["url"]
    elif paper_id:
        url = f"https://www.semanticscholar.org/paper/{paper_id}"
    else:
        url = ""

    return {
        "id": f"S2:{paper_id}" if paper_id else "",
        "doi": doi,
        "title": title,
        "authors": authors,
        "affiliations": affiliations,
        "year": year,
        "publication_date": publication_date,
        "url": url,
    }


_AUTHOR_FIELDS = "name,affiliations,paperCount,hIndex,externalIds"
_PAPER_FIELDS = (
    "title,year,authors,externalIds,venue,publicationVenue,"
    "citationCount,publicationTypes,s2FieldsOfStudy"
)


def _normalize_author_work(paper: dict) -> dict:
    """Convert a Semantic Scholar paper dict to the OpenAlex-compatible shape
    expected by the shared import loop in works.py."""
    external = paper.get("externalIds") or {}
    doi_raw = external.get("DOI")
    # Keep full URL form so the existing _strip_doi helper works unchanged.
    doi = f"https://doi.org/{doi_raw}" if doi_raw else None

    authorships = [
        {"author": {"display_name": a.get("name", "").strip()}}
        for a in (paper.get("authors") or [])
        if a.get("name")
    ]

    venue_name = (
        ((paper.get("publicationVenue") or {}).get("name") or paper.get("venue") or "")
        .strip() or None
    )

    # Map S2 fields of study → primary_topic + topics so extract_topics() works.
    s2_fields = paper.get("s2FieldsOfStudy") or []
    topic_names = list(dict.fromkeys(
        f.get("category", "").strip()
        for f in s2_fields
        if f.get("category")
    ))
    primary_topic = {"display_name": topic_names[0]} if topic_names else None
    topics_list = [{"display_name": t} for t in topic_names[1:3]]

    pub_types = paper.get("publicationTypes") or []
    if "JournalArticle" in pub_types:
        work_type = "journal-article"
    elif "Conference" in pub_types:
        work_type = "conference-paper"
    elif "Preprint" in pub_types:
        work_type = "preprint"
    else:
        work_type = None

    return {
        "doi": doi,
        "title": paper.get("title") or "",
        "publication_year": paper.get("year"),
        "id": f"S2:{paper.get('paperId', '')}",
        "cited_by_count": paper.get("citationCount") or 0,
        "type": work_type,
        "authorships": authorships,
        # Mimic OpenAlex venue structure so extract_venue() works unchanged.
        "primary_location": {"source": {"display_name": venue_name}} if venue_name else {},
        "primary_topic": primary_topic,
        "topics": topics_list,
    }


async def search_authors(query: str) -> list[dict]:
    """Search Semantic Scholar for author candidates. Returns up to 10 results."""
    hit, cached = await _author_search_cache.get(query)
    if hit:
        logger.debug("S2 author search cache hit: %s", query)
        return cached

    url = f"{_BASE_URL}/author/search"
    params: dict[str, Any] = {
        "query": query,
        "fields": _AUTHOR_FIELDS,
        "limit": 10,
    }

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("S2 author search error for query %s: %s", query, exc)
            return []

    if response.status_code != 200:
        logger.warning("S2 author search status %s for query %s", response.status_code, query)
        return []

    results = response.json().get("data", [])
    await _author_search_cache.set(query, results)
    return results


async def get_author_name(author_id: str) -> str | None:
    """Fetch just the display name for a Semantic Scholar author ID.
    Used as a last-resort fallback when no name was supplied at import time.
    """
    bare_id = author_id[3:] if author_id.startswith("S2:") else author_id
    async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0) as client:
        try:
            response = await client.get(
                f"{_BASE_URL}/author/{bare_id}",
                params={"fields": "name"},
            )
        except httpx.RequestError as exc:
            logger.error("S2 get_author_name error for %s: %s", bare_id, exc)
            return None
    if response.status_code == 200:
        return response.json().get("name") or None
    return None


async def get_paper_with_authors(doi: str) -> dict | None:
    """Look up a paper by DOI and return its title, year, and full author profiles.

    Each author object includes affiliations, paperCount, hIndex, and externalIds
    so the caller can present them as disambiguated AuthorCandidate records.
    Returns None if the paper is not found in S2.
    """
    hit, cached = await _paper_authors_cache.get(doi)
    if hit:
        logger.debug("S2 paper-with-authors cache hit: %s", doi)
        return cached

    _FIELDS = (
        "title,year,authors,authors.name,authors.affiliations,"
        "authors.paperCount,authors.hIndex,authors.externalIds"
    )
    candidates = _candidate_ids(doi)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
        for candidate_id in candidates:
            try:
                response = await client.get(
                    f"{_BASE_URL}/paper/{candidate_id}",
                    params={"fields": _FIELDS},
                )
            except httpx.RequestError as exc:
                logger.error("S2 paper lookup error for %s: %s", candidate_id, exc)
                continue

            if response.status_code == 200:
                logger.info("S2: resolved paper %s via %s", doi, candidate_id)
                result = response.json()
                await _paper_authors_cache.set(doi, result)
                return result
            if response.status_code != 404:
                logger.warning(
                    "S2 paper lookup status %s for %s", response.status_code, candidate_id
                )

    logger.info("S2: paper not found for DOI %s", doi)
    return None


async def get_works_by_author(author_id: str) -> list[dict]:
    """Fetch all papers for a Semantic Scholar author ID.

    Returns normalized OpenAlex-compatible dicts so the shared import loop
    in works.py works without modification.
    """
    # Strip "S2:" prefix stored by the app — the API uses bare numeric IDs.
    if author_id.startswith("S2:"):
        author_id = author_id[3:]

    hit, cached = await _works_by_author_cache.get(author_id)
    if hit:
        logger.debug("S2 works-by-author cache hit: %s", author_id)
        return cached

    url = f"{_BASE_URL}/author/{author_id}/papers"
    papers: list[dict] = []
    offset = 0
    limit = 1000

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        while True:
            params: dict[str, Any] = {
                "fields": _PAPER_FIELDS,
                "limit": limit,
                "offset": offset,
            }
            try:
                response = await client.get(url, params=params)
            except httpx.RequestError as exc:
                logger.error("S2 author papers error for %s: %s", author_id, exc)
                break
            if response.status_code != 200:
                logger.warning(
                    "S2 author papers status %s for author %s",
                    response.status_code,
                    author_id,
                )
                break

            payload = response.json()
            page: list[dict] = payload.get("data", [])
            papers.extend(page)

            # S2 uses offset pagination; stop when a partial page is returned.
            if len(page) < limit:
                break
            offset += limit

    logger.info("S2: found %d papers for author %s", len(papers), author_id)
    results = [_normalize_author_work(p) for p in papers]
    await _works_by_author_cache.set(author_id, results)
    return results


async def get_citation_counts(dois: list[str]) -> dict[str, int]:
    """
    Batch-fetch citation counts from Semantic Scholar for a list of DOIs.

    Returns a dict mapping each DOI (lowercased) to its citation count.
    DOIs not found in S2 are omitted from the result.
    """
    if not dois:
        return {}

    # Build candidate IDs (arXiv DOIs get ARXIV: prefix for better hit rate).
    ids = []
    for doi in dois:
        ids.extend(_candidate_ids(doi))

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        try:
            response = await client.post(
                f"{_BASE_URL}/paper/batch",
                params={"fields": "citationCount,externalIds"},
                json={"ids": ids},
            )
        except httpx.RequestError as exc:
            logger.error("Semantic Scholar batch request error: %s", exc)
            return {}

    if response.status_code != 200:
        logger.warning("Semantic Scholar batch returned status %s", response.status_code)
        return {}

    results: dict[str, int] = {}
    for item in response.json():
        if not item:
            continue
        count = item.get("citationCount")
        if count is None:
            continue
        external = item.get("externalIds") or {}
        doi = external.get("DOI")
        if doi:
            results[_clean_doi(doi).lower()] = count

    logger.info(
        "Semantic Scholar: fetched citation counts for %d/%d DOIs",
        len(results), len(dois),
    )
    return results
