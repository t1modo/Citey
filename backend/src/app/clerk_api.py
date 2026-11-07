"""
Clerk Backend API calls, for code that runs without a sign-in token or acts
on the account itself.

The nightly jobs need every account's ID, a new profile needs its email, and
deleting an account removes the Clerk user. Accounts are known by their
Clerk user ID, the same uid the API and Postgres use.

All calls block, so callers run them off the event loop.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_API = "https://api.clerk.com/v1"
_PAGE = 500


class ClerkUnavailable(RuntimeError):
    """Clerk is not configured, or could not be reached."""


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


def list_account_uids() -> set[str]:
    """Every Clerk user's ID. Raises ClerkUnavailable rather than returning a
    partial (or empty) list: a missing account would look like an orphan and
    have its data deleted."""
    if not configured():
        raise ClerkUnavailable("CLERK_SECRET_KEY is not set")
    uids: set[str] = set()
    offset = 0
    try:
        with _client() as client:
            while True:
                resp = client.get("/users", params={"limit": _PAGE, "offset": offset})
                resp.raise_for_status()
                page = resp.json()
                uids.update(u["id"] for u in page)
                if len(page) < _PAGE:
                    return uids
                offset += _PAGE
    except httpx.HTTPError as exc:
        raise ClerkUnavailable(f"listing Clerk users failed: {type(exc).__name__}") from exc


def email_for(uid: str) -> str:
    """The primary email of the Clerk user with this ID, or ''."""
    if not configured():
        return ""
    try:
        with _client() as client:
            resp = client.get(f"/users/{uid}")
    except httpx.HTTPError:
        return ""
    if resp.status_code != 200:
        return ""
    user = resp.json()
    primary = user.get("primary_email_address_id")
    for address in user.get("email_addresses") or []:
        if address.get("id") == primary:
            return address.get("email_address") or ""
    return ""


def delete_user(uid: str) -> None:
    """Delete the Clerk user, so they cannot sign in again. A user already
    gone (404) counts as deleted; any other failure raises."""
    if not configured():
        raise ClerkUnavailable("CLERK_SECRET_KEY is not set")
    with _client() as client:
        resp = client.delete(f"/users/{uid}")
    if resp.status_code not in (200, 404):
        resp.raise_for_status()
