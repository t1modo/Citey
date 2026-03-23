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

    try:
        verification_link = firebase_auth.generate_email_verification_link(fb_user.email)
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

    logger.info("Verification email sent to %s (uid=%s)", fb_user.email, uid)
