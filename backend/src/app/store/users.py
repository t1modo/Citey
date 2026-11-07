"""Accounts: the ``users`` table."""

from typing import Any

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Alert, User, UserWork


async def get(session: AsyncSession, uid: str) -> User | None:
    return await session.get(User, uid)


async def create(session: AsyncSession, uid: str, email: str = "", **fields: Any) -> User:
    """The user's row, created if missing. An existing row is left as it is."""
    await session.exec(
        insert(User)
        .values(id=uid, email=email, notification_email=email or None, **fields)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    user = await session.get(User, uid, populate_existing=True)
    assert user is not None
    return user


async def update_fields(session: AsyncSession, uid: str, **fields: Any) -> None:
    """Set columns on the user's row (column names as in app.models.User)."""
    if fields:
        await session.exec(update(User).where(User.id == uid).values(**fields))


async def delete_user(session: AsyncSession, uid: str) -> None:
    """Delete the account. Its tracking and alerts go with it (ON DELETE CASCADE);
    papers and citations stay for anyone else tracking them."""
    await session.exec(delete(User).where(User.id == uid))


async def ids_after(session: AsyncSession, cursor: str | None = None) -> list[str]:
    """Every user ID in order, after *cursor* when given (for batched jobs)."""
    query = select(User.id).order_by(User.id)
    if cursor is not None:
        query = query.where(User.id > cursor)
    return list((await session.exec(query)).all())


async def clear_linked_author(session: AsyncSession, uid: str) -> None:
    """Stop tracking every paper, drop every alert and unlink the author, so the
    user can link a different author."""
    await session.exec(delete(Alert).where(Alert.user_id == uid))
    await session.exec(delete(UserWork).where(UserWork.user_id == uid))
    await update_fields(
        session,
        uid,
        linked_author_id=None,
        linked_author_name=None,
        additional_linked_authors=[],
        name_aliases=[],
    )


async def dismiss_work(session: AsyncSession, uid: str, key: str) -> None:
    """Remember that the user removed this paper, so syncs don't add it back."""
    key = key.lower()
    await session.exec(
        update(User)
        .where(User.id == uid, func.array_position(User.dismissed_work_keys, key).is_(None))
        .values(dismissed_work_keys=func.array_append(User.dismissed_work_keys, key))
    )


async def undismiss_work(session: AsyncSession, uid: str, key: str) -> None:
    await session.exec(
        update(User)
        .where(User.id == uid)
        .values(dismissed_work_keys=func.array_remove(User.dismissed_work_keys, key.lower()))
    )


def as_user_data(user: User) -> dict[str, Any]:
    """
    The user as the dict the rest of the app reads (field names as Firestore
    stored them), for helpers such as resolve_recipient and enforce_cooldown.
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

