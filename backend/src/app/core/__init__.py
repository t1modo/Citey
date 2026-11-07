"""
Infrastructure the rest of the app builds on.

    db.py           Postgres, async: raw psycopg connections (connect) and
                    SQLModel / SQLAlchemy AsyncSessions (get_session)
    concurrency.py  run_blocking / run_off_loop, for blocking calls
                    (Clerk's Backend API and key fetch, Resend)
"""
