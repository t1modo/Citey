import json
import logging

import firebase_admin
from firebase_admin import auth, credentials

from app.config import get_settings

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None


def _initialize_firebase() -> firebase_admin.App:
    """Initialize the Firebase Admin SDK exactly once."""
    global _app
    if _app is not None:
        return _app

    settings = get_settings()

    if settings.firebase_service_account_json:
        try:
            service_account_info = json.loads(settings.firebase_service_account_json)
            cred = credentials.Certificate(service_account_info)
            logger.info("Firebase initialized from JSON string.")
        except json.JSONDecodeError as exc:
            raise ValueError(
                "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON."
            ) from exc
    elif settings.firebase_service_account_path:
        cred = credentials.Certificate(settings.firebase_service_account_path)
        logger.info(
            "Firebase initialized from file: %s",
            settings.firebase_service_account_path,
        )
    else:
        raise ValueError(
            "Either FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH "
            "must be set."
        )

    _app = firebase_admin.initialize_app(cred)
    return _app


def ensure_firebase() -> None:
    """Set up the Admin SDK before a Firebase Auth call. Checking a sign-in
    token does this too, but a nightly job has no token to check."""
    _initialize_firebase()


def verify_token(token: str) -> dict:
    """Verify a sign-in token and return its claims, with the user's ``uid``.

    Clerk session tokens are recognised by their issuer and checked against
    Clerk's public keys; anything else is a Firebase ID token. Both kinds
    work while users move from Firebase Auth to Clerk.
    """
    from app.clerk_auth import is_clerk_token, verify_clerk_token

    if is_clerk_token(token):
        return verify_clerk_token(token)
    _initialize_firebase()
    decoded = auth.verify_id_token(token)
    return decoded
