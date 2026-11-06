# Citey

Get an email when a new paper cites yours. Try it at [citey.email](https://www.citey.email/).

## What it does

* Add papers by DOI, or import your whole list from an OpenAlex, Semantic Scholar, INSPIRE or DBLP profile.
* Every night Citey checks OpenAlex, Semantic Scholar, OpenCitations and Europe PMC for new citing papers and emails you the title, authors and affiliations.
* New papers on your linked profile are added automatically.
* Export every citation as BibTeX.

## Stack

* **Frontend:** Next.js, Tailwind, Firebase Auth, PostHog analytics. Hosted on Vercel.
* **Backend:** FastAPI, Firestore, Resend for email. Hosted on Render.
* **Nightly job:** GitHub Actions calls `/jobs/run`.
* **Data:** OpenAlex and Semantic Scholar for citations. Crossref, PubMed, NASA ADS, INSPIRE and DBLP for imports and DOI lookups.

## Run locally

### With Docker

```bash
cp backend/.env.example backend/.env           # Firebase service account JSON, secrets
cp frontend/.env.example frontend/.env.local   # Firebase web config
docker compose up --build
```

Site on http://localhost:3000, API on http://localhost:8000/api. The site's
Firebase config is compiled in at build time, so rebuild after editing
`frontend/.env.local`.

### Without Docker

The backend uses [uv](https://docs.astral.sh/uv/).

```bash
# API on :8000
cd backend && uv sync && uv run uvicorn main:app --reload

# Site on :3000
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Fill `frontend/.env.local` with your Firebase web config. Run the backend
tests with `cd backend && uv run pytest`.

Add or upgrade a backend dependency with `uv add <package>`, which updates
`pyproject.toml` and `uv.lock`.

## Deploy on Render

The backend installs from `uv.lock`. `backend/requirements.txt` mirrors the
direct dependencies only so the existing Render service, whose build runs
`pip install -r requirements.txt`, keeps deploying until it is retired; delete
it then. To install from the lock on Render instead (Root Directory `backend`):

* **Build Command:** `pip install uv && uv sync --locked --no-dev`
* **Start Command:** `.venv/bin/uvicorn main:app --host 0.0.0.0 --port $PORT`

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

The API runs as one function with Hobby's 300 s limit. The nightly job
stays under it by running in batches: `.github/scripts/run-batched-job.sh`
calls `/api/jobs/run` repeatedly, each call checking users for about 200 s
and returning a `next_cursor` for the next call. The in-app scheduler
switches itself off on Vercel.

While the API still runs on its own host, requests to its old paths without
`/api` get a 308 to the `/api` path, so a site build still calling the old
address keeps working during the move. Links in emails sent before the move
point at `api.citey.email` and stop working once that domain is retired.

## Backend settings

Required in production:

* `CRON_SECRET`: shared secret the nightly job sends.
* `TOKEN_SECRET`: signs unsubscribe and confirmation links.
* `API_URL`: public API address used in email links.
* `ALLOWED_ORIGINS`: comma separated site addresses allowed to call the API.

Optional:

* `S2_API_KEY`: Semantic Scholar key. Avoids night time rate limits. [Request one free](https://www.semanticscholar.org/product/api).
* `OPENALEX_API_KEY`: OpenAlex key. Keyless use has a small daily allowance. Free from [openalex.org](https://openalex.org) after signing in.
* `OPENCITATIONS_ACCESS_TOKEN`: OpenCitations token. Raises its rate limit. [Get one free](https://opencitations.net/accesstoken).
* `ADS_API_KEY`: NASA ADS token for astronomy imports. [Get one free](https://ui.adsabs.harvard.edu/user/settings/token).
