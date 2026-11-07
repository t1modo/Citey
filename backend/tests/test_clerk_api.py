"""The Clerk Backend API: the jobs' list of real accounts, a new profile's
email, and deleting the Clerk user with the account."""

from unittest.mock import patch

import httpx
import pytest
import respx

from app import clerk_api
from app.config import Settings
from app.services import citation_service, user_service


@pytest.fixture
def clerk_on(monkeypatch):
    monkeypatch.setattr(clerk_api, "get_settings", lambda: Settings(clerk_secret_key="sk_test_x"))


@pytest.fixture
def clerk_off(monkeypatch):
    monkeypatch.setattr(clerk_api, "get_settings", lambda: Settings(clerk_secret_key=""))


@respx.mock
def test_lists_every_page_of_users(clerk_on, monkeypatch):
    monkeypatch.setattr(clerk_api, "_PAGE", 2)
    route = respx.get("https://api.clerk.com/v1/users").mock(side_effect=[
        httpx.Response(200, json=[{"id": "user_1"}, {"id": "user_2"}]),
        httpx.Response(200, json=[{"id": "user_3"}]),
    ])
    assert clerk_api.list_account_uids() == {"user_1", "user_2", "user_3"}
    assert route.call_count == 2
    assert route.calls[0].request.headers["Authorization"] == "Bearer sk_test_x"


@respx.mock
def test_an_unreachable_clerk_raises_instead_of_returning_a_partial_list(clerk_on):
    respx.get("https://api.clerk.com/v1/users").mock(return_value=httpx.Response(503))
    with pytest.raises(clerk_api.ClerkUnavailable):
        clerk_api.list_account_uids()


def test_without_a_secret_key_listing_raises_instead_of_returning_nobody(clerk_off):
    # An empty list would make every user look like an orphan to delete.
    with pytest.raises(clerk_api.ClerkUnavailable):
        clerk_api.list_account_uids()


async def test_jobs_see_the_clerk_accounts(clerk_on):
    with patch.object(clerk_api, "list_account_uids", return_value={"user_1", "user_2"}):
        assert await citation_service._get_auth_uids() == {"user_1", "user_2"}


async def test_orphan_cleanup_deletes_nobody_without_clerk(clerk_off):
    with patch.object(citation_service, "UserStore") as store:
        with pytest.raises(clerk_api.ClerkUnavailable):
            await citation_service.cleanup_orphan_users(session=None)
    store.assert_not_called()


@respx.mock
async def test_new_profile_email_comes_from_clerk(clerk_on):
    respx.get("https://api.clerk.com/v1/users/user_9").mock(return_value=httpx.Response(200, json={
        "id": "user_9", "primary_email_address_id": "idn_1",
        "email_addresses": [{"id": "idn_2", "email_address": "old@example.com"},
                            {"id": "idn_1", "email_address": "new@example.com"}],
    }))
    assert await user_service._account_email("user_9") == "new@example.com"


@respx.mock
def test_delete_user_removes_the_clerk_user(clerk_on):
    route = respx.delete("https://api.clerk.com/v1/users/user_9").mock(return_value=httpx.Response(200, json={}))
    clerk_api.delete_user("user_9")
    assert route.called


@respx.mock
def test_delete_user_already_gone_is_fine(clerk_on):
    respx.delete("https://api.clerk.com/v1/users/user_9").mock(return_value=httpx.Response(404, json={}))
    clerk_api.delete_user("user_9")


@respx.mock
def test_delete_user_failure_raises(clerk_on):
    respx.delete("https://api.clerk.com/v1/users/user_9").mock(return_value=httpx.Response(500, json={}))
    with pytest.raises(httpx.HTTPStatusError):
        clerk_api.delete_user("user_9")
