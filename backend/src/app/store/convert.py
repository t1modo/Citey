"""Rows to the API's shapes (app.schemas), keeping the IDs the site already uses."""

from datetime import datetime

from app.models import Alert, Citation, CitingWork, Work
from app.schemas import Notification, TrackedWork


def tracked_work(
    work: Work,
    added_at: datetime | None,
    *,
    citation_count: int = 0,
    new_citations_30d: int = 0,
) -> TrackedWork:
    """A paper as one user tracks it. ``id`` is the paper's key (its old
    Firestore document ID), which the site passes back to delete it."""
    return TrackedWork(
        id=work.key,
        doi=work.doi,
        openalex_id=work.openalex_id,
        title=work.title,
        authors=list(work.authors or []),
        year=work.year,
        venue=work.venue,
        work_type=work.work_type,
        topics=list(work.topics or []),
        added_at=added_at,
        last_checked_at=work.last_checked_at,
        citation_count=citation_count,
        new_citations_30d=new_citations_30d,
        s2_citation_count=work.s2_citation_count,
        openalex_citation_count=work.openalex_citation_count,
    )


def notification(alert: Alert, citation: Citation, citing: CitingWork, work: Work) -> Notification:
    """An alert as the site shows it. ``id`` is the alert's ID."""
    return Notification(
        id=str(alert.id),
        cited_work_id=work.key,
        cited_work_title=work.title,
        citing_work_id=citing.key,
        citing_work_title=citing.title,
        citing_work_doi=citing.doi,
        citing_work_url=citing.url,
        citing_authors=list(citing.authors or []),
        citing_affiliations=list(citing.affiliations or []),
        citing_year=citing.year,
        citing_publication_date=citing.publication_date,
        seen=alert.seen,
        emailed=alert.emailed,
        created_at=alert.created_at,
    )
