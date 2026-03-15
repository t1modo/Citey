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
    so we try that first.  All papers also get a DOI:{doi} attempt.
    """
    clean = _clean_doi(doi)
    ids: list[str] = []
    if clean.lower().startswith("10.48550/arxiv."):
        arxiv_id = clean.split("/arxiv.", 1)[1]
        ids.append(f"ARXIV:{arxiv_id}")
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


async def get_citing_papers(doi: str) -> list[dict]:
    """
    Fetch all papers that cite *doi* from Semantic Scholar.

    Strategy:
      1. Resolve the DOI to a native S2 paperId via the batch endpoint.
         This handles arXiv DOIs, ACL Anthology DOIs, and any encoding
         quirks without hitting path-based URL issues.
      2. Page through /paper/{paperId}/citations using the numeric S2 ID.

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
            try:
                response = await client.get(
                    f"{_BASE_URL}/paper/{s2_id}/citations", params=params
                )
            except httpx.RequestError as exc:
                logger.error("S2 citations request error for %s (DOI %s): %s", s2_id, doi, exc)
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
    ("university of pennsylvania", "UPenn"),
    ("university of michigan", "U. Michigan"),
    ("university of washington", "UW"),
    ("university of chicago", "U. Chicago"),
    ("university of texas", "UT"),
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
    ("seoul national university", "SNU"),
    ("hebrew university", "Hebrew University"),
    ("technion", "Technion"),
    ("weizmann institute", "Weizmann Institute"),
    ("max planck institute", "Max Planck Institute"),
    ("inria", "INRIA"),
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
_MARKER_LEADING = re.compile(r"^[\d\s*†‡§¶#◦○●,;:\-]+")
_MARKER_TRAILING = re.compile(r"[,;:\-\s]+$")


def _parse_affiliations_from_first_page(text: str) -> list[str]:
    """
    Extract institution names from the first-page text of an academic paper.

    Strategy:
      1. Truncate to everything before the "Abstract" heading.
      2. Pre-split combined lines where mid-line superscript numbers mark a
         new affiliation (e.g. "Watson AI Lab 3IBM Research").
      3. Strip leading markers and email addresses from each candidate line.
      4. Keep lines that contain an academic or corporate keyword.
    """
    abstract_match = re.search(r"\bAbstract\b", text, re.IGNORECASE)
    header = text[: abstract_match.start()] if abstract_match else text[:3000]

    # Split mid-line affiliation markers so "Lab 3IBM" → "Lab\nIBM"
    header = re.sub(r"(\w)\s+(\d+)(?=[A-Z])", r"\1\n\2", header)

    affiliations: list[str] = []
    seen: set[str] = set()

    for line in header.splitlines():
        line = line.strip()
        if not line or len(line) < 5 or len(line) > 300:
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

        if clean and len(clean) >= 5 and clean.lower() not in seen:
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
