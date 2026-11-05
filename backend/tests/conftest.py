"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Skip real waiting in the source clients' retry and throttle loops."""

    async def _instant(_seconds: float) -> None:
        return None

    from app.services import openalex, semantic_scholar

    monkeypatch.setattr(openalex, "_sleep", _instant)
    monkeypatch.setattr(semantic_scholar, "_sleep", _instant, raising=False)
