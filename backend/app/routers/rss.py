"""
RSS/Atom feed router.

Provides two endpoints:

  GET /rss/url          — authenticated; returns the current user's signed feed URL.
  GET /rss/{uid}        — public; token-authenticated Atom feed of recent citations.

The token is HMAC-SHA256(CRON_SECRET, "rss:<uid>"), so no database lookup is
needed and the URL stays valid until CRON_SECRET rotates.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.config import get_settings
from app.deps import get_current_user
from app.firebase_client import get_db
from app.services.email_service import make_rss_url, verify_signed_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rss", tags=["rss"])

_FEED_LIMIT = 100  # max entries in the feed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _esc(s: str) -> str:
    """XML-escape a string for safe embedding in Atom elements."""
    return html.escape(s, quote=True)


def _rfc3339(dt: datetime | None) -> str:
    """Format *dt* as an RFC 3339 timestamp string required by Atom."""
    if dt is None:
        dt = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _doc_to_dict(doc_id: str, data: dict) -> dict:
    """Minimal conversion of a Firestore notification document to a plain dict."""

    def _to_dt(val: Any) -> datetime | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if hasattr(val, "timestamp"):
            ts = val.timestamp()
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        return None

    return {
        "id": doc_id,
        "cited_work_title": data.get("cited_work_title", ""),
        "citing_work_title": data.get("citing_work_title", ""),
        "citing_work_doi": data.get("citing_work_doi"),
        "citing_work_url": data.get("citing_work_url"),
        "citing_authors": data.get("citing_authors", []),
        "citing_year": data.get("citing_year"),
        "citing_publication_date": data.get("citing_publication_date"),
        "created_at": _to_dt(data.get("created_at")),
    }


def _build_atom_feed(uid: str, notifications: list[dict], feed_url: str) -> str:
    """Render an Atom 1.0 feed from a list of notification dicts."""
    updated = _rfc3339(
        notifications[0]["created_at"] if notifications else None
    )

    entries: list[str] = []
    for n in notifications:
        title = _esc(n["citing_work_title"] or "Untitled")
        cited = _esc(n["cited_work_title"] or "")
        authors = ", ".join(n["citing_authors"][:5]) if n["citing_authors"] else "Unknown"
        if len(n["citing_authors"]) > 5:
            authors += f" +{len(n['citing_authors']) - 5} more"

        doi = n.get("citing_work_doi")
        link_url = (
            f"https://doi.org/{doi}" if doi else n.get("citing_work_url") or ""
        )
        entry_id = f"citey:notification:{_esc(n['id'])}"
        entry_updated = _rfc3339(n["created_at"])

        summary_parts = [f"Cited your paper: {cited}"]
        if authors != "Unknown":
            summary_parts.append(f"Authors: {_esc(authors)}")
        if n.get("citing_year"):
            summary_parts.append(f"Year: {n['citing_year']}")
        summary = " | ".join(summary_parts)

        link_el = (
            f'      <link href="{_esc(link_url)}" />\n' if link_url else ""
        )

        entries.append(
            f"  <entry>\n"
            f"    <id>{entry_id}</id>\n"
            f"    <title>{title}</title>\n"
            f"    <updated>{entry_updated}</updated>\n"
            f"{link_el}"
            f"    <summary>{_esc(summary)}</summary>\n"
            f"    <author><name>{_esc(authors)}</name></author>\n"
            f"  </entry>"
        )

    entries_xml = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <id>citey:rss:{_esc(uid)}</id>\n"
        f"  <title>Citey Citation Alerts</title>\n"
        f"  <subtitle>New papers citing your work</subtitle>\n"
        f'  <link rel="self" href="{_esc(feed_url)}" />\n'
        f"  <updated>{updated}</updated>\n"
        f"{entries_xml}\n"
        "</feed>\n"
    )


# ---------------------------------------------------------------------------
# Endpoints — NOTE: /url must be defined before /{uid} so FastAPI routes
# the literal path correctly before the dynamic wildcard.
# ---------------------------------------------------------------------------


@router.get("/url")
async def get_rss_url(
    request: Request,
    uid: str = Depends(get_current_user),
) -> dict:
    """
    Return the authenticated user's private RSS feed URL.
    The URL is signed with an HMAC token and can be pasted into any RSS reader.
    """
    settings = get_settings()
    url = make_rss_url(uid, str(request.base_url), settings)
    return {"url": url}


@router.get("/{uid}")
async def get_rss_feed(
    uid: str,
    request: Request,
    token: str = Query(..., description="HMAC token from the user's feed URL"),
    db: Any = Depends(get_db),
) -> Response:
    """
    Public Atom 1.0 feed of recent citation notifications for *uid*.
    Requires a valid HMAC token; no Firebase authentication needed so RSS
    readers can subscribe without managing OAuth credentials.
    """
    settings = get_settings()

    if not verify_signed_token("rss", uid, token, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired feed token.",
        )

    # Fetch notifications — include last 90 days so the feed is meaningful
    # but not unbounded.
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=90)

    docs = (
        db.collection("users")
        .document(uid)
        .collection("notifications")
        .stream()
    )
    notifications = [_doc_to_dict(doc.id, doc.to_dict() or {}) for doc in docs]

    # Filter to last 90 days and sort newest-first.
    notifications = [
        n for n in notifications
        if n["created_at"] is None or n["created_at"] >= cutoff
    ]
    notifications.sort(
        key=lambda n: n["created_at"] or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )
    notifications = notifications[:_FEED_LIMIT]

    feed_url = str(request.url)
    body = _build_atom_feed(uid, notifications, feed_url)

    return Response(
        content=body,
        media_type="application/atom+xml; charset=utf-8",
    )
