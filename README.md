# Citey

Get an email when a new paper cites yours. Try it at [citey.email](https://www.citey.email/).

## What it does

* Add papers by DOI, or import your whole list from an OpenAlex, Semantic Scholar, INSPIRE or DBLP profile.
* Every night Citey checks OpenAlex and Semantic Scholar for new citing papers and emails you the title, authors and affiliations.
* New papers on your linked profile are added automatically.
* Export every citation as BibTeX.

## Stack

* **Frontend:** Next.js, Tailwind, Firebase Auth, PostHog analytics. Hosted on Vercel.
* **Backend:** FastAPI, Firestore, Resend for email. Hosted on Render.
* **Nightly job:** GitHub Actions calls `/jobs/run`.
* **Data:** OpenAlex and Semantic Scholar for citations. Crossref, PubMed, NASA ADS, INSPIRE and DBLP for imports and DOI lookups.

## Run locally

```bash
# API on :8000
cd backend && pip install -r requirements.txt && uvicorn main:app

# Site on :3000
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Fill `frontend/.env.local` with your Firebase web config.

## Backend settings

Required in production:

* `CRON_SECRET`: shared secret the nightly job sends.
* `TOKEN_SECRET`: signs unsubscribe and confirmation links.
* `API_URL`: public API address used in email links.
* `ALLOWED_ORIGINS`: comma separated site addresses allowed to call the API.

Optional:

* `S2_API_KEY`: Semantic Scholar key. Avoids night time rate limits. [Request one free](https://www.semanticscholar.org/product/api).
* `OPENALEX_API_KEY`: OpenAlex key. Keyless use has a small daily allowance. [Get one free](https://openalex.org/settings/api).
* `ADS_API_KEY`: NASA ADS token for astronomy imports. [Get one free](https://ui.adsabs.harvard.edu/user/settings/token).
