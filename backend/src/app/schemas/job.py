"""API shapes for running the citation check by hand (/api/jobs)."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class JobRunRequest(SQLModel):
    dry_run: bool = False
    # Batching for all-users runs called with X-Cron-Secret, for example by
    # hand on Vercel (ignored for a user's own check). cursor: resume after
    # this uid, taken from the previous batch's next_cursor.
    # time_budget_seconds: start no new user after this long, so each
    # request ends inside the host's limit (300 s on Vercel Hobby).
    # Without a budget one request covers every user.
    cursor: str | None = None
    time_budget_seconds: float | None = Field(default=None, gt=0, le=3600)
    # When the run started. A user whose own papers outlast a batch resumes
    # in the next batch, skipping papers already checked since this time.
    checked_since: datetime | None = None
