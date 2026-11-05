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


def _get_jinja_env() -> Environment:
    """Return a configured Jinja2 environment pointing at the email templates."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["safe_url"] = _safe_url
    return env


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
    Render and send the daily citation digest email.

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
        The UTC datetime for which the digest is being sent (used for the
        date header in the email).
    """
    resend.api_key = settings.resend_api_key

    env = _get_jinja_env()
    date_str = f"{digest_date.strftime('%B')} {digest_date.day}, {digest_date.year}"
    context = {
        "app_name": settings.app_name,
        "app_url": settings.app_url,
        "support_email": settings.support_email,
        "recipient_name": recipient_name,
        "citation_groups": citation_groups,
        "total_citations": total_citations,
        "total_papers": len(citation_groups),
        "digest_date": date_str,
        "current_year": digest_date.year,
        "unsubscribe_url": make_unsubscribe_url(uid, settings) if uid else "",
    }

    html_template = env.get_template("digest.html")
    text_template = env.get_template("digest.txt")

    html_body = html_template.render(**context)
    text_body = text_template.render(**context)

    subject = (
        f"[{settings.app_name}] Your Citation Digest, {date_str} "
        f"({total_citations} new citation{'s' if total_citations != 1 else ''})"
    )

    from_address = f"{settings.email_from_name} <{settings.email_from_address}>"

    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    result = await _send(params)
    logger.info(
        "Digest email sent to %s — Resend ID: %s",
        to_email,
        result.get("id", "<unknown>"),
    )


async def send_verification_email(
    to_email: str,
    verification_link: str,
    settings: Settings,
) -> None:
    """Send a custom email verification email via Resend."""
    resend.api_key = settings.resend_api_key

    from_address = f"{settings.email_from_name} <{settings.email_from_address}>"
    subject = f"Verify your email address for {settings.app_name}"

    # Escape everything interpolated into HTML.
    link_html = html.escape(verification_link, quote=True)
    app_name_html = html.escape(settings.app_name)

    html_body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width,initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background-color:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <div style="padding:40px 16px;">
    <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
      <div style="background:linear-gradient(160deg,#0f0f14 0%,#1c1c28 100%);padding:36px 48px;">
        <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">{app_name_html}<span style="color:rgba(255,255,255,0.35);">.</span></div>
        <div style="font-size:12px;font-weight:500;color:#ffffff;text-transform:uppercase;letter-spacing:0.1em;margin-top:5px;">Citation Tracking</div>
      </div>
      <div style="padding:40px 48px 36px;">
        <p style="font-size:17px;font-weight:600;color:#1a1d23;margin:0 0 8px;">Verify your email address</p>
        <p style="font-size:14px;color:#4b5563;margin:0 0 24px;line-height:1.7;">
          Thanks for signing up. Click the button below to verify your email address and activate your account.
        </p>
        <a href="{link_html}" style="display:inline-block;background-color:#111111;color:#ffffff;text-decoration:none;padding:13px 30px;border-radius:7px;font-weight:600;font-size:14px;">Verify Email</a>
        <p style="font-size:13px;color:#9ca3af;margin:28px 0 0;line-height:1.7;">
          If the button does not work, paste this link into your browser:<br />
          <a href="{link_html}" style="color:#374151;word-break:break-all;">{link_html}</a>
        </p>
        <p style="font-size:13px;color:#9ca3af;margin:16px 0 0;line-height:1.7;">
          If you did not create a {app_name_html} account, you can safely ignore this email.
        </p>
      </div>
      <div style="background:#f8f9fb;border-top:1px solid #e8ecf2;padding:24px 48px;font-size:11px;color:#9ca3af;line-height:2;">
        Best regards,<br />
        <strong style="color:#4b5563;">{app_name_html} Team</strong><br />
        <a href="mailto:{settings.support_email}" style="color:#6b7280;">{settings.support_email}</a>
      </div>
    </div>
  </div>
