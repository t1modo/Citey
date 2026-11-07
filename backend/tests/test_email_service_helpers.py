"""
Tests for pure helper logic in app.services.email_service.

Covers:
  - make_unsubscribe_url — HMAC token generation, URL structure, determinism.

No HTTP calls, no Resend SDK, no database required.
"""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse


from app.services.email_service import make_unsubscribe_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(*, app_url: str = "https://citey.app", cron_secret: str = "test-secret") -> MagicMock:
    s = MagicMock()
    s.app_url = app_url
    s.cron_secret = cron_secret
    s.token_secret = ""  # unset: falls back to cron_secret (legacy links)
    s.is_local = "localhost" in app_url
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


# ---------------------------------------------------------------------------
# Token secret separation
# ---------------------------------------------------------------------------


def test_token_secret_is_preferred_when_set() -> None:
    from app.services.email_service import verify_signed_token

    settings = _make_settings(cron_secret="cron")
    settings.token_secret = "tok"
    url = make_unsubscribe_url("u1", settings)
    token = parse_qs(urlparse(url).query)["token"][0]
    assert token == _expected_token("u1", "tok")
    assert verify_signed_token("unsubscribe", "u1", token, settings)


def test_legacy_cron_signed_links_still_verify() -> None:
    from app.services.email_service import verify_signed_token

    settings = _make_settings(cron_secret="cron")
    settings.token_secret = "tok"
    assert verify_signed_token("unsubscribe", "u1", _expected_token("u1", "cron"), settings)


def test_default_secret_never_verifies_in_production() -> None:
    from app.services.email_service import verify_signed_token

    settings = _make_settings(cron_secret="changeme")
    forged = _expected_token("victim", "changeme")
    assert not verify_signed_token("unsubscribe", "victim", forged, settings)


# ---------------------------------------------------------------------------
# resolve_recipient
# ---------------------------------------------------------------------------

from app.services.email_service import resolve_recipient  # noqa: E402


def test_recipient_defaults_to_account_email() -> None:
    assert resolve_recipient({"email": "a@x.org"}) == "a@x.org"


def test_unconfirmed_custom_address_is_not_used() -> None:
    data = {"email": "a@x.org", "notification_email": "victim@y.org"}
    assert resolve_recipient(data) == "a@x.org"


def test_confirmed_custom_address_is_used() -> None:
    data = {
        "email": "a@x.org",
        "notification_email": "Me@Lab.org",
        "verified_notification_email": "me@lab.org",
    }
    assert resolve_recipient(data) == "Me@Lab.org"


def test_same_address_needs_no_confirmation() -> None:
    data = {"email": "a@x.org", "notification_email": "A@x.org"}
    assert resolve_recipient(data).lower() == "a@x.org"
