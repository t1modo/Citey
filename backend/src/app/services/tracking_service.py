"""
Which papers each user tracks: starting, stopping, listing, and resetting.

The rules live here; the database work is in WorkStore, AlertStore,
CitationStore and UserStore. Nothing here commits.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Work
from app.schemas import TrackedWork
from app.services import convert
from app.store import AlertStore, CitationStore, UserStore, WorkStore

# A user who starts tracking a paper hears about its citations published in
# the last 30 days, as the first check of a newly added paper announces them.
RECENT_DAYS = 30


async def track_paper(
    session: AsyncSession,
    uid: str,
    key: str,
    fields: dict[str, Any],
    *,
    now: datetime,
    announce_recent: bool = True,
) -> tuple[Work, bool]:
    """
    Start tracking paper *key* (one shared row, created from *fields* if
    new). Returns (work, newly_tracked). Clears an earlier dismissal; with
    *announce_recent*, the paper's recent citations become alerts.
    """
    work_store = WorkStore(session)
    work = await work_store.upsert(key, fields)
    newly = await work_store.add_tracker(uid, work.id, now)
    await UserStore(session).undismiss_work(uid, key)
    if newly and announce_recent:
        recent = await CitationStore(session).published_since(work.id, now - timedelta(days=RECENT_DAYS))
        await AlertStore(session).add_many(uid, recent, created_at=now)
    return work, newly


async def untrack_paper(session: AsyncSession, uid: str, key: str) -> int | None:
    """
    Stop tracking paper *key*: the user's alerts for it go and the paper is
    remembered as dismissed. Returns the alerts removed, or None if the user
    did not track it. The shared paper stays for everyone else.
    """
    work_store = WorkStore(session)
    work = await work_store.get_by_key(key)
    if work is None or not await work_store.tracks(uid, key):
        return None
    removed = await AlertStore(session).delete_for_user(uid, work_id=work.id)
    await work_store.remove_tracker(uid, work.id)
    await UserStore(session).dismiss_work(uid, key)
    return removed


async def tracked_papers(session: AsyncSession, uid: str, *, now: datetime) -> list[TrackedWork]:
    """The user's papers with their alert counts, newest publication year first."""
    counts = await AlertStore(session).counts_by_work(uid, now - timedelta(days=30))
    papers = [
        convert.tracked_work(
            work,
            tracking.added_at,
            citation_count=counts.get(work.key, (0, 0))[0],
            new_citations_30d=counts.get(work.key, (0, 0))[1],
        )
        for work, tracking in await WorkStore(session).tracked(uid)
    ]
    papers.sort(key=lambda w: (w.year is not None, w.year or 0), reverse=True)
    return papers


async def reset_linked_author(session: AsyncSession, uid: str) -> None:
    """Stop tracking every paper, drop every alert and unlink the author, so
    the user can link a different author."""
    await AlertStore(session).delete_for_user(uid)
    await WorkStore(session).remove_all_trackers(uid)
    await UserStore(session).update_fields(
        uid,
        linked_author_id=None,
        linked_author_name=None,
        additional_linked_authors=[],
        name_aliases=[],
    )
