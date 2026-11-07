"""
Infrastructure the rest of the app builds on.

    db.py           Postgres, async: raw psycopg connections (connect) and
                    SQLModel / SQLAlchemy AsyncSessions (get_session)
    concurrency.py  run_blocking, for the blocking SDKs (Firebase Auth,
                    Resend) until they are gone
"""
