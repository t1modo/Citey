"""API keys never reach the logs."""

import logging

from app import log_redaction


def test_httpx_request_lines_are_off_after_startup():
    import app.main  # noqa: F401  (installs the logging setup)

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_api_key_in_a_url_is_redacted():
    line = 'GET https://api.openalex.org/works?api_key=HuZX94Yy&filter=cites%3AW1 "HTTP/1.1 200 OK"'
    out = log_redaction.redact(line)
    assert "HuZX94Yy" not in out
    assert "api_key=[redacted]&filter=cites%3AW1" in out


def test_filter_rewrites_formatted_records():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "url=%s", ("https://a.b/?api_key=s3cret",), None)
    log_redaction.RedactSecrets().filter(record)
    assert "s3cret" not in record.getMessage()
    assert "api_key=[redacted]" in record.getMessage()


def test_ordinary_lines_are_untouched():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "Checked %d paper(s)", (3,), None)
    log_redaction.RedactSecrets().filter(record)
    assert record.getMessage() == "Checked 3 paper(s)"
