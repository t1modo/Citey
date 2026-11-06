"""Keep API keys out of the logs.

OpenAlex takes its key as the ``api_key`` query parameter, and httpx logs the
full URL of every request at INFO, so the key ended up in the Vercel logs.
httpx's request lines are turned off, and any ``api_key=`` (or similar) that
still reaches a log line is replaced.
"""

import logging
import re

_SECRET_PARAM = re.compile(r"((?:api_key|apikey|token|key)=)[^&\s\"']+", re.IGNORECASE)


def redact(text: str) -> str:
    return _SECRET_PARAM.sub(r"\1[redacted]", text)


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


def install() -> None:
    """Quiet httpx's per-request lines and redact secrets on every handler."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, RedactSecrets) for f in handler.filters):
            handler.addFilter(RedactSecrets())
