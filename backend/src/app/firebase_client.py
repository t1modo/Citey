import json
import logging
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials, firestore

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


def get_db() -> Any:
    """Return the Firestore client, initializing Firebase if necessary.

    The app's data lives in Postgres; only scripts/copy_firestore_to_postgres.py
    still reads Firestore.
    """
    _initialize_firebase()
    return firestore.client()


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
