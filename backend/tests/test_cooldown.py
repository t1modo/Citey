from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from citey.deps import enforce_cooldown


def _ago(seconds: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)


def test_recent_action_is_rejected_with_retry_after() -> None:
    with pytest.raises(HTTPException) as exc:
        enforce_cooldown({"last": _ago(10)}, "last", 60, "slow down")
    assert exc.value.status_code == 429
    assert 45 <= exc.value.detail["retry_after_seconds"] <= 50


def test_old_action_is_allowed() -> None:
    enforce_cooldown({"last": _ago(120)}, "last", 60, "slow down")


def test_missing_timestamp_is_allowed() -> None:
    enforce_cooldown({}, "last", 60, "slow down")


def test_new_account_falls_back_to_created_at() -> None:
    with pytest.raises(HTTPException):
        enforce_cooldown(
            {"created_at": _ago(5)}, "last", 60, "slow down", fallback_field="created_at"
        )


def test_naive_datetimes_are_treated_as_utc() -> None:
    naive = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    with pytest.raises(HTTPException):
        enforce_cooldown({"last": naive}, "last", 60, "slow down")
