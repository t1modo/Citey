# Citey — Citation Alerts for Researchers

Get email notifications whenever one of your papers is cited by a new work.
Uses [OpenAlex](https://openalex.org) + [Crossref](https://www.crossref.org) as authoritative data sources.
Tracks works by DOI.

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