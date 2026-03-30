import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

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
