"""
Accounts: making sure a user's row exists, and reading it the way the rest
of the app expects. The database work is in UserStore; nothing here commits.
"""

import logging
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.concurrency import run_blocking
from app import clerk_api
from app.clerk_auth import signed_in_email
from app.models import User
from app.services import convert
from app.store import UserStore

logger = logging.getLogger(__name__)


async def _account_email(uid: str) -> str:
    """The sign-in email: from the request's verified session token, else
    from Clerk's Backend API (a blocking call, so off the loop)."""
    return signed_in_email.get() or await run_blocking(clerk_api.email_for, uid)


async def ensure_user(session: AsyncSession, uid: str) -> User:
    """The user's row, created with their sign-in email the first time.
    Anything that points at a user (tracking, alerts) needs the row first.
    A row whose email is still empty gets it filled in."""
    store = UserStore(session)
    user = await store.get(uid)
    if user is None:
        user = await store.create(uid, email=await _account_email(uid))
        logger.info("Created profile for uid=%s", uid)
    elif not user.email:
        email = await _account_email(uid)
        if email:
            user.email = email
            if not user.notification_email:
                user.notification_email = email
            session.add(user)
            logger.info("Filled in the missing email for uid=%s", uid)
    if not user.email:
        logger.warning("Profile for uid=%s has no email; check CLERK_SECRET_KEY", uid)
    return user


async def user_data(session: AsyncSession, uid: str) -> dict[str, Any]:
    """The user as the dict the app reads (see convert.user_data), or {}."""
    user = await UserStore(session).get(uid)
    return convert.user_data(user) if user else {}
