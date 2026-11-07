"""Clerk session tokens are accepted next to Firebase ID tokens."""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from citey import clerk_auth, firebase_client
from citey.config import Settings

PK = "pk_test_ZWFnZXItc2hhcmstMjg1Ni5jbGVyay5hY2NvdW50cy5kZXYk"
ISS = "https://eager-shark-2856.clerk.accounts.dev"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(**overrides) -> str:
    now = int(time.time())
    claims = {"iss": ISS, "sub": "user_abc", "iat": now, "exp": now + 60,
              "azp": "https://www.citey.email", "external_id": "fbUid123", "email": "a@b.co"}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture(autouse=True)
def clerk_settings(monkeypatch):
    settings = Settings(clerk_publishable_key=PK, allowed_origins="https://www.citey.email,https://citey.email")
    monkeypatch.setattr(clerk_auth, "get_settings", lambda: settings)
    signing = MagicMock()
    signing.get_signing_key_from_jwt.return_value.key = _KEY.public_key()
    clerk_auth._jwks_client.cache_clear()
    with patch.object(clerk_auth.jwt, "PyJWKClient", return_value=signing):
        yield


def test_publishable_key_names_the_frontend_api():
    assert clerk_auth.frontend_api(PK) == "eager-shark-2856.clerk.accounts.dev"


def test_migrated_user_keeps_their_firebase_uid():
    claims = firebase_client.verify_token(_token())
    assert claims["uid"] == "fbUid123"
    assert claims["clerk_user_id"] == "user_abc"
    assert claims["email"] == "a@b.co" and claims["auth_provider"] == "clerk"


def test_new_clerk_user_is_known_by_clerk_id():
    assert firebase_client.verify_token(_token(external_id=""))["uid"] == "user_abc"


def test_expired_token_is_refused():
    with pytest.raises(jwt.ExpiredSignatureError):
        firebase_client.verify_token(_token(exp=int(time.time()) - 60))


def test_token_for_another_site_is_refused():
    with pytest.raises(jwt.InvalidTokenError):
        firebase_client.verify_token(_token(azp="https://evil.example"))


def test_token_signed_by_another_key_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"iss": ISS, "sub": "user_x", "iat": int(time.time()), "exp": int(time.time()) + 60},
                        other, algorithm="RS256", headers={"kid": "k1"})
    with pytest.raises(jwt.InvalidSignatureError):
        firebase_client.verify_token(forged)


def test_other_tokens_still_go_to_firebase():
    firebase_token = _token(iss="https://securetoken.google.com/citey-ad63a")
    with patch.object(firebase_client, "_initialize_firebase"), \
         patch.object(firebase_client.auth, "verify_id_token", return_value={"uid": "fb1"}) as fb:
        assert firebase_client.verify_token(firebase_token) == {"uid": "fb1"}
    fb.assert_called_once()


def test_without_a_publishable_key_nothing_is_treated_as_clerk(monkeypatch):
    monkeypatch.setattr(clerk_auth, "get_settings", lambda: Settings())
    assert clerk_auth.is_clerk_token(_token()) is False
