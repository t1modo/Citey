"""Accounts known to Clerk count as real accounts for the jobs."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app import clerk_api
from app.config import Settings
from app.services import citation_service, user_service


@pytest.fixture
def clerk_on(monkeypatch):
    monkeypatch.setattr(clerk_api, "get_settings", lambda: Settings(clerk_secret_key="sk_test_x"))


def test_account_uid_prefers_the_firebase_uid():
    assert clerk_api.account_uid({"id": "user_1", "external_id": "fb1"}) == "fb1"
    assert clerk_api.account_uid({"id": "user_2", "external_id": None}) == "user_2"


@respx.mock
def test_lists_every_page_of_users(clerk_on, monkeypatch):
    monkeypatch.setattr(clerk_api, "_PAGE", 2)
    route = respx.get("https://api.clerk.com/v1/users").mock(side_effect=[
        httpx.Response(200, json=[{"id": "user_1", "external_id": "fb1"}, {"id": "user_2"}]),
        httpx.Response(200, json=[{"id": "user_3", "external_id": ""}]),
    ])
    assert clerk_api.list_account_uids() == {"fb1", "user_2", "user_3"}
    assert route.call_count == 2
    assert route.calls[0].request.headers["Authorization"] == "Bearer sk_test_x"


@respx.mock
def test_an_unreachable_clerk_raises_instead_of_returning_a_partial_list(clerk_on):
    respx.get("https://api.clerk.com/v1/users").mock(return_value=httpx.Response(503))
    with pytest.raises(clerk_api.ClerkUnavailable):
        clerk_api.list_account_uids()


async def test_jobs_see_firebase_and_clerk_accounts(clerk_on):
    with patch.object(citation_service, "_list_auth_uids", return_value={"fb1", "fb2"}), \
         patch.object(clerk_api, "list_account_uids", return_value={"fb1", "user_new"}):
        assert await citation_service._get_auth_uids() == {"fb1", "fb2", "user_new"}


async def test_without_a_secret_key_only_firebase_is_asked(monkeypatch):
    monkeypatch.setattr(clerk_api, "get_settings", lambda: Settings())
    with patch.object(citation_service, "_list_auth_uids", return_value={"fb1"}), \
         patch.object(clerk_api, "list_account_uids") as clerk_list:
        assert await citation_service._get_auth_uids() == {"fb1"}
    clerk_list.assert_not_called()


@respx.mock
async def test_new_profile_email_comes_from_clerk_for_a_clerk_only_user(clerk_on):
    respx.get("https://api.clerk.com/v1/users/user_9").mock(return_value=httpx.Response(200, json={
        "id": "user_9", "primary_email_address_id": "idn_1",
        "email_addresses": [{"id": "idn_1", "email_address": "new@example.com"}],
    }))
    with patch.object(user_service, "ensure_firebase"), \
         patch.object(user_service.firebase_auth, "get_user", side_effect=Exception("no such user")):
        assert await user_service._account_email("user_9") == "new@example.com"
