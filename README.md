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

Site on http://localhost:3000, API on http://localhost:8000. The site's
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

Add or upgrade a backend dependency with `uv add <package>`, then refresh
the pip file Render installs from:

```bash
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```

## Deploy on Vercel

The site and the API deploy as two Vercel projects from this repo:

* **Site:** Root Directory `frontend`. Next.js is detected automatically.
* **API:** Root Directory `backend`. Vercel finds the FastAPI `app` in
  `main.py` and installs from `uv.lock`. `backend/vercel.json` allows each
  request the Hobby maximum of 300 s. Set the backend settings below as
  environment variables, plus `FIREBASE_SERVICE_ACCOUNT_JSON`. The in-app
  scheduler switches itself off on Vercel.

The nightly job runs in batches so no request reaches the 300 s limit:
`.github/scripts/run-batched-job.sh` calls `/jobs/run` repeatedly, each
call checking users for about 200 s and returning a `next_cursor` for the
next call.

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
