"""A new profile's email comes from the verified session token, so it never
depends on a Clerk Backend API call succeeding."""

from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.clerk_auth import signed_in_email
from app.deps import get_current_user
from app.services import user_service
from app.store import UserStore
from tests.conftest import needs_db


def test_the_token_email_is_visible_to_the_route():
    app = FastAPI()

    @app.get("/who")
    async def who(uid: str = Depends(get_current_user)):
        return {"uid": uid, "email": signed_in_email.get()}

    with patch("app.deps.verify_token", return_value={"uid": "user_1", "email": "ada@uni.edu"}):
        resp = TestClient(app).get("/who", headers={"Authorization": "Bearer t"})
    assert resp.json() == {"uid": "user_1", "email": "ada@uni.edu"}


async def test_account_email_prefers_the_token_and_skips_clerk():
    token = signed_in_email.set("ada@uni.edu")
    try:
        with patch("app.clerk_api.email_for") as lookup:
            assert await user_service._account_email("user_1") == "ada@uni.edu"
        lookup.assert_not_called()
    finally:
        signed_in_email.reset(token)


async def test_account_email_falls_back_to_clerk_without_a_token_email():
    with patch("app.clerk_api.email_for", return_value="ada@lab.org") as lookup:
        assert await user_service._account_email("user_1") == "ada@lab.org"
    lookup.assert_called_once_with("user_1")


@needs_db
async def test_a_profile_created_without_an_email_gets_it_filled_in(pg_session):
    await UserStore(pg_session).create("user_1", email="")
    await pg_session.commit()
    token = signed_in_email.set("ada@uni.edu")
    try:
        user = await user_service.ensure_user(pg_session, "user_1")
        await pg_session.commit()
    finally:
        signed_in_email.reset(token)
    assert user.email == "ada@uni.edu"
    assert user.notification_email == "ada@uni.edu"
    assert (await UserStore(pg_session).get("user_1")).email == "ada@uni.edu"
