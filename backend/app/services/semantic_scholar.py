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

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.app)"}
_CITATION_FIELDS = "paperId,title,year,authors,externalIds,publicationDate,url"
_PAGE_LIMIT = 500
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
        arxiv_id = clean.split("/arxiv.", 1)[1]
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
        results = [
            p for p in results
            if (p.get("publicationDate") or "") >= since_date
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

    # --- Step 4: heuristic fallback — prefer the segment most likely to be an
    # institution name (contains an org keyword) over a bare city/place name.
    # Scan from the end so that "Dept of X, University of Y, Unknown City"
    # returns "University of Y" rather than "Unknown City".
    for seg in reversed(org_segments):
        if any(kw in seg.lower() for kw in _AFFIL_KEYWORDS):
            return seg
    # Last resort: just return whatever survived geo-stripping.
    return org_segments[-1]


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

        # Reject lines that are too long to be an institution name (prose
        # sentences tend to have many words; a real affiliation is concise).
        if len(clean.split()) > 10:
            continue

        affiliations.append(clean)
        seen.add(clean.lower())

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
