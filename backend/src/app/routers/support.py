"""
Contact form: the only public way to reach support.

A published email address cannot be rate limited, so the site sends people
here instead. Each message is emailed to SUPPORT_INBOX (or SUPPORT_EMAIL when
that is unset) with Reply-To set to the sender. Limits live in Firestore so they survive restarts:

* per connection: 3 messages per hour
* per sender address: 3 messages per day
* site wide: 20 messages per day, so a scripted flood from many addresses
  still can't bury the inbox

Bots that fill the hidden ``website`` field, or submit faster than a person
can type, get a normal looking success and nothing is sent.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.core.concurrency import run_blocking
from app.firebase_client import get_db, verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_optional_bearer = HTTPBearer(auto_error=False)

PER_IP_PER_HOUR = 3
PER_EMAIL_PER_DAY = 3
SITE_PER_DAY = 20
MIN_FILL_MS = 3000

_LIMITS_COLLECTION = "supportLimits"


class SupportMessage(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    email: str = Field(..., max_length=254)
    subject: Optional[str] = Field(default=None, max_length=150)
    message: str = Field(..., min_length=10, max_length=5000)
    # Hidden from people; bots fill it in.
    website: Optional[str] = Field(default=None, max_length=200)
    # Milliseconds between the form loading and being sent.
    elapsed_ms: int = Field(default=0, ge=0)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address so we can reply.")
        return v

    @field_validator("name", "subject")
    @classmethod
    def _single_line(cls, v: Optional[str]) -> Optional[str]:
        # No line breaks: these go into an email subject and display name.
        return " ".join(v.split()) if v else v


def _client_ip(request: Request) -> str:
    """The caller's address, as the hosting proxy reports it."""
    if os.environ.get("VERCEL"):
        # Vercel overwrites X-Forwarded-For with the client's address and
        # passes other headers through untouched, so a client could set
        # CF-Connecting-IP itself to dodge the per-address limit.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # The proxy appends the address it saw; the rightmost one is not
        # client supplied.
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _hash(settings: Settings, value: str) -> str:
    """Store limits under a keyed hash, never the raw IP or email."""
    secret = (settings.token_secret or settings.cron_secret or "citey").encode()
    return hmac.new(secret, value.lower().encode(), hashlib.sha256).hexdigest()[:32]


def _take(db: Any, key: str, limit: int, window_seconds: int, now: datetime) -> bool:
    """Count one use of *key*; False when it is already at *limit* in the window."""
    ref = db.collection(_LIMITS_COLLECTION).document(key)
    snap = ref.get()
    data = snap.to_dict() if snap.exists else {}
    start = data.get("window_start")
    if isinstance(start, datetime) and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if not isinstance(start, datetime) or (now - start).total_seconds() >= window_seconds:
        ref.set({"window_start": now, "count": 1})
        return True
    count = int(data.get("count") or 0)
    if count >= limit:
        return False
    ref.update({"count": count + 1})
    return True


async def _optional_uid(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if not credentials or not credentials.credentials:
        return None
    try:
        decoded = await run_blocking(verify_token, credentials.credentials)
        return decoded.get("uid") or decoded.get("user_id")
    except Exception:  # noqa: BLE001  (signed out senders are welcome too)
        return None


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def send_support_message(
    body: SupportMessage,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    accepted = {"message": "Thanks. We'll reply to your email."}

    if body.website or body.elapsed_ms < MIN_FILL_MS:
        logger.info("Support form: dropped a likely bot submission.")
        return accepted

    now = datetime.now(tz=timezone.utc)
    ip_key = f"ip_{_hash(settings, _client_ip(request))}"
    email_key = f"email_{_hash(settings, body.email)}"
    day_key = f"site_{now.strftime('%Y%m%d')}"

    too_many = HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="You've sent several messages recently. Please try again later.",
    )
    # The limits live in Firestore, whose client blocks: off the loop.
    if not await run_blocking(_take, db, ip_key, PER_IP_PER_HOUR, 3600, now):
        raise too_many
    if not await run_blocking(_take, db, email_key, PER_EMAIL_PER_DAY, 86400, now):
        raise too_many
    if not await run_blocking(_take, db, day_key, SITE_PER_DAY, 86400, now):
        logger.warning("Support form: site wide daily limit reached.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The contact form is busy today. Please try again tomorrow.",
        )

    from app.services.email_service import send_support_message as deliver

    try:
        await deliver(
            sender_email=body.email,
            sender_name=body.name or "",
            subject=body.subject or "",
            message=body.message,
            uid=await _optional_uid(credentials),
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Support form: could not deliver message: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't send your message right now. Please try again in a few minutes.",
        ) from exc
    return accepted
