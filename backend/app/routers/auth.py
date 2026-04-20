"""
Auth utilities — custom email verification delivered via Resend.

Firebase Admin SDK generates the verification link; Resend sends the email.
Firebase's own built-in verification email is never triggered.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin import auth as firebase_auth

from app.config import Settings, get_settings
from app.deps import get_current_user
from app.firebase_client import get_db
from app.services.email_service import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Minimum seconds between verification email sends for the same user.
_VERIFICATION_COOLDOWN = 60


@router.post("/send-verification", status_code=status.HTTP_204_NO_CONTENT)
async def send_email_verification(
    uid: str = Depends(get_current_user),
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Generate a Firebase email verification link and deliver it via Resend.
    Safe to call on signup and for resend requests.
    """
    from datetime import datetime, timezone

    # Rate-limit: enforce cooldown between resend attempts.
    user_ref = db.collection("users").document(uid)
    user_snap = user_ref.get()
    if user_snap.exists:
        user_data = user_snap.to_dict() or {}
        last_sent = user_data.get("last_verification_email_at")
        if isinstance(last_sent, datetime):
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            elapsed = (now - last_sent).total_seconds()
            retry_after = int(_VERIFICATION_COOLDOWN - elapsed)
            if retry_after > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "Verification email sent recently. Please wait before resending.",
                        "retry_after_seconds": retry_after,
                    },
                )

    try:
        fb_user = firebase_auth.get_user(uid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from exc

    if fb_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified.",
        )

    if not fb_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address on file.",
        )

    action_code_settings = firebase_auth.ActionCodeSettings(
        url=f"{settings.app_url}/dashboard",
    )

    try:
        verification_link = firebase_auth.generate_email_verification_link(
            fb_user.email,
            action_code_settings=action_code_settings,
        )
    except Exception as exc:
        logger.error("Failed to generate verification link for uid=%s: %s", uid, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate verification link.",
        ) from exc

    try:
        await send_verification_email(
            to_email=fb_user.email,
            verification_link=verification_link,
            settings=settings,
        )
    except Exception as exc:
        logger.error(
            "Failed to send verification email to %s (uid=%s): %s",
            fb_user.email, uid, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not send verification email.",
        ) from exc

    # Stamp the send time so the cooldown check above works on subsequent calls.
    now_utc = datetime.now(tz=timezone.utc)
    user_ref.set({"last_verification_email_at": now_utc}, merge=True)
    logger.info("Verification email sent to %s (uid=%s)", fb_user.email, uid)
