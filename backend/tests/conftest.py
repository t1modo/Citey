"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Skip real waiting in the source clients' retry and throttle loops."""

    async def _instant(_seconds: float) -> None:
        return None

    from citey.services import openalex, semantic_scholar

    monkeypatch.setattr(openalex, "_sleep", _instant)
    monkeypatch.setattr(semantic_scholar, "_sleep", _instant, raising=False)


@pytest.fixture(autouse=True)
def _quiet_extra_citation_sources(monkeypatch, request):
    """OpenCitations and Europe PMC answer "no citations" unless a test
    patches them, so tests written for OpenAlex and S2 never reach the
    network. Tests of the clients themselves opt out with the marker."""
    from citey.services import http_retry

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http_retry, "_sleep", _instant)
    if request.node.get_closest_marker("real_extra_sources"):
        return

    from unittest.mock import AsyncMock

    from citey.services import citation_service

    monkeypatch.setattr(citation_service.opencitations_svc, "get_citing_refs", AsyncMock(return_value=[]))
    monkeypatch.setattr(citation_service.europe_pmc_svc, "get_citing_works", AsyncMock(return_value=[]))
