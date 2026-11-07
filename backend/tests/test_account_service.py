"""
Sign-in accounts across Firebase Auth and Clerk (app.services.account_service).
Firebase's SDK and app.core.clerk are replaced with fakes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from app import firebase_client
from app.core import clerk
from app.services import account_service, citation_service
from app.services.account_service import Account
from app.store import UserStore
from firebase_admin import auth as firebase_auth

from tests.conftest import needs_db


def _unsigned(iss: str) -> str:
    return jwt.encode({"iss": iss, "sub": "x"}, "k" * 32, algorithm="HS256")


@pytest.fixture
def firebase(monkeypatch):
    """A Firebase Auth with one account, fbUid123, and a record of calls."""
    calls: list[str] = []
    users = {"fbUid123": SimpleNamespace(uid="fbUid123", email="fb@x.org", email_verified=True)}
    monkeypatch.setattr(firebase_client, "ensure_firebase", lambda: calls.append("setup"))

    def get_user(uid):
        calls.append("get")
        if uid not in users:
            raise firebase_auth.UserNotFoundError("no user")
        return users[uid]

    def delete_user(uid):
        calls.append(f"delete {uid}")
        if users.pop(uid, None) is None:
            raise firebase_auth.UserNotFoundError("no user")

    def list_users():
        calls.append("list")
        return SimpleNamespace(users=[SimpleNamespace(uid=u) for u in users], get_next_page=lambda: None)

    monkeypatch.setattr(account_service.firebase_auth, "get_user", get_user)
    monkeypatch.setattr(account_service.firebase_auth, "delete_user", delete_user)
    monkeypatch.setattr(account_service.firebase_auth, "list_users", list_users)
    return calls


@pytest.fixture
def clerk_on(monkeypatch):
    monkeypatch.setattr(clerk, "can_verify_tokens", lambda: True)
    monkeypatch.setattr(clerk, "configured", lambda: True)


@pytest.fixture
def clerk_off(monkeypatch):
    monkeypatch.setattr(clerk, "can_verify_tokens", lambda: False)
    monkeypatch.setattr(clerk, "configured", lambda: False)


# --- Tokens ----------------------------------------------------------------


async def test_firebase_tokens_go_to_firebase_and_others_to_clerk(monkeypatch, clerk_on):
    fb = MagicMock(return_value={"uid": "fb1"})
    ck = AsyncMock(return_value={"uid": "user_1"})
    monkeypatch.setattr(firebase_client, "verify_id_token", fb)
    monkeypatch.setattr(clerk, "verify_session_token", ck)
    assert await account_service.verify_token(_unsigned("https://securetoken.google.com/citey-ad63a")) == {"uid": "fb1"}
    assert await account_service.verify_token(_unsigned("https://clerk.citey.email")) == {"uid": "user_1"}
    assert await account_service.verify_token("not-a-jwt") == {"uid": "user_1"}  # refused by Clerk
    assert fb.call_count == 1 and ck.await_count == 2


async def test_without_clerk_every_token_goes_to_firebase(monkeypatch, clerk_off):
    fb = MagicMock(return_value={"uid": "fb1"})
    monkeypatch.setattr(firebase_client, "verify_id_token", fb)
    monkeypatch.setattr(clerk, "verify_session_token", AsyncMock(side_effect=AssertionError))
    assert await account_service.verify_token(_unsigned("https://clerk.citey.email")) == {"uid": "fb1"}


# --- Accounts --------------------------------------------------------------


async def test_clerk_is_asked_first_then_firebase(monkeypatch, firebase, clerk_on):
    clerk_users = {"user_new": clerk.ClerkUser("user_new", None, "new@x.org", True)}
    monkeypatch.setattr(clerk, "get_user", AsyncMock(side_effect=lambda uid: clerk_users.get(uid)))
    assert await account_service.get_account("user_new") == Account("user_new", "new@x.org", True, "clerk")
    assert await account_service.get_account("fbUid123") == Account("fbUid123", "fb@x.org", True, "firebase")
    assert await account_service.get_account("nobody") is None
    assert firebase[0] == "setup"  # Firebase is set up before it is asked


async def test_when_clerk_is_down_firebase_still_answers(monkeypatch, firebase, clerk_on):
    monkeypatch.setattr(clerk, "get_user", AsyncMock(side_effect=RuntimeError("Clerk is down")))
    assert (await account_service.get_account("fbUid123")).provider == "firebase"


async def test_deleting_an_account_removes_it_from_both(monkeypatch, firebase, clerk_on):
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(clerk, "delete_user", delete)
    await account_service.delete_account("fbUid123")
    delete.assert_awaited_once_with("fbUid123")
    assert "delete fbUid123" in firebase


async def test_a_clerk_failure_does_not_stop_the_firebase_delete(monkeypatch, firebase, clerk_on):
    monkeypatch.setattr(clerk, "delete_user", AsyncMock(side_effect=RuntimeError("Clerk is down")))
    await account_service.delete_account("fbUid123")
    assert "delete fbUid123" in firebase


async def test_sign_in_uids_are_firebase_and_clerk_together(monkeypatch, firebase, clerk_on):
    monkeypatch.setattr(clerk, "all_uids", AsyncMock(return_value={"user_new", "user_imp", "fbUid123"}))
    assert await account_service.sign_in_uids() == {"fbUid123", "user_new", "user_imp"}
    # A nightly job has no sign-in token: Firebase is set up before listing.
    assert firebase[:2] == ["setup", "list"]


async def test_if_clerk_cannot_be_listed_the_list_fails(monkeypatch, firebase, clerk_on):
    monkeypatch.setattr(clerk, "all_uids", AsyncMock(side_effect=RuntimeError("Clerk is down")))
    with pytest.raises(RuntimeError):
        await account_service.sign_in_uids()


@needs_db
async def test_the_orphan_cleanup_keeps_users_who_signed_up_with_clerk(monkeypatch, firebase, clerk_on, pg_session):
    monkeypatch.setattr(clerk, "all_uids", AsyncMock(return_value={"user_new"}))
    store = UserStore(pg_session)
    for uid in ("fbUid123", "user_new", "gone"):
        await store.create(uid, email=f"{uid}@x.org")
    await pg_session.commit()

    result = await citation_service.cleanup_orphan_users(pg_session)
    assert result["orphans_deleted"] == 1
    assert await store.ids_after() == ["fbUid123", "user_new"]


@needs_db
async def test_the_orphan_cleanup_deletes_nobody_when_clerk_is_down(monkeypatch, firebase, clerk_on, pg_session):
    monkeypatch.setattr(clerk, "all_uids", AsyncMock(side_effect=RuntimeError("Clerk is down")))
    await UserStore(pg_session).create("user_new", email="n@x.org")
    await pg_session.commit()
    with pytest.raises(RuntimeError):
        await citation_service.cleanup_orphan_users(pg_session)
    assert await UserStore(pg_session).ids_after() == ["user_new"]
