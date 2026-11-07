"""Firebase Auth calls set up the Admin SDK themselves: a nightly job runs
with no sign-in token, so nothing else has done it."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import citation_service


async def test_listing_accounts_sets_up_firebase_first(monkeypatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(citation_service, "ensure_firebase", lambda: order.append("setup"))

    def list_users():
        order.append("list")
        return SimpleNamespace(users=[SimpleNamespace(uid="a")], get_next_page=lambda: None)

    monkeypatch.setattr(citation_service.firebase_auth, "list_users", list_users)
    assert await citation_service._get_auth_uids() == {"a"}
    assert order == ["setup", "list"]


def test_setting_up_twice_reuses_the_app(monkeypatch) -> None:
    from app import firebase_client

    init = MagicMock(return_value="app")
    monkeypatch.setattr(firebase_client.firebase_admin, "initialize_app", init)
    monkeypatch.setattr(firebase_client.credentials, "Certificate", lambda info: info)
    monkeypatch.setattr(firebase_client, "_app", None)
    monkeypatch.setattr(firebase_client, "get_settings", lambda: SimpleNamespace(
        firebase_service_account_json='{"type": "service_account"}', firebase_service_account_path=""))
    firebase_client.ensure_firebase()
    firebase_client.ensure_firebase()
    init.assert_called_once()
