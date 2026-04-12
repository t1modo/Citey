import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_current_user
from app.firebase_client import get_db
from app.models import LinkedAuthorEntry, UpdateProfileRequest, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


def _doc_to_profile(uid: str, data: dict) -> UserProfile:
    """Convert a raw Firestore document dict to a UserProfile."""
    created_at = data.get("created_at")
    if hasattr(created_at, "timestamp"):
        # Firestore DatetimeWithNanoseconds → Python datetime
        created_at = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at

    return UserProfile(
        uid=uid,
        email=data.get("email", ""),
        display_name=data.get("display_name"),
        notification_email=data.get("notification_email"),
        notify_enabled=data.get("notify_enabled", True),
        notify_new_publications=data.get("notify_new_publications", True),
        scholar_url=data.get("scholar_url"),
        linked_author_id=data.get("linked_author_id"),
        linked_author_name=data.get("linked_author_name"),
        additional_linked_authors=[
            LinkedAuthorEntry(**e) if isinstance(e, dict) else e
            for e in (data.get("additional_linked_authors") or [])
        ],
        name_aliases=data.get("name_aliases") or [],
        created_at=created_at,
    )


@router.get("", response_model=UserProfile)
async def get_profile(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> UserProfile:
    """
    Fetch the current user's profile from Firestore.
    If no document exists, a default profile is created and returned.
    """
    ref = db.collection("users").document(uid)
    snapshot = ref.get()

    if snapshot.exists:
        data = snapshot.to_dict() or {}
        return _doc_to_profile(uid, data)

    # First-time user: create a minimal default document.
    now = datetime.now(tz=timezone.utc)
    try:
        fb_user = firebase_auth.get_user(uid)
        user_email = fb_user.email or ""
    except Exception:
        user_email = ""
    default_data: dict = {
        "uid": uid,
        "email": user_email,
        "notification_email": user_email,
        "notify_enabled": True,
        "created_at": now,
    }
    ref.set(default_data)
    logger.info("Created default profile for uid=%s", uid)
    return _doc_to_profile(uid, default_data)


@router.put("", response_model=UserProfile)
async def update_profile(
    body: UpdateProfileRequest,
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> UserProfile:
    """Update mutable fields of the current user's profile."""
    ref = db.collection("users").document(uid)

    # Only include fields that were explicitly provided (not None).
    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.notification_email is not None:
        updates["notification_email"] = body.notification_email
    if body.notify_enabled is not None:
        updates["notify_enabled"] = body.notify_enabled
    if body.notify_new_publications is not None:
        updates["notify_new_publications"] = body.notify_new_publications
    if body.scholar_url is not None:
        # Empty string means the user deliberately cleared the field.
        updates["scholar_url"] = body.scholar_url if body.scholar_url else firestore.DELETE_FIELD
    if body.name_aliases is not None:
        updates["name_aliases"] = body.name_aliases

    if updates:
        ref.set(updates, merge=True)
        logger.info("Updated profile for uid=%s: fields=%s", uid, list(updates.keys()))

    snapshot = ref.get()
    data = snapshot.to_dict() or {}
    return _doc_to_profile(uid, data)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> None:
    """
    Permanently delete the account.

    Cascade order:
      1. All notification documents in the notifications subcollection.
      2. All tracked work documents in the trackedWorks subcollection.
      3. The top-level users/{uid} profile document.
      4. The Firebase Authentication record (so the email can be re-used or the
         user simply cannot log in again).

    The endpoint returns 204 on success.  If the Firebase Auth deletion fails
    (e.g. the record was already removed), the error is logged but does NOT
    cause the endpoint to fail — all Firestore data has already been wiped.
    """
    from firebase_admin import auth as firebase_auth

    user_ref = db.collection("users").document(uid)

    # 1. Wipe notifications subcollection.
    for ndoc in user_ref.collection("notifications").stream():
        ndoc.reference.delete()

    # 2. Wipe trackedWorks subcollection.
    for wdoc in user_ref.collection("trackedWorks").stream():
        wdoc.reference.delete()

    # 3. Delete the profile document itself.
    user_ref.delete()

    # 4. Remove the Firebase Auth record so the user cannot sign in again.
    try:
        firebase_auth.delete_user(uid)
        logger.info("Deleted Firebase Auth record for uid=%s", uid)
    except Exception as exc:
        logger.error(
            "Could not delete Firebase Auth user %s (data already wiped): %s", uid, exc
        )

    logger.info("Account fully deleted for uid=%s", uid)


@router.delete("/linked-author", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_author(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> None:
    """
    Unlink the current author profile and delete all tracked works + notifications.
    This resets the account so the user can link a different author.
    """
    user_ref = db.collection("users").document(uid)

    # Delete all notifications first.
    for ndoc in user_ref.collection("notifications").stream():
        ndoc.reference.delete()

    # Delete all tracked works.
    for wdoc in user_ref.collection("trackedWorks").stream():
        wdoc.reference.delete()

    # Remove linked-author fields and aliases from the user document.
    user_ref.update({
        "linked_author_id": firestore.DELETE_FIELD,
        "linked_author_name": firestore.DELETE_FIELD,
        "additional_linked_authors": firestore.DELETE_FIELD,
        "name_aliases": firestore.DELETE_FIELD,
    })

    logger.info("Unlinked author and cleared all works/notifications for uid=%s", uid)


class UnsubscribeRequest(BaseModel):
    uid: str
    token: str


@router.post("/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe(
    body: UnsubscribeRequest,
    db: Any = Depends(get_db),
) -> dict:
    """
    One-click unsubscribe endpoint — no authentication required.

    Validates the HMAC token generated by email_service.make_unsubscribe_url(),
    then sets notify_enabled=False on the user's profile.
    """
    settings = get_settings()
    expected = hmac.new(
        key=settings.cron_secret.encode(),
        msg=f"unsubscribe:{body.uid}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(body.token, expected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired unsubscribe link.",
        )

    db.collection("users").document(body.uid).set(
        {"notify_enabled": False}, merge=True
    )
    logger.info("Unsubscribed uid=%s via one-click link.", body.uid)
    return {"message": "You have been unsubscribed from citation notifications."}
