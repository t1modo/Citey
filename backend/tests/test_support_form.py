"""Contact form: delivery, bot traps and the three rate limits."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.firebase_client import get_db
from app.routers import support


class _Snap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Ref:
    def __init__(self, store, key):
        self._store, self._key = store, key

    def get(self):
        return _Snap(self._store.get(self._key))

    def set(self, data):
        self._store[self._key] = dict(data)

    def update(self, data):
        self._store[self._key].update(data)


class _DB:
    def __init__(self):
        self.store: dict = {}

    def collection(self, _name):
        db = self

        class _C:
            def document(self, key):
                return _Ref(db.store, key)

        return _C()


@pytest.fixture()
def client():
    from app.main import app

    db = _DB()
    app.dependency_overrides[get_db] = lambda: db
    deliver = AsyncMock()
    with patch("app.services.email_service.send_support_message", deliver):
        yield TestClient(app), deliver
    app.dependency_overrides.clear()


def _msg(**kw):
    body = {"email": "ada@example.com", "message": "Hello, my citations are missing.", "elapsed_ms": 9000}
    body.update(kw)
    return body


def _post(c, body, ip="1.1.1.1"):
    return c.post("/api/support", json=body, headers={"cf-connecting-ip": ip})


def test_valid_message_is_delivered_with_reply_to_sender(client):
    c, deliver = client
    r = _post(c, _msg(name="Ada", subject="Missing"))
    assert r.status_code == 202
    kwargs = deliver.await_args.kwargs
    assert kwargs["sender_email"] == "ada@example.com" and kwargs["subject"] == "Missing"


@pytest.mark.parametrize("trap", [{"website": "http://spam"}, {"elapsed_ms": 500}])
def test_bots_get_a_success_but_nothing_is_sent(client, trap):
    c, deliver = client
    assert _post(c, _msg(**trap)).status_code == 202
    deliver.assert_not_awaited()


def test_fourth_message_from_one_connection_in_an_hour_is_refused(client):
    c, _ = client
    codes = [_post(c, _msg(email=f"u{i}@example.com")).status_code for i in range(4)]
    assert codes == [202, 202, 202, 429]


def test_fourth_message_from_one_address_in_a_day_is_refused(client):
    c, _ = client
    codes = [_post(c, _msg(), ip=f"9.9.9.{i}").status_code for i in range(4)]
    assert codes == [202, 202, 202, 429]


def test_site_wide_daily_cap(client):
    c, deliver = client
    codes = [
        _post(c, _msg(email=f"u{i}@example.com"), ip=f"10.0.0.{i}").status_code
        for i in range(support.SITE_PER_DAY + 1)
    ]
    assert codes[:-1] == [202] * support.SITE_PER_DAY and codes[-1] == 429
    assert deliver.await_count == support.SITE_PER_DAY


def test_line_breaks_cannot_reach_the_subject(client):
    c, deliver = client
    _post(c, _msg(subject="Hi\r\nBcc: everyone@example.com"))
    assert "\n" not in deliver.await_args.kwargs["subject"]


@pytest.mark.parametrize("body", [_msg(email="not-an-email"), _msg(message="short")])
def test_invalid_input_is_rejected(client, body):
    c, deliver = client
    assert _post(c, body).status_code == 422
    deliver.assert_not_awaited()


def test_client_ip_on_vercel_ignores_a_spoofed_cloudflare_header(monkeypatch) -> None:
    from starlette.requests import Request

    from app.routers.support import _client_ip

    def req(headers: dict) -> Request:
        raw = [(k.encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1234)})

    spoofed = {"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "203.0.113.7"}
    monkeypatch.setenv("VERCEL", "1")
    assert _client_ip(req(spoofed)) == "203.0.113.7"
    assert _client_ip(req({})) == "10.0.0.1"
    monkeypatch.delenv("VERCEL")
    assert _client_ip(req(spoofed)) == "1.2.3.4"


async def test_contact_form_goes_to_support_inbox_when_set():
    from unittest.mock import AsyncMock, patch

    from app.config import Settings
    from app.services import email_service

    send = AsyncMock(return_value={"id": "x"})
    with patch.object(email_service, "_send", send):
        await email_service.send_support_message(
            "a@b.co", "Ann", "Hi", "Hello there", None,
            Settings(support_inbox="owner@example.com"),
        )
        await email_service.send_support_message(
            "a@b.co", "Ann", "Hi", "Hello there", None, Settings(),
        )
    first, second = (c.args[0] for c in send.await_args_list)
    assert first["to"] == ["owner@example.com"]
    assert first["reply_to"] == ["a@b.co"]
    assert second["to"] == ["support@citey.email"]