</body></html>"""

    text_body = (
        f"Verify your email address for {settings.app_name}\n"
        f"{'=' * 60}\n\n"
        f"Thanks for signing up. Please verify your email address by visiting the link below:\n\n"
        f"{verification_link}\n\n"
        f"If you didn't create a {settings.app_name} account, you can safely ignore this email.\n\n"
        f"Best regards,\n"
        f"{settings.app_name} Team\n"
        f"{settings.support_email}"
    )

    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    result = await _send(params)
    logger.info(
        "Verification email sent to %s — Resend ID: %s",
        to_email,
        result.get("id", "<unknown>"),
    )


async def send_new_publications_email(
    to_email: str,
    recipient_name: str,
    new_titles: list[str],
    settings: Settings,
    uid: str = "",
) -> None:
    """
    Render and send the new-publications notification email.

    Parameters
    ----------
    to_email:
        Recipient email address.
    recipient_name:
        Human-readable name used in the email greeting.
    new_titles:
        Titles of the newly auto-added publications.
    settings:
        Application settings.
    """
    resend.api_key = settings.resend_api_key

    env = _get_jinja_env()
    count = len(new_titles)
    context = {
        "app_name": settings.app_name,
        "app_url": settings.app_url,
        "support_email": settings.support_email,
        "recipient_name": recipient_name,
        "new_titles": new_titles,
        "count": count,
        "current_year": datetime.now(tz=timezone.utc).year,
        "unsubscribe_url": make_unsubscribe_url(uid, settings) if uid else "",
    }

    html_template = env.get_template("new_publications.html")
    text_template = env.get_template("new_publications.txt")

    html_body = html_template.render(**context)
    text_body = text_template.render(**context)

    subject = (
        f"[{settings.app_name}] {count} new publication{'s' if count != 1 else ''} "
        f"added to your tracking list"
    )

    from_address = f"{settings.email_from_name} <{settings.email_from_address}>"

    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    result = await _send(params)
    logger.info(
        "New-publications email sent to %s — Resend ID: %s",
        to_email,
        result.get("id", "<unknown>"),
    )


async def send_test_email(
    to_email: str,
    recipient_name: str,
    settings: Settings,
) -> None:
    """
    Send a simple test / connectivity email to *to_email*.
    Does not use a Jinja template — kept intentionally minimal.
    """
    resend.api_key = settings.resend_api_key

    from_address = f"{settings.email_from_name} <{settings.email_from_address}>"
    subject = f"{settings.app_name}: Email Notifications Confirmed"
    # recipient_name comes from the user editable display_name; escape it.
    name_html = html.escape(recipient_name)
    app_name_html = html.escape(settings.app_name)

    html_body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width,initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background-color:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <div style="padding:40px 16px;">
    <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
      <div style="background:linear-gradient(160deg,#0f0f14 0%,#1c1c28 100%);padding:36px 48px;">
        <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">{app_name_html}<span style="color:rgba(255,255,255,0.35);">.</span></div>
        <div style="font-size:12px;font-weight:500;color:#ffffff;text-transform:uppercase;letter-spacing:0.1em;margin-top:5px;">Citation Tracking</div>
      </div>
      <div style="padding:40px 48px 36px;">
        <p style="font-size:17px;font-weight:600;color:#1a1d23;margin:0 0 8px;">Notifications are active, {name_html}</p>
        <p style="font-size:14px;color:#4b5563;margin:0 0 24px;line-height:1.7;">
          This is a confirmation that your email notification settings are working correctly.
          You will receive an alert like this whenever new citations are detected for your tracked publications.
        </p>
        <p style="font-size:14px;color:#4b5563;margin:0 0 32px;line-height:1.7;">
          To manage your preferences or review your tracked works, visit your dashboard.
        </p>
        <a href="{settings.app_url}/dashboard" style="display:inline-block;background-color:#111111;color:#ffffff;text-decoration:none;padding:13px 30px;border-radius:7px;font-weight:600;font-size:14px;">Go to Dashboard</a>
      </div>
      <div style="background:#f8f9fb;border-top:1px solid #e8ecf2;padding:24px 48px;text-align:center;font-size:11px;color:#9ca3af;line-height:2;">
        &copy; {app_name_html} &middot; <a href="mailto:{settings.support_email}" style="color:#6b7280;">{settings.support_email}</a><br />
        <a href="{settings.app_url}/settings" style="color:#6b7280;">Manage notification preferences</a>
      </div>
    </div>
  </div>
</body></html>"""
    text_body = (
        f"{settings.app_name}: Email Notifications Confirmed\n"
        f"{'=' * 60}\n\n"
        f"Dear {recipient_name},\n\n"
        f"This is a confirmation that your email notification settings are\n"
        f"working correctly. You will receive an alert whenever new citations\n"
        f"are detected for your tracked publications.\n\n"
        f"Dashboard: {settings.app_url}/dashboard\n"
        f"Settings:  {settings.app_url}/settings\n\n"
        f"{settings.app_name}\n"
        f"{settings.support_email}"
    )

    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    result = await _send(params)
    logger.info(
        "Test email sent to %s — Resend ID: %s",
        to_email,
        result.get("id", "<unknown>"),
    )


async def send_notification_email_confirmation(
    to_email: str,
    confirm_url: str,
    settings: Settings,
) -> None:
    """Ask the owner of *to_email* to confirm it as a notification address."""
    resend.api_key = settings.resend_api_key
    app_name = html.escape(settings.app_name)
    link = html.escape(confirm_url, quote=True)
    html_body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /></head>
<body style="margin:0;padding:40px 16px;background:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:10px;padding:40px 48px;">
    <p style="font-size:17px;font-weight:600;color:#1a1d23;margin:0 0 12px;">Confirm your notification email</p>
    <p style="font-size:14px;color:#4b5563;line-height:1.7;margin:0 0 24px;">
      Someone asked {app_name} to send citation alerts to this address. If that was you, confirm below.
    </p>
    <a href="{link}" style="display:inline-block;background:#111111;color:#ffffff;text-decoration:none;padding:13px 30px;border-radius:7px;font-weight:600;font-size:14px;">Confirm address</a>
    <p style="font-size:13px;color:#9ca3af;margin:28px 0 0;line-height:1.7;">
      If you didn't request this, ignore this email and nothing will be sent here.
    </p>
  </div>
</body></html>"""
    text_body = (
        f"Someone asked {settings.app_name} to send citation alerts to this address.\n\n"
        f"Confirm it here: {confirm_url}\n\n"
        "If you didn't request this, ignore this email."
    )
    await _send({
        "from": f"{settings.email_from_name} <{settings.email_from_address}>",
        "to": [to_email],
        "subject": f"Confirm your notification email for {settings.app_name}",
        "html": html_body,
        "text": text_body,
    })
