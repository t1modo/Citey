"""
Email delivery service using the Resend SDK.

Templates are Jinja2 HTML and plain-text files located in
``templates/email/``.
"""

import asyncio
import hashlib
import hmac
import html
import logging
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from urllib.parse import urlencode

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import Settings

logger = logging.getLogger(__name__)

# Path to the templates directory (two levels up from this file).
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "email"


async def _send(params: resend.Emails.SendParams) -> dict:
    """Run the blocking resend.Emails.send() in a thread so it doesn't block the event loop."""
    return await asyncio.to_thread(partial(resend.Emails.send, params))


def _hmac_hex(secret: str, purpose: str, uid: str) -> str:
    return hmac.new(
        key=secret.encode(),
        msg=f"{purpose}:{uid}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


def _make_signed_token(purpose: str, uid: str, settings: Settings) -> str:
    """Return an HMAC-SHA256 hex token for the given purpose + uid pair."""
    return _hmac_hex(settings.token_secret or settings.cron_secret, purpose, uid)


def verify_signed_token(purpose: str, uid: str, token: str, settings: Settings) -> bool:
    """Return True if *token* is the valid HMAC for *purpose* + *uid*.

    Tokens signed with the legacy cron_secret are still accepted so links in
    emails sent before token_secret was configured keep working. Nothing
    signed with the insecure default secret is ever accepted outside local dev.
    """
    secrets = [settings.token_secret, settings.cron_secret]
    for secret in secrets:
        if not secret:
            continue
        if secret == "changeme" and not settings.is_local:
            continue
        if hmac.compare_digest(_hmac_hex(secret, purpose, uid), token):
            return True
    return False


def resolve_recipient(user_data: dict) -> str | None:
    """Return the address Citey may email for this user.

    A custom notification_email is only used once its owner has confirmed it
    (verified_notification_email matches). Until then mail goes to the account
    email, so nobody can point Citey's mail at an address they don't control.
    """
    account = (user_data.get("email") or "").strip()
    custom = (user_data.get("notification_email") or "").strip()
    if not custom or custom.lower() == account.lower():
        return account or custom or None
    verified = (user_data.get("verified_notification_email") or "").strip().lower()
    if verified == custom.lower():
        return custom
    return account or None


def make_confirm_email_url(uid: str, email: str, api_base_url: str, settings: Settings) -> str:
    """Signed link that confirms *email* as *uid*'s notification address."""
    token = _make_signed_token(f"confirm_email:{email.lower()}", uid, settings)
    qs = urlencode({"uid": uid, "email": email, "token": token})
    return f"{api_base_url.rstrip('/')}/profile/confirm-notification-email?{qs}"


def make_unsubscribe_url(uid: str, settings: Settings) -> str:
    """Return a signed, stateless one-click unsubscribe URL for *uid*."""
    token = _make_signed_token("unsubscribe", uid, settings)
    qs = urlencode({"uid": uid, "token": token})
    return f"{settings.app_url}/unsubscribe?{qs}"


def make_rss_url(uid: str, api_base_url: str, settings: Settings) -> str:
    """Return a signed, shareable RSS/Atom feed URL for *uid*.

    *api_base_url* should be the backend's base URL (e.g. from ``request.base_url``),
    so the link is correct in both local dev and production.
    """
    token = _make_signed_token("rss", uid, settings)
    return f"{api_base_url.rstrip('/')}/rss/{uid}?token={token}"


def _safe_url(value: object) -> str:
    """Only allow http(s) links from upstream APIs into email hrefs."""
    url = str(value or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else "#"


def _author_line(names: object, limit: int = 3, rest: str = "others") -> str:
    """"A, B and C" for short lists, "A, B, C and 4 others" for long ones."""
    items = [str(n).strip() for n in (names or []) if str(n or "").strip()]  # type: ignore[union-attr]
    if not items:
        return ""
    if len(items) <= limit:
        return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
    extra = len(items) - limit
    noun = rest if extra != 1 and rest == "others" else ("other" if rest == "others" else rest)
    return f"{', '.join(items[:limit])} and {extra} {noun}"


def _nice_date(value: object) -> str:
    """2026-10-30 becomes "October 30, 2026"; anything else passes through."""
    text = str(value or "")
    try:
        d = datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return text
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _greeting_name(name: str | None) -> str:
    """A name worth greeting by; an email address used as a fallback is not."""
    name = (name or "").strip()
    return "" if "@" in name else name


def _get_jinja_env() -> Environment:
    """Return a configured Jinja2 environment pointing at the email templates."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["safe_url"] = _safe_url
    env.filters["author_line"] = _author_line
    env.filters["nice_date"] = _nice_date
    return env


def _base_context(settings: Settings) -> dict:
    return {
        "app_name": settings.app_name,
        "app_url": settings.app_url,
        "support_email": settings.support_email,
        "current_year": datetime.now(tz=timezone.utc).year,
        "unsubscribe_url": "",
        "recipient_name": "",
    }


def _render(name: str, context: dict) -> tuple[str, str]:
    """Render ``name.html`` and ``name.txt`` with *context*."""
    env = _get_jinja_env()
    return (
        env.get_template(f"{name}.html").render(**context),
        env.get_template(f"{name}.txt").render(**context),
    )


async def _deliver(settings: Settings, to_email: str, subject: str, html_body: str, text_body: str, kind: str) -> None:
    resend.api_key = settings.resend_api_key
    params: resend.Emails.SendParams = {
        "from": f"{settings.email_from_name} <{settings.email_from_address}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    result = await _send(params)
    logger.info("%s email sent to %s, Resend ID: %s", kind, to_email, result.get("id", "<unknown>"))


def digest_subject(total_citations: int) -> str:
    if total_citations == 1:
        return "A new paper cites your work"
    return f"{total_citations} new papers cite your work"


async def send_digest_email(
    to_email: str,
    recipient_name: str,
    citation_groups: list[dict],
    total_citations: int,
    digest_date: datetime,
    settings: Settings,
    uid: str = "",
) -> None:
    """
    Render and send the citation digest email.

    Parameters
    ----------
    citation_groups:
        List of dicts, each with keys:
          - cited_work_title (str)
          - cited_work_doi (str | None)
          - citations (list[Notification])
    total_citations:
        Total number of citing papers across all groups.
    digest_date:
        The UTC datetime the citations were found.
    """
    context = {
        **_base_context(settings),
        "recipient_name": _greeting_name(recipient_name),
        "citation_groups": citation_groups,
        "total_citations": total_citations,
        "total_papers": len(citation_groups),
        "digest_date": f"{digest_date.strftime('%B')} {digest_date.day}, {digest_date.year}",
        "current_year": digest_date.year,
        "unsubscribe_url": make_unsubscribe_url(uid, settings) if uid else "",
    }
    html_body, text_body = _render("digest", context)
    await _deliver(settings, to_email, digest_subject(total_citations), html_body, text_body, "Digest")


async def send_verification_email(
    to_email: str,
    verification_link: str,
    settings: Settings,
) -> None:
    """Send the sign-up email verification message."""
    html_body, text_body = _render("verify", {**_base_context(settings), "link": verification_link})
    await _deliver(
        settings, to_email, f"Confirm your email for {settings.app_name}", html_body, text_body, "Verification",
    )


async def send_new_publications_email(
    to_email: str,
    recipient_name: str,
    new_titles: list[str],
    settings: Settings,
    uid: str = "",
) -> None:
    """Tell a user that new papers from their author profile were added."""
    count = len(new_titles)
    context = {
        **_base_context(settings),
        "recipient_name": _greeting_name(recipient_name),
        "new_titles": new_titles,
        "count": count,
        "unsubscribe_url": make_unsubscribe_url(uid, settings) if uid else "",
    }
    html_body, text_body = _render("new_publications", context)
    subject = f"{count} new paper{'s' if count != 1 else ''} added to your {settings.app_name} list"
    await _deliver(settings, to_email, subject, html_body, text_body, "New publications")


async def send_test_email(
    to_email: str,
    recipient_name: str,
    settings: Settings,
) -> None:
    """Send a short test email confirming alerts reach *to_email*."""
    context = {**_base_context(settings), "recipient_name": _greeting_name(recipient_name)}
    html_body, text_body = _render("test", context)
    await _deliver(
        settings, to_email, f"Your {settings.app_name} email alerts are on", html_body, text_body, "Test",
    )


async def send_notification_email_confirmation(
    to_email: str,
    confirm_url: str,
    settings: Settings,
) -> None:
    """Ask the owner of *to_email* to confirm it as a notification address."""
    html_body, text_body = _render("confirm_address", {**_base_context(settings), "link": confirm_url})
    await _deliver(
        settings, to_email, f"Confirm your alert address for {settings.app_name}", html_body, text_body,
        "Address confirmation",
    )


ANNOUNCEMENT_SUBJECT = "Citey has been rebuilt"


async def send_announcement_email(
    to_email: str,
    recipient_name: str,
    settings: Settings,
    uid: str = "",
) -> None:
    """Send the one off "Citey has been rebuilt" update to a user."""
    unsubscribe_url = make_unsubscribe_url(uid, settings) if uid else ""
    context = {
        **_base_context(settings),
        "recipient_name": _greeting_name(recipient_name),
        "unsubscribe_url": unsubscribe_url,
    }
    html_body, text_body = _render("announcement", context)
    resend.api_key = settings.resend_api_key
    params: resend.Emails.SendParams = {
        "from": f"{settings.email_from_name} <{settings.email_from_address}>",
        "to": [to_email],
        "subject": ANNOUNCEMENT_SUBJECT,
        "html": html_body,
        "text": text_body,
    }
    if unsubscribe_url:
        params["headers"] = {"List-Unsubscribe": f"<{unsubscribe_url}>"}
    result = await _send(params)
    logger.info("Announcement email sent to %s, Resend ID: %s", to_email, result.get("id", "<unknown>"))
