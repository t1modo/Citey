"""
The backend is async-driven: one event loop serves every request, so nothing
may block it.

* Every route handler and every dependency is a coroutine (two cheap, cached
  sync dependencies excepted).
* The Postgres layer (app.core.db) and the migrations are async.
* At runtime, no blocking call (Firestore, Firebase Auth, Resend) runs on
  the loop that serves the request: each goes through run_blocking or
  run_off_loop (app.core.concurrency). A fake Firestore and fake Firebase
  Auth record every call made on the serving loop, and every endpoint that
  touches them is exercised.

A new route must be added to ``REQUESTS`` (if it can block) or to
``NO_BLOCKING_IO`` (if it only awaits async clients), or the coverage test
fails.
"""

import asyncio
import inspect
from contextlib import AbstractAsyncContextManager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import firebase_admin.auth
import pytest
import resend
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.core import db as core_db
from app.firebase_client import get_db
from app.main import create_app

USER = {"email": "ada@uni.edu", "notify_enabled": True, "display_name": "Ada"}


# --- Introspection helpers ---------------------------------------------------


def api_routes(app) -> list[tuple[str, str, APIRoute]]:
    """(method, full path, route) for every API route, including those of
    included routers."""
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            out += [(m, r.path, r) for m in r.methods]
        elif type(r).__name__ == "_IncludedRouter":
            for sub in r.original_router.routes:
                if isinstance(sub, APIRoute):
                    path = r.include_context.prefix + sub.path
                    out += [(m, path, sub) for m in sub.methods]
    return out


def _is_async_callable(call) -> bool:
    if inspect.iscoroutinefunction(call) or inspect.isasyncgenfunction(call):
        return True
    dunder = getattr(type(call), "__call__", None)
    return inspect.iscoroutinefunction(dunder)


