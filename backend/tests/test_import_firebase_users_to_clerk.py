"""The Firebase to Clerk user import script."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_firebase_users_to_clerk.py"
_spec = importlib.util.spec_from_file_location("import_users", _PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

PARAMS = {"signer_key": "SIGNER==", "salt_separator": "Bw==", "rounds": "8", "mem_cost": "14"}


def test_password_digest_is_clerks_scrypt_firebase_layout():
    user = {"passwordHash": "HASH==", "salt": "SALT=="}
    assert mod.password_digest(user, PARAMS) == "HASH==$SALT==$SIGNER==$Bw==$8$14"


def test_user_with_a_password_keeps_it_and_their_firebase_uid():
    body = mod.clerk_user_body(
        {"localId": "fb1", "email": "a@b.co", "displayName": "Ann Lee",
         "passwordHash": "H", "salt": "S"}, PARAMS)
    assert body["external_id"] == "fb1"
    assert body["email_address"] == ["a@b.co"]
    assert body["password_hasher"] == "scrypt_firebase"
    assert body["first_name"] == "Ann" and body["last_name"] == "Lee"
    assert "skip_password_requirement" not in body


def test_user_without_a_password_is_created_without_one():
    body = mod.clerk_user_body({"localId": "fb2", "email": "c@d.co"}, PARAMS)
    assert body["skip_password_requirement"] is True
    assert "password_digest" not in body


def test_record_without_email_is_skipped():
    assert mod.clerk_user_body({"localId": "fb3"}, PARAMS) is None
