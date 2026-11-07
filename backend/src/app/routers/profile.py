import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.concurrency import run_blocking
from app.firebase_client import ensure_firebase
from app.core.db import get_session
from app.deps import get_current_user
from app.schemas import LinkedAuthorEntry, UpdateProfileRequest, UserProfile
from app.services import convert, tracking_service, user_service
from app.store import UserStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


def _doc_to_profile(uid: str, data: dict) -> UserProfile:
    """Convert a raw Firestore document dict to a UserProfile."""
    created_at = data.get("created_at")
    if hasattr(created_at, "timestamp"):
        # Firestore DatetimeWithNanoseconds → Python datetime
        created_at = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at

    from app.services.email_service import resolve_recipient

    custom = (data.get("notification_email") or "").strip()
    pending = bool(custom) and resolve_recipient(data) != custom

    return UserProfile(
        uid=uid,
        email=data.get("email", ""),
        display_name=data.get("display_name"),
        notification_email=data.get("notification_email"),
        notification_email_pending=pending,
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
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    """The current user's profile, created with their sign-in email the first time."""
    user = await user_service.ensure_user(session, uid)
    await session.commit()
    return _doc_to_profile(uid, convert.user_data(user))


# Saving settings resends the link while the address is unconfirmed; this
# cooldown keeps repeated saves from spamming the inbox.
_CONFIRM_EMAIL_COOLDOWN = 300


@router.put("", response_model=UserProfile)
async def update_profile(
    body: UpdateProfileRequest,
    request: Request,
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    """Update mutable fields of the current user's profile.

    Changing notification_email to an address other than the account email
    sends a confirmation link; alerts keep going to the account email until
    the new address is confirmed.
    """
    store = UserStore(session)
    current = convert.user_data(await user_service.ensure_user(session, uid))

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
        updates["scholar_url"] = body.scholar_url or None
    if body.name_aliases is not None:
        updates["name_aliases"] = body.name_aliases

    new_email = (body.notification_email or "").strip()
    needs_confirmation = (
        body.notification_email is not None
        and new_email
        and new_email.lower() != (current.get("email") or "").lower()
        and new_email.lower() != (current.get("verified_notification_email") or "").lower()
    )

    if updates:
        await store.update_fields(uid, **updates)
        logger.info("Updated profile for uid=%s: fields=%s", uid, list(updates.keys()))

    if needs_confirmation:
        await _send_confirmation(store, uid, new_email, current, request)

    await session.commit()
    user = await store.get(uid)
    assert user is not None
    return _doc_to_profile(uid, convert.user_data(await store.refresh(user)))


async def _send_confirmation(store: UserStore, uid: str, email: str, current: dict, request: Request) -> None:
    """Email a confirmation link for a new notification address (best effort)."""
    from app.services.email_service import (
        make_confirm_email_url,
        send_notification_email_confirmation,
    )

    now = datetime.now(tz=timezone.utc)
    last = current.get("last_confirm_email_at")
    if isinstance(last, datetime):
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last).total_seconds() < _CONFIRM_EMAIL_COOLDOWN:
            logger.info("Confirmation email for uid=%s skipped (cooldown).", uid)
            return

    settings = get_settings()
    api_base = settings.api_url or str(request.base_url)
    try:
        await send_notification_email_confirmation(
            to_email=email,
            confirm_url=make_confirm_email_url(uid, email, api_base, settings),
            settings=settings,
        )
        await store.update_fields(uid, last_confirm_email_at=now)
        logger.info("Sent notification email confirmation for uid=%s", uid)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not send confirmation email for uid=%s: %s", uid, exc)


@router.get("/confirm-notification-email", include_in_schema=False)
async def confirm_notification_email(
    uid: str = Query(..., max_length=128),
    email: str = Query(..., max_length=254),
    token: str = Query(..., max_length=128),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Target of the link in the confirmation email; no login required."""
    from app.services.email_service import verify_signed_token

    settings = get_settings()
    ok = verify_signed_token(f"confirm_email:{email.lower()}", uid, token, settings)
    if ok:
        store = UserStore(session)
        if await store.get(uid) is not None:
            await store.update_fields(uid, verified_notification_email=email)
            await session.commit()
            logger.info("Confirmed notification email for uid=%s", uid)
        else:
            ok = False
    status_param = "confirmed" if ok else "invalid"
    return RedirectResponse(f"{settings.app_url}/settings?email={status_param}", status_code=303)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Permanently delete the account: the profile, what it tracks and its
    alerts (papers and citations stay for anyone else tracking them), then
    the Firebase Authentication record, so the user cannot sign in again.

    If the Firebase Auth deletion fails (e.g. the record was already
    removed), the error is logged but the endpoint still succeeds: the
    data has already been deleted.
    """
    await UserStore(session).delete_by_id(uid)
    await session.commit()

    try:
        ensure_firebase()
        await run_blocking(firebase_auth.delete_user, uid)
        logger.info("Deleted Firebase Auth record for uid=%s", uid)
    except Exception as exc:
        logger.error("Could not delete Firebase Auth user %s (data already wiped): %s", uid, exc)

    logger.info("Account fully deleted for uid=%s", uid)


@router.delete("/linked-author", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_author(
    uid: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Unlink the current author profile and stop tracking every paper (their
    alerts go too). This resets the account so the user can link a
    different author.
    """
    await tracking_service.reset_linked_author(session, uid)
    await session.commit()
    logger.info("Unlinked author and cleared all works/notifications for uid=%s", uid)


class UnsubscribeRequest(BaseModel):
    uid: str
    token: str


@router.post("/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe(
    body: UnsubscribeRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    One-click unsubscribe endpoint — no authentication required.

    Validates the HMAC token generated by email_service.make_unsubscribe_url(),
    then sets notify_enabled=False on the user's profile.
    """
    from app.services.email_service import verify_signed_token

    settings = get_settings()
    if not verify_signed_token("unsubscribe", body.uid, body.token, settings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired unsubscribe link.",
        )

    await UserStore(session).update_fields(body.uid, notify_enabled=False)
    await session.commit()
    logger.info("Unsubscribed uid=%s via one-click link.", body.uid)
    return {"message": "You have been unsubscribed from citation notifications."}
