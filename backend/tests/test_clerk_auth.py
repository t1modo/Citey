"""Clerk session tokens are how users sign in to the API."""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import clerk_auth
from app.config import Settings

PK = "pk_test_ZWFnZXItc2hhcmstMjg1Ni5jbGVyay5hY2NvdW50cy5kZXYk"
ISS = "https://eager-shark-2856.clerk.accounts.dev"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(**overrides) -> str:
    now = int(time.time())
    claims = {"iss": ISS, "sub": "user_abc", "iat": now, "exp": now + 60,
              "azp": "https://www.citey.email", "email": "a@b.co"}
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


def test_user_is_known_by_their_clerk_id():
    assert clerk_auth.verify_token(_token()) == {"uid": "user_abc", "email": "a@b.co"}


def test_expired_token_is_refused():
    with pytest.raises(jwt.ExpiredSignatureError):
        clerk_auth.verify_token(_token(exp=int(time.time()) - 60))


def test_token_for_another_site_is_refused():
    with pytest.raises(jwt.InvalidTokenError):
        clerk_auth.verify_token(_token(azp="https://evil.example"))


def test_token_from_another_issuer_is_refused():
    with pytest.raises(jwt.InvalidIssuerError):
        clerk_auth.verify_token(_token(iss="https://securetoken.google.com/citey-ad63a"))


def test_token_signed_by_another_key_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"iss": ISS, "sub": "user_x", "iat": int(time.time()), "exp": int(time.time()) + 60},
                        other, algorithm="RS256", headers={"kid": "k1"})
    with pytest.raises(jwt.InvalidSignatureError):
        clerk_auth.verify_token(forged)


def test_without_a_publishable_key_every_token_is_refused(monkeypatch):
    monkeypatch.setattr(clerk_auth, "get_settings", lambda: Settings())
    with pytest.raises(ValueError):
        clerk_auth.verify_token(_token())
