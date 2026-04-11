"""
Jobs router.

Two approaches to trigger the citation-check job:
  1. POST /jobs/run          — protected by X-Cron-Secret header (for cron/Cloud Scheduler)
  2. POST /jobs/run          — also accepts a valid Firebase Bearer token (for manual triggers)
  3. POST /jobs/email-test   — requires Firebase Bearer token
"""

import logging
from datetime import datetime, timezone
from typing import Any

# Minimum seconds between manual job triggers from the same user.
_MANUAL_CHECK_COOLDOWN = 600      # /jobs/run       — 10 minutes
_MANUAL_SYNC_COOLDOWN  = 600      # /jobs/sync-publications — 10 minutes
_EMAIL_TEST_COOLDOWN   = 300      # /jobs/email-test — 5 minutes

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.firebase_client import verify_token
from app.models import JobRunRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_bearer_scheme = HTTPBearer(auto_error=False)


async def _authorize_job_request(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Accept either:
    - A valid X-Cron-Secret header value, or
    - A valid Firebase Bearer token.

    Returns a string identity label (e.g. "cron" or the uid) for logging.
    Raises HTTP 401/403 if neither credential is valid.
    """
    # 1. Check cron secret first (cheap, no network call).
    if x_cron_secret is not None:
        if x_cron_secret == settings.cron_secret:
            return "cron"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid cron secret.",
        )

    # 2. Fall back to Firebase Bearer token.
    if credentials and credentials.credentials:
        try:
            decoded = verify_token(credentials.credentials)
            uid: str = decoded.get("uid") or decoded.get("user_id", "")
            if uid:
                return uid
        except Exception as exc:
            logger.warning("Token verification failed in job auth: %s", exc)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Provide a valid X-Cron-Secret header or a Firebase Bearer token "
            "to trigger this job."
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/run")
async def run_job(
    body: JobRunRequest,
    caller_id: str = Depends(_authorize_job_request),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Trigger the citation-check job.

    - When called via X-Cron-Secret (scheduled cron): checks all users.
    - When called via Firebase Bearer token (manual user trigger): checks only that user.

    Authorization: X-Cron-Secret header **or** Firebase Bearer token.
    """
    from app.firebase_client import get_db as _get_db
    from app.services import email_service as email_svc

    _db = _get_db()
    logger.info("Job /run triggered by caller_id=%s dry_run=%s", caller_id, body.dry_run)

    if caller_id == "cron":
        from app.services.citation_service import run_job_for_all_users
        summary = await run_job_for_all_users(
            db=_db,
            email_service=email_svc,
            dry_run=body.dry_run,
            settings=settings,
        )
    else:
        # Manual trigger by an authenticated user — scope to their papers only.
        from app.services.citation_service import run_job_for_user
        user_doc = _db.collection("users").document(caller_id).get()
        user_data: dict = user_doc.to_dict() or {} if user_doc.exists else {}

        # Rate-limit manual checks: reject if last check was within the cooldown window.
        now = datetime.now(tz=timezone.utc)
        last_check = user_data.get("last_manual_check_at")
        if last_check is not None:
            # Firestore timestamps arrive as datetime; plain strings are ignored.
            if isinstance(last_check, datetime):
                if last_check.tzinfo is None:
                    last_check = last_check.replace(tzinfo=timezone.utc)
                elapsed = (now - last_check).total_seconds()
                retry_after = int(_MANUAL_CHECK_COOLDOWN - elapsed)
                if retry_after > 0:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "message": "You've run a citation check recently. Please wait before trying again.",
                            "retry_after_seconds": retry_after,
                        },
                    )

        works_processed, new_notifications = await run_job_for_user(
            uid=caller_id,
            user_data=user_data,
            db=_db,
            email_service=email_svc,
            dry_run=body.dry_run,
            settings=settings,
        )
        if not body.dry_run:
            _db.collection("users").document(caller_id).set(
                {"last_manual_check_at": now}, merge=True
            )
        summary = {
            "users_processed": 1,
            "works_processed": works_processed,
            "new_notifications": new_notifications,
        }

    logger.info("Job complete: %s", summary)
    n = summary["new_notifications"]
    w = summary["works_processed"]
    if n > 0:
        summary["message"] = f"Found {n} new citation(s) across {w} paper(s)."
    else:
        summary["message"] = f"Checked {w} paper(s) — all citations already up to date."
    return summary