def _dependencies(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependencies(dep)


# Sync dependencies FastAPI may run on its threadpool: both return cached
# objects and do no I/O.
ALLOWED_SYNC_DEPENDENCIES = {get_settings, get_db}


# --- Static checks -----------------------------------------------------------


def test_every_route_handler_is_async() -> None:
    sync = [
        f"{method} {path} ({route.endpoint.__module__}.{route.endpoint.__name__})"
        for method, path, route in api_routes(create_app())
        if not inspect.iscoroutinefunction(route.endpoint)
    ]
    assert sync == [], "Route handlers must be `async def`:\n" + "\n".join(sync)


def test_every_dependency_is_async() -> None:
    sync = sorted({
        f"{getattr(call, '__module__', '?')}.{getattr(call, '__name__', type(call).__name__)}"
        for _, _, route in api_routes(create_app())
        for call in _dependencies(route.dependant)
        if call not in ALLOWED_SYNC_DEPENDENCIES and not _is_async_callable(call)
    })
    assert sync == [], "Dependencies must be async:\n" + "\n".join(sync)


def test_the_postgres_layer_is_async() -> None:
    assert inspect.isasyncgenfunction(core_db.get_session)
    assert inspect.iscoroutinefunction(core_db.check)
    assert isinstance(core_db.make_engine("postgresql://u@localhost/db"), AsyncEngine)


def test_connect_is_an_async_context_manager(monkeypatch) -> None:
    monkeypatch.setattr(core_db, "get_settings", lambda: Settings(database_url="postgresql://u@h/d"))
    assert isinstance(core_db.connect(), AbstractAsyncContextManager)


def test_migrations_run_on_the_async_engine() -> None:
    from pathlib import Path

    env = (Path(__file__).resolve().parent.parent / "migrations" / "env.py").read_text()
    assert "run_sync(" in env and "asyncio.run(" in env


# --- Runtime check: nothing blocks the serving loop --------------------------


class LoopGuard:
    """Records blocking calls made on a loop that is serving a request."""

    def __init__(self) -> None:
        self.serving_loops: set[asyncio.AbstractEventLoop] = set()
        self.calls_on_loop: list[str] = []
        self.calls_total = 0

    def record(self, what: str) -> None:
        self.calls_total += 1
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # a worker thread: fine
        if loop in self.serving_loops:
            self.calls_on_loop.append(what)

    def asgi(self, app):
        async def wrapped(scope, receive, send):
            self.serving_loops.add(asyncio.get_running_loop())
            await app(scope, receive, send)

        return wrapped


class FakeSnapshot:
    def __init__(self, guard: LoopGuard, path: str, exists: bool) -> None:
        self.id = path.rsplit("/", 1)[-1]
        self.exists = exists
        self.reference = FakeRef(guard, path)
        self._data = dict(USER) if exists else {}

    def to_dict(self) -> dict:
        return dict(self._data)


class FakeBatch:
    def __init__(self, guard: LoopGuard) -> None:
        self.guard = guard

    def set(self, *a, **k) -> None: ...
    def update(self, *a, **k) -> None: ...
    def delete(self, *a, **k) -> None: ...

    def commit(self) -> None:
        self.guard.record("batch.commit")


class FakeRef:
    """A Firestore client, collection, document or query. Building a
    reference is local; reading or writing is I/O and is recorded."""

    def __init__(self, guard: LoopGuard, path: str = "") -> None:
        self.guard, self.path = guard, path

    # Local: no I/O.
    def collection(self, name: str) -> "FakeRef":
        return FakeRef(self.guard, f"{self.path}/{name}")

    def document(self, doc_id: str = "new") -> "FakeRef":
        return FakeRef(self.guard, f"{self.path}/{doc_id}")

    def where(self, *a, **k) -> "FakeRef":
        return self

    def order_by(self, *a, **k) -> "FakeRef":
        return self

    def limit(self, *a, **k) -> "FakeRef":
        return self

    def select(self, *a, **k) -> "FakeRef":
        return self

    def offset(self, *a, **k) -> "FakeRef":
        return self

    def batch(self) -> FakeBatch:
        return FakeBatch(self.guard)

    # I/O.
    def get(self, *a, **k) -> FakeSnapshot:
        self.guard.record(f"get {self.path}")
        # Users exist; their papers don't, so adding one goes all the way.
        return FakeSnapshot(self.guard, self.path, exists="/trackedWorks/" not in self.path)

    def stream(self, *a, **k):
        self.guard.record(f"stream {self.path}")
        return iter([FakeSnapshot(self.guard, f"{self.path}/doc1", exists=True)])

    def set(self, *a, **k) -> None:
        self.guard.record(f"set {self.path}")

    def update(self, *a, **k) -> None:
        self.guard.record(f"update {self.path}")

    def delete(self, *a, **k) -> None:
        self.guard.record(f"delete {self.path}")

    def collections(self):
        self.guard.record(f"collections {self.path}")
        return iter([])


@pytest.fixture
def guarded(monkeypatch):
    """The app wired to a fake Firestore and fake Firebase Auth / Resend."""
    guard = LoopGuard()
    fake_db = FakeRef(guard)
    settings = Settings(cron_secret="s3cret", resend_api_key="re_test", app_url="https://www.citey.email")

    def blocking(name, result=None):
        def call(*a, **k):
            guard.record(name)
            return result() if callable(result) else result
        return call

    # Sign-in checks, Firebase Auth and Resend are blocking SDK calls.
    for module in ("app.deps", "app.routers.jobs", "app.routers.support"):
        monkeypatch.setattr(f"{module}.verify_token", blocking("verify_token", {"uid": "u1"}))
    monkeypatch.setattr(firebase_admin.auth, "get_user", blocking(
        "auth.get_user", lambda: SimpleNamespace(uid="u1", email="ada@uni.edu", email_verified=False)))
    monkeypatch.setattr(firebase_admin.auth, "delete_user", blocking("auth.delete_user"))
    monkeypatch.setattr(firebase_admin.auth, "generate_email_verification_link",
                        blocking("auth.generate_email_verification_link", "https://verify"))
    monkeypatch.setattr(resend.Emails, "send", blocking("resend.send", {"id": "email_1"}))
    monkeypatch.setattr("app.services.email_service.verify_signed_token", lambda *a, **k: True)
    monkeypatch.setattr("app.firebase_client.get_db", lambda: fake_db)

    # Remote lookups are async HTTP clients, mocked here.
    monkeypatch.setattr("app.routers.works.resolve_doi", AsyncMock(return_value={
        "doi": "10.1/x", "title": "A Paper", "authors": ["Ada"], "openalex_id": "W1"}))
    monkeypatch.setattr("app.services.arxiv_api.get_authors", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.openalex.get_works_by_author", AsyncMock(return_value=[
        {"id": "W2", "doi": "https://doi.org/10.1/y", "title": "Another", "authorships": []}]))

    # The Firestore-backed jobs. Each reads Firestore like the real one; the
    # routes must run them off the serving loop (run_off_loop).
    async def job(*result, **kwargs):
        fake_db.collection("users").document("u1").get()
        return result[0] if len(result) == 1 else result

    svc = "app.services.citation_service"
    monkeypatch.setattr(f"{svc}.run_job_for_user", lambda **k: job(0, 0))
    monkeypatch.setattr(f"{svc}.prune_user_notifications", lambda **k: job(0))
    monkeypatch.setattr(f"{svc}.cleanup_orphan_users", lambda **k: job({"users_deleted": 0}))
    monkeypatch.setattr("app.services.publication_sync.sync_new_publications_for_user", lambda **k: job(0))

    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(guard.asgi(app), raise_server_exceptions=False)
    return guard, client, app


