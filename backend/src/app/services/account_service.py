"""
Sign-in accounts, wherever they live, while users move from Firebase Auth
to Clerk. A request may carry either kind of token, and an account may be
in Firebase, in Clerk (a new sign-up), or in both (an imported user, whose
Clerk external ID is their Firebase UID). The rest of the app asks here,
never Firebase or Clerk directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jwt
from firebase_admin import auth as firebase_auth

from app import firebase_client
from app.core import clerk
from app.core.concurrency import run_blocking

logger = logging.getLogger(__name__)

FIREBASE_ISSUER_PREFIX = "https://securetoken.google.com/"


@dataclass(frozen=True)
class Account:
    uid: str
    email: str
    email_verified: bool
    provider: str  # "clerk" or "firebase"


def _issuer(token: str) -> str:
    """The token's issuer, unverified: it only decides who checks it."""
    try:
        return jwt.decode(token, options={"verify_signature": False}).get("iss") or ""
    except jwt.PyJWTError:
        return ""


async def verify_token(token: str) -> dict[str, Any]:
    """
    Check a sign-in token; its claims, with the user's ``uid``. Firebase ID
    tokens go to Firebase; any other token goes to Clerk when Clerk is set
    up. Raises when the token is not valid.
    """
    if clerk.can_verify_tokens() and not _issuer(token).startswith(FIREBASE_ISSUER_PREFIX):
        return await clerk.verify_session_token(token)
    # Checking a Firebase token can fetch Google's public keys: off the loop.
    return await run_blocking(firebase_client.verify_id_token, token)


# ---------------------------------------------------------------------------
# Firebase Auth (blocking SDK, so each call runs off the loop)
# ---------------------------------------------------------------------------


def _firebase_user_blocking(uid: str) -> Any | None:
    firebase_client.ensure_firebase()
    try:
        return firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        return None


def _delete_firebase_user_blocking(uid: str) -> bool:
    firebase_client.ensure_firebase()
    try:
        firebase_auth.delete_user(uid)
    except firebase_auth.UserNotFoundError:
        return False
    return True


def _firebase_uids_blocking() -> set[str]:
    firebase_client.ensure_firebase()
    uids: set[str] = set()
    page = firebase_auth.list_users()
    while page:
        uids.update(user.uid for user in page.users)
        page = page.get_next_page()
    return uids


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


async def get_account(uid: str) -> Account | None:
    """
    The account *uid* signs in with: Clerk's when it has one (an imported
    user's Clerk account is the one in use), else Firebase's. None when
    neither has it, or neither can be reached.
    """
    if clerk.configured():
        try:
            user = await clerk.get_user(uid)
        except Exception as exc:  # noqa: BLE001  (fall back to Firebase)
            logger.warning("Could not look up Clerk user for uid=%s: %s", uid, exc)
        else:
            if user is not None:
                return Account(uid, user.email, user.email_verified, "clerk")
    try:
        record = await run_blocking(_firebase_user_blocking, uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not look up Firebase user for uid=%s: %s", uid, exc)
        return None
    if record is None:
        return None
    return Account(uid, record.email or "", bool(record.email_verified), "firebase")


async def delete_account(uid: str) -> None:
    """Delete *uid*'s sign-in records in Clerk and Firebase, so they cannot
    sign in again. Failures are logged: the caller has already removed
    their data."""
    if clerk.configured():
        try:
            if await clerk.delete_user(uid):
                logger.info("Deleted Clerk user for uid=%s", uid)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not delete Clerk user for uid=%s: %s", uid, exc)
    try:
        if await run_blocking(_delete_firebase_user_blocking, uid):
            logger.info("Deleted Firebase Auth record for uid=%s", uid)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not delete Firebase Auth user %s: %s", uid, exc)


async def sign_in_uids() -> set[str]:
    """
    Every uid that can sign in: Firebase Auth's and, when Clerk is set up,
    Clerk's. Raises if either list cannot be read, so a cleanup that relies
    on it stops instead of deleting accounts it could not see.
    """
    uids = await run_blocking(_firebase_uids_blocking)
    if clerk.configured():
        uids |= await clerk.all_uids()
    return uids
