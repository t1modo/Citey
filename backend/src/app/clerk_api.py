"""
Clerk Backend API lookups, for code that runs without a sign-in token.

The nightly jobs need every account's ID, and a new profile needs its
email. Accounts are known by the same uid the API uses: the user's
external_id (their Firebase UID, set when they were imported) or, for
someone who signed up with Clerk, their Clerk user ID.

Both calls block, so callers run them off the event loop.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_API = "https://api.clerk.com/v1"
_PAGE = 500


class ClerkUnavailable(RuntimeError):
    """Clerk is configured but could not be reached."""


def configured() -> bool:
    return bool(get_settings().clerk_secret_key)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_API,
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {get_settings().clerk_secret_key}",
            # Cloudflare in front of api.clerk.com blocks default agents.
            "User-Agent": "citey-api/1.0",
        },
    )


def account_uid(user: dict) -> str:
    """The uid the rest of the app knows this Clerk user by."""
    return (user.get("external_id") or "").strip() or user["id"]


def list_account_uids() -> set[str]:
    """Every Clerk user's uid. Raises ClerkUnavailable rather than returning a
    partial list: a missing account would look like an orphan."""
    uids: set[str] = set()
    offset = 0
    try:
        with _client() as client:
            while True:
                resp = client.get("/users", params={"limit": _PAGE, "offset": offset})
                resp.raise_for_status()
                page = resp.json()
                uids.update(account_uid(u) for u in page)
                if len(page) < _PAGE:
                    return uids
                offset += _PAGE
    except httpx.HTTPError as exc:
        raise ClerkUnavailable(f"listing Clerk users failed: {type(exc).__name__}") from exc


def email_for(uid: str) -> str:
    """The primary email of the Clerk user with this uid, or ''."""
    try:
        with _client() as client:
            if uid.startswith("user_"):
                resp = client.get(f"/users/{uid}")
                users = [resp.json()] if resp.status_code == 200 else []
            else:
                resp = client.get("/users", params={"external_id": uid, "limit": 1})
                users = resp.json() if resp.status_code == 200 else []
    except httpx.HTTPError:
        return ""
    if not users:
        return ""
    user = users[0]
    primary = user.get("primary_email_address_id")
    for address in user.get("email_addresses") or []:
        if address.get("id") == primary:
            return address.get("email_address") or ""
    return ""
