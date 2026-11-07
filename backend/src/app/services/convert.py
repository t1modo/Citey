"""Database rows (app.models) to the API's shapes (app.schemas), keeping the
IDs and field names the site and the rest of the app already use."""

from datetime import datetime
from typing import Any

from app.models import Alert, Citation, CitingWork, User, Work
from app.schemas import Notification, TrackedWork


def tracked_work(
    work: Work,
    added_at: datetime | None,
    *,
    citation_count: int = 0,
    new_citations_30d: int = 0,
) -> TrackedWork:
    """A paper as one user tracks it. ``id`` is the paper's key (see
    normalize), which the site passes back to delete it."""
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


def user_data(user: User) -> dict[str, Any]:
    """
    The user as the dict the rest of the app reads (the field names the routers
    and helpers use), for helpers such as resolve_recipient and enforce_cooldown.
    """
    return {
        "uid": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "notification_email": user.notification_email,
        "verified_notification_email": user.verified_notification_email,
        "notify_enabled": user.notify_enabled,
        "notify_new_publications": user.notify_new_publications,
        "scholar_url": user.scholar_url,
        "linked_author_id": user.linked_author_id,
        "linked_author_name": user.linked_author_name,
        "additional_linked_authors": list(user.additional_linked_authors or []),
        "name_aliases": list(user.name_aliases or []),
        "dismissed_work_ids": list(user.dismissed_work_keys or []),
        "last_import_at": user.last_import_at,
        "last_manual_check_at": user.last_manual_check_at,
        "last_manual_sync_at": user.last_manual_sync_at,
        "last_publication_sync": user.last_publication_sync_at,
        "last_email_test_at": user.last_email_test_at,
        "last_verification_email_at": user.last_verification_email_at,
        "last_confirm_email_at": user.last_confirm_email_at,
        "created_at": user.created_at,
    }
