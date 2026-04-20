import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.deps import get_current_user
from app.firebase_client import get_db
from app.models import Notification, PaginatedNotifications

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _doc_to_notification(doc_id: str, data: dict) -> Notification:
    """Convert a Firestore document dict to a Notification model."""

    def _to_dt(val: Any) -> datetime | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if hasattr(val, "timestamp"):
            # Firestore DatetimeWithNanoseconds
            return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
        if isinstance(val, str):
            # Stored as an ISO string (Pydantic serialisation path)
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    return Notification(
        id=doc_id,
        cited_work_id=data.get("cited_work_id", ""),
        cited_work_title=data.get("cited_work_title", ""),
        citing_work_id=data.get("citing_work_id", ""),
        citing_work_title=data.get("citing_work_title", ""),
        citing_work_doi=data.get("citing_work_doi"),
        citing_work_url=data.get("citing_work_url"),
        citing_authors=data.get("citing_authors", []),
        citing_affiliations=data.get("citing_affiliations", []),
        citing_year=data.get("citing_year"),
        citing_publication_date=data.get("citing_publication_date"),
        seen=data.get("seen", False),
        created_at=_to_dt(data.get("created_at")),
    )


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


_MAX_LIMIT = 100


@router.get("", response_model=PaginatedNotifications)
async def list_notifications(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
) -> PaginatedNotifications:
    """
    Return paginated notifications for the authenticated user, newest first.

    Sorting is done in Python after streaming the full collection so that
    documents with a null/missing created_at are not silently excluded.
    """
    thirty_days_ago = (datetime.now(tz=timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_year = int(thirty_days_ago[:4])

    docs = (
        db.collection("users")
        .document(uid)
        .collection("notifications")
        .stream()
    )
    all_notifications = [_doc_to_notification(doc.id, doc.to_dict() or {}) for doc in docs]

    # Only surface citations where the citing paper was published within the last
    # 30 days.  When an exact publication date is absent we fall back to year,
    # accepting anything from the cutoff year or later so that papers that haven't
    # yet been fully dated by OpenAlex/S2 are not silently excluded.
    all_notifications = [
        n for n in all_notifications
        if (n.citing_publication_date or "") >= thirty_days_ago
        or (not n.citing_publication_date and (n.citing_year or 0) >= cutoff_year)
    ]

    all_notifications.sort(key=lambda n: n.created_at or _EPOCH, reverse=True)

    total = len(all_notifications)
    unseen = sum(1 for n in all_notifications if not n.seen)
    pages = max(1, math.ceil(total / limit))
    page = min(page, pages)  # clamp to valid range

    offset = (page - 1) * limit
    items = all_notifications[offset : offset + limit]

    return PaginatedNotifications(
        items=items,
        total=total,
        unseen=unseen,
        page=page,
        limit=limit,
        pages=pages,
    )


def _notification_to_bibtex(n: Notification) -> str:
    """Convert a single Notification to a BibTeX @misc entry."""
    if n.citing_work_doi:
        key = re.sub(r"[^a-zA-Z0-9]", "_", n.citing_work_doi)[:50]
    else:
        key = f"citey_{re.sub(r'[^a-zA-Z0-9]', '_', n.id)[:30]}"

    authors = " and ".join(n.citing_authors) if n.citing_authors else "Unknown"
    title = (n.citing_work_title or "Untitled").replace("{", "\\{").replace("}", "\\}")
    cited = (n.cited_work_title or n.cited_work_id).replace("{", "\\{").replace("}", "\\}")

    lines = [f"@misc{{{key},"]
    lines.append(f"  author       = {{{{{authors}}}}},")
    lines.append(f"  title        = {{{{{title}}}}},")
    if n.citing_year:
        lines.append(f"  year         = {{{n.citing_year}}},")
    if n.citing_work_doi:
        lines.append(f"  doi          = {{{n.citing_work_doi}}},")
        lines.append(f"  howpublished = {{\\url{{https://doi.org/{n.citing_work_doi}}}}},")
    elif n.citing_work_url:
        lines.append(f"  howpublished = {{\\url{{{n.citing_work_url}}}}},")
    lines.append(f"  note         = {{Cites: {cited}}},")
    lines.append("}")
    return "\n".join(lines)


@router.get("/export.bib", response_class=PlainTextResponse)
async def export_bibtex(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> PlainTextResponse:
    """
    Export all of the authenticated user's citation notifications as a BibTeX
    file.  Unlike the paginated list endpoint this returns the full history
    (no 30-day window) so researchers can build a complete reference list.
    """
    _EXPORT_CAP = 5_000

    docs = (
        db.collection("users")
        .document(uid)
        .collection("notifications")
        .stream()
    )
    notifications = [_doc_to_notification(doc.id, doc.to_dict() or {}) for doc in docs]
    notifications.sort(key=lambda n: n.created_at or _EPOCH, reverse=True)
    notifications = notifications[:_EXPORT_CAP]

    if not notifications:
        body = "% No citation notifications found.\n"
    else:
        header = f"% Citey citation export — {len(notifications)} citing paper(s)\n\n"
        body = header + "\n\n".join(_notification_to_bibtex(n) for n in notifications) + "\n"

    return PlainTextResponse(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="citey-citations.bib"'},
    )


@router.post("/prune", status_code=200)
async def prune_notifications(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict:
    """
    Delete the authenticated user's stale notifications — those whose citing
    paper was published more than 30 days ago, or whose notification record is
    itself more than 30 days old.

    Returns {deleted: <count>}.
    """
    from app.services.citation_service import prune_user_notifications

    deleted = await prune_user_notifications(uid=uid, db=db, dry_run=False)
    logger.info("Manual prune for uid=%s: %d notification(s) deleted.", uid, deleted)
    return {"deleted": deleted}


@router.post("/seen/all", status_code=204)
async def mark_all_seen(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> None:
    """Mark every unseen notification as seen for the authenticated user."""
    unseen_docs = list(
        db.collection("users")
        .document(uid)
        .collection("notifications")
        .where("seen", "==", False)
        .stream()
    )

    if not unseen_docs:
        return

    # Firestore batch is capped at 500 writes — chunk if needed.
    batch_size = 500
    for i in range(0, len(unseen_docs), batch_size):
        batch = db.batch()
        for doc in unseen_docs[i : i + batch_size]:
            batch.update(doc.reference, {"seen": True})
        batch.commit()

    logger.info(
        "Bulk-marked %d notifications as seen for uid=%s", len(unseen_docs), uid
    )


@router.post("/{notification_id}/seen", response_model=Notification)
async def mark_seen(
    notification_id: str,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Notification:
    """Mark a single notification as seen."""
    ref = (
        db.collection("users")
        .document(uid)
        .collection("notifications")
        .document(notification_id)
    )
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    ref.update({"seen": True})
    logger.info("Marked notification %s as seen for uid=%s", notification_id, uid)

    updated = ref.get()
    return _doc_to_notification(notification_id, updated.to_dict() or {})
