# Citey

Get an email when a new paper cites yours. Try it at [citey.email](https://www.citey.email/).

## What it does

* Add papers by DOI, or import your whole list from an OpenAlex, Semantic Scholar, INSPIRE or DBLP profile.
* Every night Citey checks OpenAlex, Semantic Scholar, OpenCitations and Europe PMC for new citing papers and emails you the title, authors and affiliations.
* New papers on your linked profile are added automatically.
* Export every citation as BibTeX.

## Stack

* **Frontend:** Next.js, Tailwind, Firebase Auth, PostHog analytics.
* **Backend:** FastAPI, Firestore, Resend for email. Served at `/api` on the same domain.
* **Hosting:** one Vercel project builds both (see [Deploy on Vercel](#deploy-on-vercel)).
* **Scheduled jobs:** [Inngest](https://www.inngest.com/) calls `/api/inngest`. See [Scheduled jobs](#scheduled-jobs).
* **Data:** OpenAlex and Semantic Scholar for citations. Crossref, PubMed, NASA ADS, INSPIRE and DBLP for imports and DOI lookups.

## Run locally

### With Docker

```bash
cp backend/.env.example backend/.env           # Firebase service account JSON, secrets
cp frontend/.env.example frontend/.env.local   # Firebase web config
docker compose up --build
```

Site on http://localhost:3000, API on http://localhost:8000/api, Inngest
Dev Server on http://localhost:8288. The site's Firebase config is compiled
in at build time, so rebuild after editing `frontend/.env.local`.

### Without Docker

The backend uses [uv](https://docs.astral.sh/uv/).

```bash
# API on :8000
cd backend && uv sync && uv run uvicorn app.main:app --reload

# Site on :3000
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Fill `frontend/.env.local` with your Firebase web config.

Run the tests:

```bash
cd backend && uv run pytest        # backend
cd frontend && npm test            # frontend (Vitest), or npm run test:watch
```

Both run on every pull request (`.github/workflows/tests.yml`). The backend's
live API checks are skipped there; run them with
`CITEY_LIVE_TESTS=1 uv run pytest tests/test_live_researchers.py`.
Dependabot (`.github/dependabot.yml`) opens weekly PRs for the uv and npm
dependencies, and monthly ones for GitHub Actions and the Docker base images.

To run the scheduled jobs, keep `INNGEST_DEV=1` in `backend/.env` and start
the Inngest Dev Server next to the API:

```bash
npx --ignore-scripts=false inngest-cli@latest dev -u http://localhost:8000/api/inngest
```

Add or upgrade a backend dependency with `uv add <package>`, which updates
`pyproject.toml` and `uv.lock`.

### Backend layout

```
backend/
  src/app/            the API, as the installable package `app`
    main.py           FastAPI app
    models/           database tables (SQLModel): base.py, user.py, work.py,
                      citation.py, alert.py, support.py
    store/            database access only: base.py (BaseStore), user.py,
                      work.py, citation.py, alert.py, limit.py
    schemas/          API request/response shapes (SQLModel, no table)
    core/             infrastructure: db.py (async Postgres), concurrency.py
    config.py, ...
    routers/          one module per /api/... area
    services/         the rules: tracking, alerts, citation checks, sources,
                      email, publication sync; they use the stores
    templates/email/  email templates, shipped inside the package
  main.py             Vercel's entrypoint: puts src/ on the path, exposes the app
  migrations/         Alembic migrations
  tests/              pytest
  scripts/            one-off maintenance scripts
```

`uv sync` installs `app` in editable mode, so `import app` works from the
tests, scripts, Alembic and `uvicorn app.main:app`. Vercel installs only the
dependencies, never the project itself, so its entrypoint is
`backend/main.py` (`main:app`), which adds `src/` to the path first.
`tests/test_vercel_entrypoint.py` imports it the same way.

### Async

The backend is async throughout: every route handler and dependency is
`async def`, and one event loop serves every request, so nothing may block
it.

- Postgres goes through `app.core.db`: an async engine and `AsyncSession`
  (`Depends(get_session)`), or `async with connect()` for raw SQL. Load
  relationships up front (`selectinload(...)`); lazy loading doesn't work in
  async code.
- The blocking SDKs still in use (Firestore, Firebase Auth, Resend) are called
  through `run_blocking(fn, ...)`, or `run_off_loop(job, ...)` for a whole
  Firestore-backed job, from `app.core.concurrency`, so they run on worker
  threads.

`tests/test_async_backend.py` enforces this: every handler and dependency
must be async, and every route is called against a fake Firestore and fake
Firebase Auth that fail the test if a blocking call runs on the serving
loop. A new route goes in that test's `REQUESTS` (or `NO_BLOCKING_IO`).

### Database (Postgres)

The Postgres tables are SQLModel models (SQLAlchemy 2.1 ORM tables that are
also Pydantic models) in `backend/src/app/models/`, and Alembic migrations
in `backend/migrations/`. `docker compose up` starts a local Postgres 18 and
applies the migrations before the API starts; Compose always uses that local
database, never Neon.

```bash
cd backend
uv run alembic upgrade head                              # apply migrations
uv run alembic revision --autogenerate -m "add x to y"   # after editing app/models/
uv run alembic check                                     # models and migrations agree?
```

Read the generated migration before committing it. The schema tests need a
throwaway database: with Compose running,
`TEST_DATABASE_URL=postgresql://citey:citey@localhost:5432/citey_test uv run pytest`.
CI runs them against its own Postgres. A separate Migrations job:
- fails if there is more than one Alembic head (two branches each added a
  migration);
- applies every migration to an empty database;
- fails if a model changed without a migration (`alembic check`);
- downgrades to empty and upgrades again.

On a pull request it also writes a **migration SQL draft** to the job summary:
the SQL the PR's new migrations will run, and the SQL that undoes them. Read
it before merging. Locally:
`DATABASE_URL=postgresql://x@localhost/x ../.github/scripts/migration-draft.sh origin/main`.

Code reaches Postgres in layers: **routers → services → stores → database**.

- `app/store/` does database access and nothing else: `BaseStore` (in
  `base.py`) holds the request's session, and each area has its own store,
  `UserStore` (`user.py`), `WorkStore` (`work.py`), `CitationStore`
  (`citation.py`), `AlertStore` (`alert.py`) and `LimitStore` (`limit.py`).
  Stores return model rows and never commit.
- `app/services/` holds the rules and uses the stores: for example
  `tracking_service.track_paper` creates the shared paper, adds the user as a
  tracker and announces its recent citations; `convert` turns rows into the
  API's shapes. The router (or job) commits once per request.

To copy the data from Firestore into Postgres (read-only on the Firestore
side, every write an upsert, one transaction per user):

```bash
uv run python scripts/copy_firestore_to_postgres.py --dry-run   # copy, then roll back
uv run python scripts/copy_firestore_to_postgres.py
```

Production is the Neon project `citey`. Migrations are not run on deploy yet:
apply them with `DATABASE_URL_UNPOOLED` set to Neon's direct connection
string before deploying code that needs them.

## Deploy on Vercel

The site and the API deploy as one Vercel project using
[Services](https://vercel.com/docs/services) (beta, available on Hobby).
The root `vercel.json` builds `frontend/` with Next.js and `backend/` with
FastAPI, then routes:

* `/api/*` to the API. Every backend route lives under `/api`, on the
  same domain as the site: `https://www.citey.email/api/...`.
* everything else to the site.

Project settings:

* **Root Directory:** the repository root, not `frontend`.
* **Domains:** `citey.email` and `www.citey.email`.
* **Environment variables:** `NEXT_PUBLIC_API_URL=/api` for the site, plus
  the backend settings below and `FIREBASE_SERVICE_ACCOUNT_JSON`. Set
  `API_URL=https://www.citey.email` (no `/api`); the backend adds the prefix
  to links.

The API runs as one function with Hobby's 300 s limit. The scheduled jobs
stay under it because Inngest checks one user per request (see
[Scheduled jobs](#scheduled-jobs)). The in-app scheduler switches itself off
on Vercel.

Requests to old backend paths without `/api` get a 308 to the `/api` path.
Links in emails sent before the move point at `api.citey.email`, which is
retired with Render, so those stop working.

## Scheduled jobs

[Inngest](https://www.inngest.com/) runs the jobs by calling
`/api/inngest`; the functions are in `backend/src/app/inngest_functions.py`.
Schedules are in Pacific time and follow daylight saving time.

| Job | When | How |
| --- | --- | --- |
| Citation check | Every day, 00:00 | A sweep lists every user with an account and sends one event per user. Each event runs that user's check as its own run, retried up to 3 times if it fails. |
| Notification cleanup | Every day, 01:00 | Deletes notifications older than 30 days. |
| Publication sync | Sundays, 00:00 | Like the citation check, for users with a linked OpenAlex author. |

Every request checks one user, so it stays well inside Vercel Hobby's
300 s limit. At most 2 users are checked at once, across both jobs, to stay
inside the citation sources' rate limits. One user is never checked twice at
once. A sweep that starts while another is running is skipped. Each event ID
names the user and the day, so if the sweep runs again the same night, nobody
is checked or emailed twice.

To run a job now, open the function in the Inngest dashboard (or the Dev
Server at http://localhost:8288) and choose **Invoke**. To check one user,
send `citey/citation-check.requested` with `{"uid": "...", "dry_run": true}`.
The `/api/jobs/*` endpoints still work for checks run by hand: a user's own
check uses their Firebase token, and an all-users run uses `X-Cron-Secret`.

### Production setup

1. In the [Inngest dashboard](https://app.inngest.com), production
   environment, copy the signing key and create an event key.
2. In the Vercel project (the site and API deploy together), set
   `INNGEST_SIGNING_KEY`, `INNGEST_EVENT_KEY` and
   `INNGEST_SERVE_ORIGIN=https://www.citey.email`. Leave `INNGEST_DEV` unset.
   Redeploy. Without the signing key the API still serves everything else
   but leaves `/api/inngest` out and logs an error.
3. In the dashboard choose **Apps > Sync new app** and enter
   `https://www.citey.email/api/inngest`. Five functions should appear.
   Resync after a deploy that changes the functions: use **Resync** in the
   dashboard, or run `curl -X PUT https://www.citey.email/api/inngest`.
4. Delete the `CRON_SECRET` secret from the GitHub repository (Settings >
   Secrets and variables > Actions); no workflow uses it now. Keep
   `CRON_SECRET` on the API host for the `/api/jobs/*` endpoints.

Sync only after the change that removes the GitHub workflows is on `main`.
That way the GitHub workflows and Inngest never both run the same night.

## Backend settings

Required in production:

* `INNGEST_SIGNING_KEY`, `INNGEST_EVENT_KEY`: from the Inngest dashboard; see [Production setup](#production-setup).
* `CRON_SECRET`: secret for running the all-users `/api/jobs/*` endpoints by hand (`X-Cron-Secret` header).
* `TOKEN_SECRET`: signs unsubscribe and confirmation links.
* `API_URL`: `https://www.citey.email`, the public origin used in email links (the backend adds `/api`).
* `ALLOWED_ORIGINS`: comma separated site addresses allowed to call the API.

Optional:

* `INNGEST_SERVE_ORIGIN`: public origin Inngest calls, `https://www.citey.email`.
* `INNGEST_DEV`: `1` (or the Dev Server URL) to use a local Inngest Dev Server. Local only.

* `S2_API_KEY`: Semantic Scholar key. Avoids night time rate limits. [Request one free](https://www.semanticscholar.org/product/api).
* `OPENALEX_API_KEY`: OpenAlex key. Keyless use has a small daily allowance. Free from [openalex.org](https://openalex.org) after signing in.
* `OPENCITATIONS_ACCESS_TOKEN`: OpenCitations token. Raises its rate limit. [Get one free](https://opencitations.net/accesstoken).
* `ADS_API_KEY`: NASA ADS token for astronomy imports. [Get one free](https://ui.adsabs.harvard.edu/user/settings/token).
