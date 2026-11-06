"""A small GET-with-retry helper shared by the newer citation source clients."""

import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 4
# A rate limit asking for longer than this means the budget is spent; the
# source counts as unavailable and the work is checked again the next night.
MAX_RETRY_WAIT = 60.0
# Indirection so tests can skip real waiting.
_sleep = asyncio.sleep


def _retry_after(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            try:
                when = parsedate_to_datetime(header)
                return max(0.0, (when - datetime.now(tz=timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return float(2 ** attempt)


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any] | None,
    source: str,
    context: str = "",
) -> httpx.Response | None:
    """
    GET *url*, retrying 429s, 5xx and network errors with backoff.

    Returns the response for any other status, the last 5xx response if the
    server never recovers, or ``None`` when every attempt was rate limited or
    failed at the network level.
    """
    response: httpx.Response | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.warning("%s request error [%s] (attempt %d/%d): %s",
                           source, context, attempt + 1, MAX_RETRIES, exc)
            response = None
            await _sleep(float(2 ** attempt))
            continue
        if response.status_code == 429:
            wait = _retry_after(response, attempt)
            if wait > MAX_RETRY_WAIT:
                logger.error("%s rate limited (429) [%s] with a %.0fs wait; giving up for now",
                             source, context, wait)
                return None
            logger.warning("%s rate limited (429) [%s]; waiting %.0fs (attempt %d/%d)",
                           source, context, wait, attempt + 1, MAX_RETRIES)
            response = None
            await _sleep(wait)
            continue
        if response.status_code >= 500:
            logger.warning("%s server error %s [%s] (attempt %d/%d)",
                           source, response.status_code, context, attempt + 1, MAX_RETRIES)
            await _sleep(float(2 ** attempt))
            continue
        return response
    logger.error("%s did not recover after %d attempts [%s]", source, MAX_RETRIES, context)
    return response
