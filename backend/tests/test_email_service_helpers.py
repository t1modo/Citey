"""
Tests for pure helper logic in app.services.email_service.

Covers:
  - make_unsubscribe_url — HMAC token generation, URL structure, determinism.

No HTTP calls, no Resend SDK, no Firebase required.
"""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

from app.services.email_service import make_unsubscribe_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(*, app_url: str = "https://citey.app", cron_secret: str = "test-secret") -> MagicMock:
    s = MagicMock()
    s.app_url = app_url
    s.cron_secret = cron_secret
    return s


def _expected_token(uid: str, secret: str) -> str:
    return hmac.new(
        key=secret.encode(),
        msg=f"unsubscribe:{uid}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# URL structure
# ---------------------------------------------------------------------------


def test_url_starts_with_app_url() -> None:
    url = make_unsubscribe_url("uid123", _make_settings())
    assert url.startswith("https://citey.app/unsubscribe")


def test_url_contains_uid_param() -> None:
    url = make_unsubscribe_url("uid123", _make_settings())
    qs = parse_qs(urlparse(url).query)
    assert qs["uid"] == ["uid123"]


def test_url_contains_token_param() -> None:
    url = make_unsubscribe_url("uid123", _make_settings())
    qs = parse_qs(urlparse(url).query)
    assert "token" in qs
    assert len(qs["token"][0]) == 64  # SHA-256 hex digest is 64 chars


def test_url_path_is_unsubscribe() -> None:
    url = make_unsubscribe_url("abc", _make_settings())
    assert urlparse(url).path == "/unsubscribe"


# ---------------------------------------------------------------------------
# HMAC correctness
# ---------------------------------------------------------------------------


def test_token_matches_expected_hmac() -> None:
    uid = "user_xyz_789"
    secret = "my-cron-secret"
    url = make_unsubscribe_url(uid, _make_settings(cron_secret=secret))
    qs = parse_qs(urlparse(url).query)
    actual_token = qs["token"][0]
    assert actual_token == _expected_token(uid, secret)


def test_different_uids_produce_different_tokens() -> None:
    settings = _make_settings()
    url_a = make_unsubscribe_url("user_a", settings)
    url_b = make_unsubscribe_url("user_b", settings)
    token_a = parse_qs(urlparse(url_a).query)["token"][0]
    token_b = parse_qs(urlparse(url_b).query)["token"][0]
    assert token_a != token_b


def test_different_secrets_produce_different_tokens() -> None:
    url_a = make_unsubscribe_url("uid1", _make_settings(cron_secret="secret-a"))
    url_b = make_unsubscribe_url("uid1", _make_settings(cron_secret="secret-b"))
    token_a = parse_qs(urlparse(url_a).query)["token"][0]
    token_b = parse_qs(urlparse(url_b).query)["token"][0]
    assert token_a != token_b


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_inputs_always_produce_same_url() -> None:
    settings = _make_settings(cron_secret="stable-secret")
    url1 = make_unsubscribe_url("user_abc", settings)
    url2 = make_unsubscribe_url("user_abc", settings)
    assert url1 == url2


# ---------------------------------------------------------------------------
# App URL variation
# ---------------------------------------------------------------------------


def test_localhost_url() -> None:
    url = make_unsubscribe_url("uid", _make_settings(app_url="http://localhost:3000"))
    assert url.startswith("http://localhost:3000/unsubscribe")


def test_custom_domain_url() -> None:
    url = make_unsubscribe_url("uid", _make_settings(app_url="https://staging.citey.app"))
    assert url.startswith("https://staging.citey.app/unsubscribe")