@router.post("/cleanup-notifications")
async def cleanup_notifications(
    body: JobRunRequest,
    caller_id: str = Depends(_authorize_job_request),
) -> dict:
    """
    Delete notification documents older than 30 days (by created_at).

    Authorization: X-Cron-Secret header **or** Firebase Bearer token.
    When called by an authenticated user, only cleans up their own notifications.
    """
    from app.firebase_client import get_db as _get_db
    from app.services.citation_service import cleanup_old_notifications, _NOTIFICATION_TTL_DAYS

    _db = _get_db()
    logger.info(
        "Job /cleanup-notifications triggered by caller_id=%s dry_run=%s",
        caller_id,
        body.dry_run,
    )

    if caller_id == "cron":
        summary = await cleanup_old_notifications(db=_db, dry_run=body.dry_run)
    else:
        # Scoped to the requesting user only.
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_NOTIFICATION_TTL_DAYS)
        notifs_ref = _db.collection("users").document(caller_id).collection("notifications")
        old_docs = list(notifs_ref.where("created_at", "<", cutoff).stream())
        if old_docs and not body.dry_run:
            batch = _db.batch()
            for doc in old_docs:
                batch.delete(doc.reference)
            batch.commit()
        count = len(old_docs)
        summary = {"users_processed": 1, "notifications_deleted": count}

    n = summary["notifications_deleted"]
    summary["message"] = (
        f"Deleted {n} notification(s) older than {_NOTIFICATION_TTL_DAYS} days."
        if n > 0
        else f"No notifications older than {_NOTIFICATION_TTL_DAYS} days found."
    )
    logger.info("Notification cleanup complete: %s", summary)
    return summary


@router.post("/sync-publications")
async def sync_publications(
    body: JobRunRequest,
    caller_id: str = Depends(_authorize_job_request),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Trigger the publication-sync job.

    Checks each linked OpenAlex author for new publications not yet in their
    trackedWorks collection, and auto-adds them.

    Authorization: X-Cron-Secret header **or** Firebase Bearer token.
    """
    from app.firebase_client import get_db as _get_db
    from app.services import email_service as email_svc
    from app.services.publication_sync import (
        sync_new_publications_for_all_users,
        sync_new_publications_for_user,
    )

    _db = _get_db()
    logger.info(
        "Job /sync-publications triggered by caller_id=%s dry_run=%s",
        caller_id,
        body.dry_run,
    )

    if caller_id == "cron":
        summary = await sync_new_publications_for_all_users(
            db=_db,
            email_service=email_svc,
            dry_run=body.dry_run,
            settings=settings,
        )
    else:
        user_doc = _db.collection("users").document(caller_id).get()
        user_data: dict = user_doc.to_dict() or {} if user_doc.exists else {}

        now = datetime.now(tz=timezone.utc)
        last_sync = user_data.get("last_manual_sync_at")
        if isinstance(last_sync, datetime):
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            elapsed = (now - last_sync).total_seconds()
            retry_after = int(_MANUAL_SYNC_COOLDOWN - elapsed)
            if retry_after > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "You've run a publication sync recently. Please wait before trying again.",
                        "retry_after_seconds": retry_after,
                    },
                )

        added = await sync_new_publications_for_user(
            uid=caller_id,
            user_data=user_data,
            db=_db,
            email_service=email_svc,
            dry_run=body.dry_run,
            settings=settings,
        )
        if not body.dry_run:
            _db.collection("users").document(caller_id).set(
                {"last_manual_sync_at": now}, merge=True
            )
        summary = {"users_processed": 1, "works_added": added}

    logger.info("Publication sync complete: %s", summary)
    n = summary["works_added"]
    summary["message"] = (
        f"Added {n} new publication(s)." if n > 0 else "No new publications found."
    )
    return summary


@router.post("/email-test")
async def email_test(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Send a test email to the authenticated user's notification_email."""
    # Verify token
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        decoded = verify_token(credentials.credentials)
        uid: str = decoded.get("uid") or decoded.get("user_id", "")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a valid user ID.",
        )

    from app.firebase_client import get_db as _get_db
    from app.services.email_service import send_test_email

    db = _get_db()
    user_ref = db.collection("users").document(uid)
    snapshot = user_ref.get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Create a profile first.",
        )

    data = snapshot.to_dict() or {}

    now = datetime.now(tz=timezone.utc)
    last_test = data.get("last_email_test_at")
    if isinstance(last_test, datetime):
        if last_test.tzinfo is None:
            last_test = last_test.replace(tzinfo=timezone.utc)
        elapsed = (now - last_test).total_seconds()
        retry_after = int(_EMAIL_TEST_COOLDOWN - elapsed)
        if retry_after > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "You've sent a test email recently. Please wait before trying again.",
                    "retry_after_seconds": retry_after,
                },
            )

    to_email: str | None = data.get("notification_email") or data.get("email")
    if not to_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No email address found on profile. Set a notification_email first.",
        )

    recipient_name: str = data.get("display_name") or to_email
    try:
        await send_test_email(
            to_email=to_email,
            recipient_name=recipient_name,
            settings=settings,
        )
    except Exception as exc:
        logger.error("Failed to send test email to %s: %s", to_email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email delivery failed: {exc}",
        ) from exc

    user_ref.set({"last_email_test_at": now}, merge=True)
    logger.info("Test email sent to %s for uid=%s", to_email, uid)
    return {"message": f"Test email sent to {to_email}."}
