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


def test_password_checker_reproduces_firebases_published_example():
    """firebase/scrypt's README example: user1password with these parameters."""
    import base64

    spec = importlib.util.spec_from_file_location("verify", _PATH.parent / "verify_firebase_password.py")
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    signer = base64.b64decode(
        "jxspr8Ki0RYycVU8zykbdLGjFQ3McFUH0uiiTvC8pVMXAn210wjLNmdZJzxUECKbm0QsEmYUSDzZvpjeJ9WmXA==")
    computed = verify.firebase_hash(
        "user1password", base64.b64decode("42xEC+ixf3L2lw=="), base64.b64decode("Bw=="), signer, 8, 14)
    assert base64.b64encode(computed).decode() == (
        "lSrfV15cpx95/sZS2W9c9Kp6i/LVgQNDNC/qzrCnh1SAyZvqmZqAjTdn3aoItz+VHjoZilo78198JAdRuid5lQ==")
