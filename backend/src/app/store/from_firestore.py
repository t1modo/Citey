"""
Copying one user's Firestore data into Postgres (scripts/copy_firestore_to_postgres.py).

Takes the documents as plain dicts, so it is tested without Firestore. Safe
to run again: every write is an upsert, the user's settings are refreshed
from Firestore, and papers, citations and alerts already copied are found
rather than duplicated. Goes away with Firestore.

    users/{uid}                    -> users
    users/{uid}/trackedWorks/{key} -> works (shared by key) + user_works
    users/{uid}/notifications/{id} -> citing_works + citations + alerts
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import User, UserWork, Work
from app.schemas import is_openalex_work_id
from app.services.citing_identity import identity_keys
from app.store import alerts, citations

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_USER_FIELDS = {
    # Postgres column: Firestore field
    "email": "email",
    "display_name": "display_name",
    "notification_email": "notification_email",
    "verified_notification_email": "verified_notification_email",
    "scholar_url": "scholar_url",
    "linked_author_id": "linked_author_id",
    "linked_author_name": "linked_author_name",
}
_USER_TIMES = {
    "last_import_at": "last_import_at",
    "last_manual_check_at": "last_manual_check_at",
    "last_manual_sync_at": "last_manual_sync_at",
    "last_publication_sync_at": "last_publication_sync",
    "last_email_test_at": "last_email_test_at",
    "last_verification_email_at": "last_verification_email_at",
    "last_confirm_email_at": "last_confirm_email_at",
}


def as_datetime(value: Any) -> datetime | None:
    """A Firestore timestamp, datetime or ISO string as an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


@dataclass
class Copied:
    users: int = 0
    tracked: int = 0
    alerts: int = 0
    skipped: list[str] = field(default_factory=list)

    def add(self, other: "Copied") -> None:
        self.users += other.users
        self.tracked += other.tracked
        self.alerts += other.alerts
        self.skipped += other.skipped


async def copy_user(
    session: AsyncSession,
    uid: str,
    user: dict[str, Any],
    tracked: dict[str, dict[str, Any]],
    notifications: dict[str, dict[str, Any]],
) -> Copied:
    """Copy one user. *tracked* and *notifications* map document ID to data."""
    out = Copied(users=1)
    await _copy_profile(session, uid, user)

    work_ids: dict[str, int] = {}
    for key, data in tracked.items():
        work_ids[key] = await _copy_work(session, key, data)
        await session.exec(
            insert(UserWork)
            .values(user_id=uid, work_id=work_ids[key], added_at=as_datetime(data.get("added_at")) or EPOCH)
            .on_conflict_do_nothing(index_elements=["user_id", "work_id"])
        )
        out.tracked += 1

    for doc_id, data in notifications.items():
        cited = data.get("cited_work_id") or ""
        if cited not in work_ids:
            # A notification for a paper the user no longer tracks.
            out.skipped.append(f"{uid}/notifications/{doc_id}: paper {cited or '?'} not tracked")
            continue
        doi = (data.get("citing_work_doi") or "").strip().lower() or None
        key = doi or (data.get("citing_work_id") or "").strip().lower()
        if not key:
            out.skipped.append(f"{uid}/notifications/{doc_id}: no citing paper ID")
            continue
        created = as_datetime(data.get("created_at")) or EPOCH
        title = data.get("citing_work_title") or "Untitled"
        keys = identity_keys(doi=doi, title=title, source_ids=[data.get("citing_work_id")])
        citation_id, _ = await citations.record(
            session,
            work_ids[cited],
            key,
            keys,
            {
                "doi": doi,
                "url": data.get("citing_work_url"),
                "title": title,
                "authors": list(data.get("citing_authors") or []),
                "affiliations": list(data.get("citing_affiliations") or []),
                "year": data.get("citing_year"),
                "publication_date": data.get("citing_publication_date"),
            },
            found_at=created,
        )
        # Older notifications have no `emailed` field and were never re-sent;
        # they count as emailed.
        if await alerts.add(
            session,
            uid,
            citation_id,
            created_at=created,
            seen=bool(data.get("seen", False)),
            emailed=bool(data.get("emailed", True)),
        ):
            out.alerts += 1
    await session.flush()
    return out


async def _copy_profile(session: AsyncSession, uid: str, user: dict[str, Any]) -> None:
    values: dict[str, Any] = {col: user.get(src) for col, src in _USER_FIELDS.items()}
    values["email"] = values["email"] or ""
    values.update({col: as_datetime(user.get(src)) for col, src in _USER_TIMES.items()})
    values["notify_enabled"] = bool(user.get("notify_enabled", True))
    values["notify_new_publications"] = bool(user.get("notify_new_publications", True))
    values["additional_linked_authors"] = [
        {"id": e.get("id"), "name": e.get("name")}
        for e in (user.get("additional_linked_authors") or [])
        if isinstance(e, dict) and e.get("id")
    ]
    values["name_aliases"] = [a for a in (user.get("name_aliases") or []) if isinstance(a, str)]
    values["dismissed_work_keys"] = sorted({d.lower() for d in (user.get("dismissed_work_ids") or [])})
    created = as_datetime(user.get("created_at"))
    stmt = insert(User).values(id=uid, **values, **({"created_at": created} if created else {}))
    await session.exec(stmt.on_conflict_do_update(index_elements=["id"], set_=values))


async def _copy_work(session: AsyncSession, key: str, data: dict[str, Any]) -> int:
    """The shared paper row. Each user's copy of the check state is merged:
    the latest check wins, and the already-reported keys are combined."""
    oa_id = data.get("openalex_id") if is_openalex_work_id(data.get("openalex_id")) else None
    checked = as_datetime(data.get("last_checked_at"))
    values = {
        "key": key,
        "doi": (data.get("doi") or "").strip().lower() or None,
        "openalex_id": oa_id,
        "title": data.get("title") or "Untitled",
        "authors": list(data.get("authors") or []),
        "year": data.get("year"),
        "venue": data.get("venue"),
        "work_type": data.get("work_type"),
        "topics": list(data.get("topics") or []),
        "openalex_citation_count": data.get("openalex_citation_count") if oa_id else None,
        "s2_citation_count": data.get("s2_citation_count"),
        "last_checked_at": checked,
        "last_check_failed_sources": list(data.get("last_check_failed_sources") or []),
        "citation_window": data.get("citation_window"),
        "known_citing_keys": sorted(set(data.get("notified_keys") or [])),
    }
    stmt = insert(Work).values(**values)
    ex = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "doi": func.coalesce(Work.doi, ex.doi),
            "openalex_id": func.coalesce(Work.openalex_id, ex.openalex_id),
            "venue": func.coalesce(Work.venue, ex.venue),
            "work_type": func.coalesce(Work.work_type, ex.work_type),
            "openalex_citation_count": func.greatest(Work.openalex_citation_count, ex.openalex_citation_count),
            "s2_citation_count": func.greatest(Work.s2_citation_count, ex.s2_citation_count),
            "last_checked_at": func.greatest(Work.last_checked_at, ex.last_checked_at),
            "citation_window": func.greatest(Work.citation_window, ex.citation_window),
            # The union of both copies' keys, each once.
            "known_citing_keys": literal_column(
                "ARRAY(SELECT DISTINCT k FROM unnest(works.known_citing_keys"
                " || excluded.known_citing_keys) AS k ORDER BY k)"
            ),
        },
    )
    return (await session.exec(stmt.returning(Work.id))).scalar_one()
