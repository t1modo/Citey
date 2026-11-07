"""
Auth utilities — custom email verification delivered via Resend.

Firebase Admin SDK generates the verification link; Resend sends the email.
Firebase's own built-in verification email is never triggered.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin import auth as firebase_auth
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.core.concurrency import run_blocking
from app.core.db import get_session
from app.deps import enforce_cooldown, get_current_user
from app.services import user_service
from app.services.email_service import send_verification_email
from app.store import UserStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Minimum seconds between verification email sends for the same user.
_VERIFICATION_COOLDOWN = 60


@router.post("/send-verification", status_code=status.HTTP_204_NO_CONTENT)
async def send_email_verification(
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Generate a Firebase email verification link and deliver it via Resend.
    Safe to call on signup and for resend requests.
    """
    from datetime import datetime, timezone

    # Rate-limit: enforce cooldown between resend attempts.
    # Firebase Auth calls block, so each runs off the loop.
    enforce_cooldown(
        await user_service.user_data(session, uid),
        "last_verification_email_at", _VERIFICATION_COOLDOWN,
        "Verification email sent recently. Please wait before resending.",
    )

    try:
        fb_user = await run_blocking(firebase_auth.get_user, uid)
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
        verification_link = await run_blocking(
            firebase_auth.generate_email_verification_link,
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
    await user_service.ensure_user(session, uid)
    await UserStore(session).update_fields(uid, last_verification_email_at=now_utc)
    await session.commit()
    logger.info("Verification email sent to %s (uid=%s)", fb_user.email, uid)
