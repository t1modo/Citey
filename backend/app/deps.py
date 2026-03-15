import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.firebase_client import verify_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """
    Extract and verify the Firebase Bearer token from the Authorization header.
    Returns the authenticated user's UID.
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
        decoded = verify_token(token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    uid: str = decoded.get("uid") or decoded.get("user_id", "")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a valid user ID.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return uid
