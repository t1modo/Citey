"""
Import Firebase Auth users into Clerk, keeping their passwords.

Run this on your own computer: it reads the password hashes and Clerk's
secret key, which should never leave it.

1. Export the users with the Firebase CLI:

       firebase auth:export users.json --format=json --project citey-ad63a

2. In the Firebase Console, open Authentication > Users > the "⋮" menu >
   "Password hash parameters", and set these four variables from it:

       FIREBASE_HASH_SIGNER_KEY      base64_signer_key
       FIREBASE_HASH_SALT_SEPARATOR  base64_salt_separator
       FIREBASE_HASH_ROUNDS          rounds
       FIREBASE_HASH_MEM_COST        mem_cost

3. Set CLERK_SECRET_KEY to the production instance's secret key (sk_live_...,
   Clerk Dashboard > API keys).

4. Prove the password format with one account on the development
   instance first (its sk_test_ key), and sign in with your old password
   on the development Account Portal:

       python backend/scripts/import_firebase_users_to_clerk.py users.json --only you@example.com

   Then the production instance (its sk_live_ key), a dry run first:

       python backend/scripts/import_firebase_users_to_clerk.py users.json --dry-run
       python backend/scripts/import_firebase_users_to_clerk.py users.json

Each user keeps their email (marked verified) and password, and their
Firebase UID becomes the Clerk external_id, which the API reads to find
their data. A user who already exists in Clerk is skipped, so the script
can be run again. Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

CLERK_API = "https://api.clerk.com/v1/users"
# Clerk allows 100 requests per 10 seconds on the Backend API.
_PAUSE_SECONDS = 0.12


def password_digest(user: dict, params: dict) -> str | None:
    """Clerk's scrypt_firebase digest: hash$salt$signer_key$salt_separator$rounds$mem_cost."""
    if not user.get("passwordHash") or not user.get("salt"):
        return None
    return "$".join([
        user["passwordHash"],
        user["salt"],
        params["signer_key"],
        params["salt_separator"],
        str(params["rounds"]),
        str(params["mem_cost"]),
    ])


def clerk_user_body(user: dict, params: dict) -> dict | None:
    """The Clerk create-user request for one Firebase export record, or None
    when the record has no email (Citey only ever used email sign-in)."""
    email = (user.get("email") or "").strip()
    if not email:
        return None
    body: dict = {
        "external_id": user["localId"],
        "email_address": [email],
        "skip_password_checks": True,
    }
    name = (user.get("displayName") or "").strip()
    if name:
        first, _, last = name.partition(" ")
        body["first_name"] = first
        if last:
            body["last_name"] = last
    digest = password_digest(user, params)
    if digest:
        body["password_digest"] = digest
        body["password_hasher"] = "scrypt_firebase"
    else:
        body["skip_password_requirement"] = True
    return body


def _create(body: dict, secret_key: str) -> tuple[int, str]:
    request = urllib.request.Request(
        CLERK_API,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
            # Cloudflare in front of api.clerk.com refuses Python's default
            # "Python-urllib" agent with "error code: 1010".
            "User-Agent": "citey-firebase-import/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response).get("id", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            errors = json.loads(detail).get("errors") or []
            detail = "; ".join(e.get("code", "") + ": " + e.get("message", "") for e in errors) or detail
        except ValueError:
            pass
        return exc.code, detail


def _hash_params() -> dict:
    names = {
        "signer_key": "FIREBASE_HASH_SIGNER_KEY",
        "salt_separator": "FIREBASE_HASH_SALT_SEPARATOR",
        "rounds": "FIREBASE_HASH_ROUNDS",
        "mem_cost": "FIREBASE_HASH_MEM_COST",
    }
    missing = [env for env in names.values() if not os.environ.get(env)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} from Firebase's password hash parameters.")
    return {key: os.environ[env].strip() for key, env in names.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("export", help="users.json from `firebase auth:export --format=json`")
    parser.add_argument("--dry-run", action="store_true", help="show what would be created")
    parser.add_argument("--only", metavar="EMAIL", help="import just this account (to test first)")
    args = parser.parse_args()

    params = _hash_params()
    secret_key = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not args.dry_run and not secret_key.startswith("sk_"):
        sys.exit("Set CLERK_SECRET_KEY to the Clerk instance's secret key (sk_test_... or sk_live_...).")
    if not args.dry_run:
        print("Instance:", "PRODUCTION" if secret_key.startswith("sk_live_") else "development")

    users = json.load(open(args.export)).get("users", [])
    if args.only:
        users = [u for u in users if (u.get("email") or "").lower() == args.only.lower()]
        if not users:
            sys.exit(f"No user with email {args.only} in {args.export}.")
    created = skipped = failed = 0
    for user in users:
        body = clerk_user_body(user, params)
        uid = user.get("localId", "?")
        if body is None:
            print(f"skip  {uid}: no email")
            skipped += 1
            continue
        if args.dry_run:
            kind = "with password" if "password_digest" in body else "no password"
            print(f"would create {uid} ({kind})")
            created += 1
            continue
        status, result = _create(body, secret_key)
        if status == 200:
            print(f"created {uid} -> {result}")
            created += 1
        elif status == 422 and ("form_identifier_exists" in result or "external_id" in result):
            print(f"skip  {uid}: already in Clerk")
            skipped += 1
        else:
            print(f"FAIL  {uid}: HTTP {status} {result}")
            failed += 1
        time.sleep(_PAUSE_SECONDS)

    verb = "would create" if args.dry_run else "created"
    print(f"\n{len(users)} user(s): {created} {verb}, {skipped} skipped, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
