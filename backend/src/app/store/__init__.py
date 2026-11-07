"""
Reading and writing Citey's data in Postgres, over the async session
(app.core.db.get_session). Routers and jobs call these instead of building
queries themselves.

    users      accounts, settings, linked authors, cooldowns
    works      papers and who tracks them
    citations  citing papers and "A cites B", for the citation check
    alerts     each user's citations: listing, seen, emailed, pruning
    limits     contact form rate limits
    convert    rows to the API shapes in app.schemas

Functions flush but never commit: the caller commits once its whole change
is made, so a request either saves everything or nothing.
"""