AUTH = {"Authorization": "Bearer t"}
CRON = {"X-Cron-Secret": "s3cret"}

# One request per route that can block, with what it needs to get far.
REQUESTS = {
    ("POST", "/api/auth/send-verification"): dict(headers=AUTH),
    ("GET", "/api/profile"): dict(headers=AUTH),
    ("PUT", "/api/profile"): dict(headers=AUTH, json={"display_name": "Ada L."}),
    ("GET", "/api/profile/confirm-notification-email"): dict(
        params={"uid": "u1", "email": "ada@lab.org", "token": "t"}),
    ("DELETE", "/api/profile"): dict(headers=AUTH),
    ("DELETE", "/api/profile/linked-author"): dict(headers=AUTH),
    ("POST", "/api/profile/unsubscribe"): dict(json={"uid": "u1", "token": "t"}),
    ("POST", "/api/works"): dict(headers=AUTH, json={"doi": "10.1/x"}),
    ("POST", "/api/works/import"): dict(headers=AUTH, json={"author_id": "A1", "author_name": "Ada"}),
    ("DELETE", "/api/works/{work_id}"): dict(headers=AUTH, path="/api/works/10.1_x"),
    ("GET", "/api/works"): dict(headers=AUTH),
    ("GET", "/api/notifications"): dict(headers=AUTH),
    ("GET", "/api/notifications/export.bib"): dict(headers=AUTH),
    ("POST", "/api/notifications/prune"): dict(headers=AUTH),
    ("POST", "/api/notifications/seen/all"): dict(headers=AUTH),
    ("POST", "/api/notifications/{notification_id}/seen"): dict(
        headers=AUTH, path="/api/notifications/n1/seen"),
    ("POST", "/api/jobs/run"): dict(headers=AUTH, json={}),
    ("POST", "/api/jobs/cleanup-notifications"): dict(headers=AUTH, json={}),
    ("POST", "/api/jobs/sync-publications"): dict(headers=AUTH, json={}),
    ("POST", "/api/jobs/cleanup-orphan-users"): dict(headers=CRON, json={}),
    ("POST", "/api/jobs/email-test"): dict(headers=AUTH),
    ("POST", "/api/support"): dict(json={
        "email": "ada@uni.edu", "message": "My citations look wrong.", "elapsed_ms": 5000}),
}

# Routes that only await async clients (httpx, AsyncAnthropic, async
# psycopg) and never touch Firestore, Firebase Auth or Resend.
NO_BLOCKING_IO = {
    ("GET", "/"),
    ("GET", "/api/health"),
    ("GET", "/api/health/db"),
    ("GET", "/api/works/author-search"),
    ("GET", "/api/works/paper-authors"),
    ("POST", "/api/chat"),
}


def test_every_route_is_covered_by_the_blocking_check() -> None:
    routes = {(m, p) for m, p, _ in api_routes(create_app()) if m != "HEAD"}
    missing = routes - set(REQUESTS) - NO_BLOCKING_IO
    stale = (set(REQUESTS) | NO_BLOCKING_IO) - routes
    assert not missing, f"Add these routes to REQUESTS or NO_BLOCKING_IO: {sorted(missing)}"
    assert not stale, f"These routes no longer exist: {sorted(stale)}"


@pytest.mark.parametrize("route", sorted(REQUESTS), ids=lambda r: f"{r[0]} {r[1]}")
def test_no_blocking_call_runs_on_the_serving_loop(guarded, route) -> None:
    guard, client, _ = guarded
    method, path = route
    req = dict(REQUESTS[route])
    resp = client.request(method, req.pop("path", path), **req)

    assert resp.status_code < 500, f"{method} {path} -> {resp.status_code}: {resp.text[:300]}"
    assert guard.calls_total > 0, "the request never reached Firestore or the auth/email SDKs"
    assert guard.calls_on_loop == [], (
        f"{method} {path} blocked the event loop with: {guard.calls_on_loop}. "
        "Wrap blocking calls in run_blocking / run_off_loop (app.core.concurrency)."
    )


def test_the_guard_catches_a_blocking_call_on_the_loop(guarded) -> None:
    """The check itself works: a handler that calls Firestore directly fails."""
    guard, client, app = guarded

    @app.get("/api/__blocking_probe")
    async def probe(db=__import__("fastapi").Depends(get_db)):
        db.collection("users").document("u1").get()  # blocking, on the loop
        return {}

    client.get("/api/__blocking_probe")
    assert guard.calls_on_loop == ["get /users/u1"]
