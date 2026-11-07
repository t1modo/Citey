import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.concurrency import run_blocking
from app.clerk_auth import verify_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """
    Extract and verify the Clerk session token (Bearer) from the Authorization header.
    Returns the authenticated user's Clerk user ID.
    Raises HTTP 401 if the token is missing or invalid.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        # Checking a token can fetch the issuer's public keys: off the loop.
        decoded = await run_blocking(verify_token, token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    uid: str = decoded.get("uid", "")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a valid user ID.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return uid


def enforce_cooldown(
    user_data: dict,
    field: str,
    seconds: int,
    message: str,
    *,
    fallback_field: str | None = None,
) -> None:
    """Raise HTTP 429 if ``user_data[field]`` is more recent than *seconds* ago.

    *fallback_field* (usually ``created_at``) closes the loophole where a brand
    new account has no timestamp yet and could otherwise skip the limit.
    """
    from datetime import datetime, timezone

    last = user_data.get(field)
    if last is None and fallback_field:
        last = user_data.get(fallback_field)
    if not isinstance(last, datetime):
        return
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    retry_after = int(seconds - (datetime.now(tz=timezone.utc) - last).total_seconds())
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": message, "retry_after_seconds": retry_after},
        )
