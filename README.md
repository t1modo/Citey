# Citey — Citation Alerts for Researchers

Get email notifications whenever one of your papers is cited by a new work.
Uses [OpenAlex](https://openalex.org) + [Crossref](https://www.crossref.org) as authoritative data sources.
Tracks works by DOI, identifies authors by ORCID when available.

---

## Project structure

```
Citey/
├── frontend/        Next.js 15 · TypeScript · Tailwind CSS
└── backend/         Python FastAPI · Firestore · Resend · APScheduler
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 20 LTS or later |
| Python | 3.11 or later |
| Firebase project | Auth + Firestore enabled |
| Resend account | Free tier is fine |

---

## Local development

### 1. Clone and enter the repo

```bash
git clone https://github.com/your-username/citey.git
cd citey
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the env template and fill in your values:

```bash
cp .env.example .env
```

**Required `.env` values:**

| Variable | Description |
|----------|-------------|
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full JSON string from Firebase → Project Settings → Service Accounts |
| `RESEND_API_KEY` | From resend.com → API Keys |
| `CRON_SECRET` | Any random string — used to protect the `/jobs/run` endpoint |

Start the API server:

```bash
uvicorn main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

Run backend tests:

```bash
pytest
```

Run a sample citation-detection dry-run for any DOI:

```bash
python scripts/run_sample_job.py 10.1145/3292500.3330701
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

Copy the env template:

```bash
cp .env.local.example .env.local
```

Fill in your Firebase web app config from Firebase Console → Project Settings → Your apps.
Set `NEXT_PUBLIC_API_URL=http://localhost:8000`.

Start the dev server:

```bash
npm run dev
```

App: <http://localhost:3000>

---

## Environment variables reference

### Backend (`backend/.env`)

```
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
# Or use a file path instead:
# FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json

RESEND_API_KEY=re_...
EMAIL_FROM_ADDRESS=notifications@citey.app
EMAIL_FROM_NAME=Citey

APP_NAME=Citey
APP_URL=https://citey.app
SUPPORT_EMAIL=support@citey.app

CRON_SECRET=strong-random-secret
SCHEDULER_INTERVAL_HOURS=24
ALLOWED_ORIGINS=https://citey.app
```

### Frontend (`frontend/.env.local`)

```
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

---

## Firestore data model

```
users/{uid}
  displayName, email, orcid, notificationEmail, notifyEnabled, createdAt

  trackedWorks/{workId}
    doi, openalex_id, title, authors[], year, addedAt, lastCheckedAt

  notifications/{notificationId}   (id = "{citedWorkId}__{citingWorkId}")
    citedWorkId, citedWorkTitle
    citingWorkId, citingWorkTitle, citingWorkDoi, citingWorkUrl
    citingAuthors[], citingAffiliations[], citingYear
    seen, createdAt
```

---

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | Health check |
| GET | `/profile` | Bearer | Get user profile |
| PUT | `/profile` | Bearer | Update profile / preferences |
| GET | `/works` | Bearer | List tracked works |
| POST | `/works` | Bearer | Add a work by DOI |
| DELETE | `/works/{id}` | Bearer | Remove a tracked work |
| GET | `/notifications` | Bearer | Recent notifications (50) |
| POST | `/notifications/{id}/seen` | Bearer | Mark notification seen |
| POST | `/jobs/run` | Bearer or X-Cron-Secret | Trigger citation job |
| POST | `/jobs/email-test` | Bearer | Send test email |

---

## Email templates

Templates live in `backend/templates/email/`:

- `base.html` — base layout (teal/indigo header, footer with unsubscribe link)
- `citation.html` — per-notification citation card (Jinja2, extends base)
- `citation.txt` — plain-text fallback

Edit these files directly. Re-deploy the backend to pick up changes.
Config values (`APP_NAME`, `APP_URL`, `SUPPORT_EMAIL`) are injected from environment variables.

---

## Deployment — Option A: Vercel + Render *(default)*

### Frontend → Vercel

1. Push the repo to GitHub.
2. Import the repo in [Vercel](https://vercel.com). Set the **Root Directory** to `frontend`.
3. Add all `NEXT_PUBLIC_*` environment variables in Vercel's project settings.
4. Deploy.

### Backend → Render (web service)

1. In [Render](https://render.com), create a **New Web Service** pointed at your repo.
2. Set **Root Directory** to `backend`.
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add all backend environment variables in Render's environment section.
6. Set `APP_URL` to your Vercel URL and `ALLOWED_ORIGINS` to your Vercel URL.

### Scheduler → Render Cron Job

1. In Render, create a **New Cron Job** in the same service.
2. **Schedule:** `0 6 * * *` (daily at 06:00 UTC)
3. **Command:**
   ```
   curl -X POST https://your-backend.onrender.com/jobs/run \
     -H "X-Cron-Secret: $CRON_SECRET" \
     -H "Content-Type: application/json" \
     -d '{"dry_run": false}'
   ```
4. Add `CRON_SECRET` to the cron job's environment.

> **Note:** APScheduler still runs inside the web service process for additional in-process scheduling. The Render Cron Job is the authoritative daily trigger.

---

## Deployment — Option B: Vercel + Google Cloud Run

### Frontend → Vercel
Same as Option A.

### Backend → Cloud Run

Create a `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Deploy:

```bash
gcloud run deploy citey-backend \
  --source backend/ \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "RESEND_API_KEY=...,CRON_SECRET=..."
```

### Scheduler → Cloud Scheduler

```bash
gcloud scheduler jobs create http citey-daily \
  --schedule="0 6 * * *" \
  --uri="https://your-cloud-run-url/jobs/run" \
  --message-body='{"dry_run":false}' \
  --headers="Content-Type=application/json,X-Cron-Secret=YOUR_SECRET" \
  --time-zone="UTC"
```

---

## Privacy

- Only the data you explicitly provide is stored (email, ORCID, DOIs).
- Citation metadata is fetched from public APIs (OpenAlex, Crossref) — no scraping.
- Notification history is stored to prevent duplicate emails.
- You can delete your account and all data from Settings → Danger Zone.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Follow the local dev steps above.
3. Run `pytest` (backend) and `npm run lint` (frontend) before opening a PR.
