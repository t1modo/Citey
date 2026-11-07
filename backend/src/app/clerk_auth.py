"""
Verify Clerk session tokens.

Clerk signs session tokens with RS256; the public keys live at the
instance's Frontend API (``/.well-known/jwks.json``), so verifying needs no
secret. The instance comes from the publishable key, which encodes the
Frontend API host.

The session token template adds ``external_id`` (the user's Firebase UID,
set when existing users were imported) and ``email``. ``uid`` is the
external ID when there is one, so a migrated user keeps the data stored
under their Firebase UID; a user who signed up with Clerk has the Clerk user ID instead.
"""

from __future__ import annotations

import base64
from functools import lru_cache

import jwt

from app.config import get_settings

_LEEWAY_SECONDS = 5


def frontend_api(publishable_key: str) -> str:
    """'pk_test_ZWFnZXIt...JA' -> 'eager-shark-2856.clerk.accounts.dev'."""
    parts = publishable_key.split("_", 2)
    if len(parts) != 3 or parts[0] != "pk" or parts[1] not in ("test", "live"):
        raise ValueError("Not a Clerk publishable key")
    encoded = parts[2]
    host = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    return host.rstrip("$")


def issuer() -> str | None:
    key = get_settings().clerk_publishable_key
    return f"https://{frontend_api(key)}" if key else None


@lru_cache(maxsize=4)
def _jwks_client(iss: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{iss}/.well-known/jwks.json", cache_keys=True, lifespan=3600)


def is_clerk_token(token: str) -> bool:
    """True when the token's (unverified) issuer is the configured Clerk instance."""
    iss = issuer()
    if not iss:
        return False
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return False
    return claims.get("iss") == iss


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk session token; return claims shaped like Firebase's."""
    iss = issuer()
    if not iss:
        raise ValueError("Clerk is not configured")
    key = _jwks_client(iss).get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=iss,
        leeway=_LEEWAY_SECONDS,
        options={"require": ["exp", "iat", "sub", "iss"]},
    )
    allowed = _authorized_parties()
    azp = claims.get("azp")
    if azp and allowed and azp not in allowed:
        raise jwt.InvalidTokenError("Token was issued for another site")
    external_id = (claims.get("external_id") or "").strip()
    return {
        "uid": external_id or claims["sub"],
        "clerk_user_id": claims["sub"],
        "email": claims.get("email") or None,
        "email_verified": True,  # Clerk verifies the address at sign-up
        "auth_provider": "clerk",
    }


def _authorized_parties() -> set[str]:
    """Origins the site is served from; a token minted elsewhere is refused."""
    raw = get_settings().allowed_origins.strip()
    if not raw or raw == "*":
        return set()
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}
