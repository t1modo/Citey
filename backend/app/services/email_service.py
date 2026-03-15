"""
Email delivery service using the Resend SDK.

Templates are Jinja2 HTML and plain-text files located in
``templates/email/``.
"""

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import Settings
from app.models import Notification

logger = logging.getLogger(__name__)

# Path to the templates directory (two levels up from this file).
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "email"


async def _send(params: resend.Emails.SendParams) -> dict:
    """Run the blocking resend.Emails.send() in a thread so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, partial(resend.Emails.send, params))
    return result


def _get_jinja_env() -> Environment:
    """Return a configured Jinja2 environment pointing at the email templates."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


async def send_citation_email(
    to_email: str,
    recipient_name: str,
    notifications: list[Notification],
    settings: Settings,
) -> None:
    """
    Render and send the citation notification email.

    Parameters
    ----------
    to_email:
        Recipient email address.
    recipient_name:
        Human-readable name used in the email greeting.
    notifications:
        List of new Notification objects to include in the email body.
    settings:
        Application settings (used for API key, from address, etc.).
    """
    resend.api_key = settings.resend_api_key

    env = _get_jinja_env()
    context = {
        "app_name": settings.app_name,
        "app_url": settings.app_url,
        "support_email": settings.support_email,
        "recipient_name": recipient_name,
        "notifications": notifications,
        "notification_count": len(notifications),
        "current_year": datetime.now(tz=timezone.utc).year,
    }

    html_template = env.get_template("citation.html")
    text_template = env.get_template("citation.txt")

    html_body = html_template.render(**context)
    text_body = text_template.render(**context)

    subject = (
        f"[{settings.app_name}] {len(notifications)} "
        f"new citation{'s' if len(notifications) != 1 else ''} for your work"
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
        "Citation email sent to %s — Resend ID: %s",
        to_email,
        result.get("id", "<unknown>"),
    )


async def send_digest_email(
    to_email: str,
    recipient_name: str,
    citation_groups: list[dict],
    total_citations: int,
    digest_date: datetime,
    settings: Settings,
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
    }

    html_template = env.get_template("digest.html")
    text_template = env.get_template("digest.txt")

    html_body = html_template.render(**context)
    text_body = text_template.render(**context)

    subject = (
        f"[{settings.app_name}] Your Citation Digest — {date_str} "
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
    subject = f"{settings.app_name} — Email Notifications Confirmed"
    html_body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width,initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background-color:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <div style="padding:40px 16px;">
    <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
      <div style="background:linear-gradient(135deg,#0d9488 0%,#4f46e5 100%);padding:36px 48px;">
        <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">{settings.app_name}<span style="color:rgba(255,255,255,0.6);">.</span></div>
        <div style="font-size:12px;font-weight:500;color:rgba(255,255,255,0.65);text-transform:uppercase;letter-spacing:0.1em;margin-top:5px;">Citation Intelligence</div>
      </div>
      <div style="padding:40px 48px 36px;">
        <p style="font-size:17px;font-weight:600;color:#1e2530;margin:0 0 8px;">Notifications are active, {recipient_name}</p>
        <p style="font-size:14px;color:#5a6478;margin:0 0 24px;line-height:1.7;">
          This is a confirmation that your email notification settings are working correctly.
          You will receive an alert like this whenever new citations are detected for your tracked publications.
        </p>
        <p style="font-size:14px;color:#5a6478;margin:0 0 32px;line-height:1.7;">
          To manage your preferences or review your tracked works, visit your dashboard.
        </p>
        <a href="{settings.app_url}/dashboard" style="display:inline-block;background:linear-gradient(135deg,#0d9488 0%,#4f46e5 100%);color:#ffffff;text-decoration:none;padding:13px 30px;border-radius:7px;font-weight:600;font-size:14px;">Go to Dashboard</a>
      </div>
      <div style="background:#f4f6f9;border-top:1px solid #e8ecf2;padding:24px 48px;text-align:center;font-size:11px;color:#9aa3b5;line-height:2;">
        &copy; {settings.app_name} &middot; <a href="mailto:{settings.support_email}" style="color:#7b849a;">{settings.support_email}</a><br />
        <a href="{settings.app_url}/settings" style="color:#7b849a;">Manage notification preferences</a>
      </div>
    </div>
  </div>
</body></html>"""
    text_body = (
        f"{settings.app_name} — Email Notifications Confirmed\n"
        f"{'=' * 60}\n\n"
        f"Dear {recipient_name},\n\n"
        f"This is a confirmation that your email notification settings are\n"
        f"working correctly. You will receive an alert whenever new citations\n"
        f"are detected for your tracked publications.\n\n"
        f"Dashboard: {settings.app_url}/dashboard\n"
        f"Settings:  {settings.app_url}/settings\n\n"
        f"— {settings.app_name}\n"
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
