"""
Clerk through its Backend SDK (app.core.clerk). Tokens are signed here and
checked by the SDK against CLERK_JWT_KEY, so no request reaches Clerk; the
user API is a fake client.
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from app.config import Settings
from app.core import clerk
from clerk_backend_api import models
from clerk_backend_api.security import TokenVerificationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
).decode()
SITE = "https://www.citey.email"


def _token(key=_KEY, **overrides) -> str:
    now = int(time.time())
    claims = {"iss": "https://clerk.citey.email", "sub": "user_abc", "iat": now, "nbf": now,
              "exp": now + 60, "azp": SITE, "sid": "sess_1", "external_id": "fbUid123"}
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256")


@pytest.fixture(autouse=True)
def clerk_settings(monkeypatch):
    settings = Settings(clerk_jwt_key=_PEM, allowed_origins=f"{SITE},https://citey.email")
    monkeypatch.setattr(clerk, "get_settings", lambda: settings)
    clerk._uid_cache.clear()
    return settings


# --- Session tokens --------------------------------------------------------


async def test_an_imported_user_keeps_their_firebase_uid():
    claims = await clerk.verify_session_token(_token())
    assert claims["uid"] == "fbUid123"
    assert claims["clerk_user_id"] == "user_abc" and claims["auth_provider"] == "clerk"


async def test_a_user_who_signed_up_with_clerk_is_known_by_their_clerk_id():
    assert (await clerk.verify_session_token(_token(external_id="")))["uid"] == "user_abc"


@pytest.mark.parametrize("bad", [
    {"exp": int(time.time()) - 60, "iat": int(time.time()) - 120},  # expired
    {"azp": "https://evil.example"},  # minted for another site
    {"azp": None},  # no authorized party
    {"exp": None},  # never expires
    {"sub": "org_1"},  # not a user
])
async def test_bad_tokens_are_refused(bad):
    with pytest.raises((TokenVerificationError, jwt.PyJWTError)):
        await clerk.verify_session_token(_token(**bad))


async def test_a_token_signed_by_another_key_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises((TokenVerificationError, jwt.PyJWTError)):
        await clerk.verify_session_token(_token(key=other))


async def test_machine_tokens_and_api_keys_are_refused_without_calling_clerk(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(clerk, "verify_token_async", check)
    for token in ("ak_live_123", "mt_123", "oat_123"):
        with pytest.raises(TokenVerificationError):
            await clerk.verify_session_token(token)
    check.assert_not_awaited()


async def test_without_keys_no_token_is_checked(monkeypatch, clerk_settings):
    monkeypatch.setattr(clerk, "get_settings", lambda: Settings())
    assert not clerk.can_verify_tokens() and not clerk.configured()
    with pytest.raises(TokenVerificationError):
        await clerk.verify_session_token(_token())


async def test_a_template_without_external_id_looks_the_uid_up_once(monkeypatch, clerk_settings):
    clerk_settings.clerk_secret_key = "sk_test_x"
    lookup = AsyncMock(return_value=clerk.ClerkUser("user_abc", "fbUid123", "a@b.co", True))
    monkeypatch.setattr(clerk, "get_user", lookup)
    for _ in range(3):
        assert (await clerk.verify_session_token(_token(external_id=None)))["uid"] == "fbUid123"
    lookup.assert_awaited_once_with("user_abc")


# --- Users -----------------------------------------------------------------


def _user(uid, external_id=None, email="a@b.co", status="verified"):
    address = SimpleNamespace(id=f"idn_{uid}", email_address=email,
                              verification=SimpleNamespace(status=status))
    return SimpleNamespace(id=uid, external_id=external_id, primary_email_address_id=address.id,
                           email_addresses=[address])


def _not_found() -> models.ClerkErrors:
    response = httpx.Response(404, request=httpx.Request("GET", "https://api.clerk.com/v1/users/x"))
    return models.ClerkErrors(data=models.ClerkErrorsData(errors=[]), raw_response=response)


class _FakeClerk:
    def __init__(self, users):
        self.all = users
        self.deleted: list[str] = []
        self.lists: list[dict] = []
        self.users = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_async(self, user_id):
        for user in self.all:
            if user.id == user_id:
                return user
        raise _not_found()

    async def list_async(self, request):
        self.lists.append(request)
        users = self.all
        if "external_id" in request:
            users = [u for u in users if u.external_id in request["external_id"]]
        offset = request.get("offset", 0)
        return users[offset:offset + request.get("limit", 10)]

    async def delete_async(self, user_id):
        self.deleted.append(user_id)


@pytest.fixture
def fake(monkeypatch, clerk_settings):
    clerk_settings.clerk_secret_key = "sk_test_x"
    client = _FakeClerk([_user("user_new"), _user("user_imp", external_id="fbUid123", status="unverified")])
    monkeypatch.setattr(clerk, "_client", lambda: client)
    return client


async def test_a_user_is_found_by_clerk_id_or_by_firebase_uid(fake):
    assert (await clerk.get_user("user_new")) == clerk.ClerkUser("user_new", None, "a@b.co", True)
    imported = await clerk.get_user("fbUid123")
    assert imported.id == "user_imp" and imported.uid == "fbUid123" and not imported.email_verified
    assert await clerk.get_user("user_gone") is None
    assert await clerk.get_user("fbNobody") is None


async def test_deleting_removes_the_clerk_user_behind_a_firebase_uid(fake):
    assert await clerk.delete_user("fbUid123") is True
    assert fake.deleted == ["user_imp"]
    assert await clerk.delete_user("fbNobody") is False


async def test_every_uid_is_listed_across_pages(monkeypatch, fake):
    fake.all = [_user(f"user_{i}", external_id=f"fb{i}" if i % 2 else None) for i in range(5)]
    monkeypatch.setattr(clerk, "_PAGE_SIZE", 2)
    uids = await clerk.all_uids()
    assert uids == {"user_0", "user_1", "fb1", "user_2", "user_3", "fb3", "user_4"}
    assert [r["offset"] for r in fake.lists] == [0, 2, 4]
