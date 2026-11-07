import logging
import math
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_session
from app.deps import get_current_user
from app.schemas import Notification, PaginatedNotifications
from app.services import alert_service
from app.store import AlertStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_MAX_LIMIT = 100
# Alerts Citey found in the last 30 days. Found, not published: an index can
# list a paper weeks after it appears, and that citation is still news.
_WINDOW_DAYS = 30
_EXPORT_CAP = 5_000


@router.get("", response_model=PaginatedNotifications)
async def list_notifications(
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
) -> PaginatedNotifications:
    """Return the user's alerts from the last 30 days, newest first, a page at a time."""
    found_since = datetime.now(tz=timezone.utc) - timedelta(days=_WINDOW_DAYS)
    all_notifications = await alert_service.notifications(session, uid, since=found_since)

    total = len(all_notifications)
    unseen = sum(1 for n in all_notifications if not n.seen)
    pages = max(1, math.ceil(total / limit))
    page = min(page, pages)  # clamp to valid range
    offset = (page - 1) * limit

    return PaginatedNotifications(
        items=all_notifications[offset : offset + limit],
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
    session: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    """
    Export the user's citation alerts as a BibTeX file. Unlike the list,
    this has no 30-day window, so researchers can build a reference list.
    """
    notifications = await alert_service.notifications(session, uid, limit=_EXPORT_CAP)

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
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete the user's alerts found more than 30 days ago. Returns {deleted: <count>}."""
    before = datetime.now(tz=timezone.utc) - timedelta(days=_WINDOW_DAYS)
    deleted = await AlertStore(session).prune(before, uid=uid)
    await session.commit()
    logger.info("Manual prune for uid=%s: %d notification(s) deleted.", uid, deleted)
    return {"deleted": deleted}


@router.post("/seen/all", status_code=204)
async def mark_all_seen(
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Mark every unseen alert as seen for the user."""
    count = await AlertStore(session).mark_all_seen(uid)
    await session.commit()
    if count:
        logger.info("Bulk-marked %d notifications as seen for uid=%s", count, uid)


@router.post("/{notification_id}/seen", response_model=Notification)
async def mark_seen(
    notification_id: str,
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Notification:
    """Mark a single alert as seen."""
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    if not notification_id.isdigit():
        raise not_found
    alert_id = int(notification_id)
    if not await AlertStore(session).mark_seen(uid, alert_id):
        raise not_found
    await session.commit()
    logger.info("Marked notification %s as seen for uid=%s", notification_id, uid)
    marked = await alert_service.notification(session, uid, alert_id)
    assert marked is not None
    return marked
