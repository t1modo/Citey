"""
Clerk, through its Backend SDK (clerk-backend-api): checking session
tokens, and finding, listing and deleting users.

Citey knows a user by their ``uid``. A user imported from Firebase Auth has
their Firebase UID as Clerk's ``external_id``, and keeps it as their uid, so
their data stays where it is; a user who signed up with Clerk is known by
their Clerk user ID (``user_...``).

Settings: CLERK_SECRET_KEY checks tokens (fetching Clerk's signing keys)
and calls the user API. CLERK_JWT_KEY, the instance's PEM public key,
checks tokens without a network call.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from clerk_backend_api import Clerk, models
from clerk_backend_api.security import (
    TokenVerificationError,
    TokenVerificationErrorReason,
    VerifyTokenOptions,
    verify_token_async,
)
from clerk_backend_api.security.machine import get_token_type
from clerk_backend_api.security.types import TokenType

from app.config import get_settings

logger = logging.getLogger(__name__)

CLERK_ID_PREFIX = "user_"
# Clerk's largest page of users.
_PAGE_SIZE = 500
# Claims every session token carries; the SDK checks exp only when present.
_REQUIRED_CLAIMS = ("sub", "iat", "exp")


@dataclass(frozen=True)
class ClerkUser:
    id: str
    external_id: str | None
    email: str
    email_verified: bool

    @property
    def uid(self) -> str:
        return self.external_id or self.id


def can_verify_tokens() -> bool:
    settings = get_settings()
    return bool(settings.clerk_secret_key or settings.clerk_jwt_key)


def configured() -> bool:
    """True when the user API can be called (it needs the secret key)."""
    return bool(get_settings().clerk_secret_key)


def _client() -> Clerk:
    """A client for one block of calls: ``async with _client() as clerk``.
    A fresh one each time, so its HTTP connections never outlive the event
    loop that opened them."""
    return Clerk(bearer_auth=get_settings().clerk_secret_key)


def _authorized_parties() -> list[str] | None:
    """Origins the site is served from; a token minted for another is refused."""
    raw = get_settings().allowed_origins.strip()
    if not raw or raw == "*":
        return None
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

# Clerk user ID -> uid, for tokens whose template leaves out external_id.
_uid_cache: OrderedDict[str, str] = OrderedDict()
_UID_CACHE_SIZE = 1024


async def _uid_for(clerk_user_id: str) -> str:
    if clerk_user_id in _uid_cache:
        _uid_cache.move_to_end(clerk_user_id)
        return _uid_cache[clerk_user_id]
    user = await get_user(clerk_user_id)
    uid = user.uid if user else clerk_user_id
    _uid_cache[clerk_user_id] = uid
    if len(_uid_cache) > _UID_CACHE_SIZE:
        _uid_cache.popitem(last=False)
    return uid


async def verify_session_token(token: str) -> dict[str, Any]:
    """
    Check a Clerk session token and return its claims with the user's
    ``uid``. Only user session tokens are accepted: Clerk's machine tokens,
    OAuth tokens and API keys are refused.

    The session token template (Clerk Dashboard > Sessions) should add
    ``"external_id": "{{user.external_id}}"``. Without it, the uid is looked
    up from Clerk once per user and remembered.
    """
    settings = get_settings()
    if not can_verify_tokens():
        raise TokenVerificationError(TokenVerificationErrorReason.SECRET_KEY_MISSING)
    if get_token_type(token) is not TokenType.SESSION_TOKEN:
        raise TokenVerificationError(TokenVerificationErrorReason.TOKEN_INVALID)

    claims = await verify_token_async(
        token,
        VerifyTokenOptions(
            secret_key=settings.clerk_secret_key or None,
            jwt_key=settings.clerk_jwt_key or None,
            authorized_parties=_authorized_parties(),
        ),
    )
    sub = claims.get("sub") or ""
    if any(claims.get(k) is None for k in _REQUIRED_CLAIMS) or not sub.startswith(CLERK_ID_PREFIX):
        raise TokenVerificationError(TokenVerificationErrorReason.TOKEN_INVALID)

    if "external_id" in claims:
        uid = (claims.get("external_id") or "").strip() or sub
    elif configured():
        uid = await _uid_for(sub)
    else:
        uid = sub
    return {
        **claims,
        "uid": uid,
        "clerk_user_id": sub,
        "auth_provider": "clerk",
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def _from_model(user: models.User) -> ClerkUser:
    emails = list(user.email_addresses or [])
    primary = next((e for e in emails if e.id == user.primary_email_address_id), emails[0] if emails else None)
    status = getattr(primary.verification, "status", None) if primary else None
    return ClerkUser(
        id=user.id,
        external_id=(user.external_id or None),
        email=primary.email_address if primary else "",
        email_verified=status == "verified",
    )


def _not_found(exc: models.ClerkErrors) -> bool:
    return exc.status_code == 404


async def get_user(uid: str) -> ClerkUser | None:
    """The Clerk user for *uid* (a Clerk user ID, or a Firebase UID kept as
    the external ID), or None when Clerk has no such user."""
    async with _client() as clerk:
        if uid.startswith(CLERK_ID_PREFIX):
            try:
                return _from_model(await clerk.users.get_async(user_id=uid))
            except models.ClerkErrors as exc:
                if _not_found(exc):
                    return None
                raise
        found = await clerk.users.list_async(request={"external_id": [uid], "limit": 1})
        return _from_model(found[0]) if found else None


async def delete_user(uid: str) -> bool:
    """Delete *uid*'s Clerk user. False when Clerk has none."""
    user = await get_user(uid)
    if user is None:
        return False
    async with _client() as clerk:
        try:
            await clerk.users.delete_async(user_id=user.id)
        except models.ClerkErrors as exc:
            if _not_found(exc):
                return False
            raise
    _uid_cache.pop(user.id, None)
    return True


async def all_uids() -> set[str]:
    """The uid of every Clerk user (both IDs of an imported user)."""
    uids: set[str] = set()
    offset = 0
    async with _client() as clerk:
        while True:
            page = await clerk.users.list_async(request={"limit": _PAGE_SIZE, "offset": offset})
            for user in page:
                uids.add(user.id)
                if user.external_id:
                    uids.add(user.external_id)
            if len(page) < _PAGE_SIZE:
                return uids
            offset += _PAGE_SIZE
