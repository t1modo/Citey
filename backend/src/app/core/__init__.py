"""
Infrastructure the rest of the app builds on.

    db.py           Postgres, async: raw psycopg connections (connect) and
                    SQLModel / SQLAlchemy AsyncSessions (get_session)
    concurrency.py  run_blocking / run_off_loop, for the blocking SDKs
                    (Firestore, Firebase Auth, Resend) until they are gone
"""
