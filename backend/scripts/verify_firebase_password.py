"""
Check a password against one user's hash in a Firebase Auth export.

Run on your own computer, in the same terminal as the Clerk import (it
reads the same FIREBASE_HASH_* variables). It asks for the password
without showing it and prints only whether it matches, so you can tell a
mistyped password apart from a problem with how hashes reach Clerk.

    uv run --project backend python backend/scripts/verify_firebase_password.py users.json you@example.com

(cryptography comes with the backend's locked dependencies.)

Firebase's scrypt: key = scrypt(password, salt + salt_separator,
N = 2**mem_cost, r = rounds, p = 1, 32 bytes); the stored hash is the
signer key encrypted with AES-256-CTR under that key, with a zero IV.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
import sys


def _b64(value: str) -> tuple[bytes, str]:
    """Decode standard or URL-safe base64; report which it was."""
    padded = value + "=" * (-len(value) % 4)
    if "-" in value or "_" in value:
        return base64.urlsafe_b64decode(padded), "url-safe"
    return base64.b64decode(padded), "standard"


def firebase_hash(password: str, salt: bytes, separator: bytes, signer: bytes, rounds: int, mem_cost: int) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = hashlib.scrypt(
        password.encode(), salt=salt + separator, n=2 ** mem_cost, r=rounds, p=1,
        dklen=32, maxmem=256 * 1024 * 1024,
    )
    encryptor = Cipher(algorithms.AES(key), modes.CTR(b"\0" * 16)).encryptor()
    return encryptor.update(signer) + encryptor.finalize()


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: verify_firebase_password.py users.json EMAIL")
    export, email = sys.argv[1], sys.argv[2].lower()
    try:
        signer, _ = _b64(os.environ["FIREBASE_HASH_SIGNER_KEY"].strip())
        separator, _ = _b64(os.environ["FIREBASE_HASH_SALT_SEPARATOR"].strip())
        rounds = int(os.environ["FIREBASE_HASH_ROUNDS"])
        mem_cost = int(os.environ["FIREBASE_HASH_MEM_COST"])
    except KeyError as missing:
        sys.exit(f"Set {missing} first (same as for the import).")

    users = [u for u in json.load(open(export)).get("users", []) if (u.get("email") or "").lower() == email]
    if not users:
        sys.exit(f"No user with email {email} in {export}.")
    user = users[0]
    if not user.get("passwordHash"):
        sys.exit("That user has no password in Firebase (signs in another way).")

    stored, hash_enc = _b64(user["passwordHash"])
    salt, salt_enc = _b64(user["salt"])
    print(f"Export encoding: hash {hash_enc} base64, salt {salt_enc} base64")

    password = getpass.getpass("Password (not shown): ")
    computed = firebase_hash(password, salt, separator, signer, rounds, mem_cost)
    if hmac.compare_digest(computed, stored):
        print("MATCH: this is the password Firebase has stored.")
    else:
        print("NO MATCH: Firebase has a different password for this account.")


if __name__ == "__main__":
    main()
