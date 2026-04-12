# Citey

Get email notifications whenever one of your papers is cited by a new work.

**Want to try it out? Visit [citey.email](https://www.citey.email/)**

---

## What it does

Citey lets researchers track citations to their published papers. Add a paper by DOI, and Citey will notify you by email whenever a new citation is detected. Citation data is drawn from multiple sources — OpenAlex, Semantic Scholar, PubMed, NASA ADS, INSPIRE-HEP, and DBLP — giving broad coverage across disciplines, publishers, and conference proceedings.

You can bulk-import your entire publication list by author profile. Search by name (queried in parallel across OpenAlex and Semantic Scholar), enter a paper DOI to find co-authors, or paste a profile URL directly from INSPIRE-HEP or DBLP. After import, Citey cross-references all six sources to maximize coverage. Duplicate detection and merge prompts handle cases where the same author appears under multiple profiles.

Citey also automatically discovers new publications from your linked author profile and adds them to your tracking list, so you don't have to add new papers manually.

---

## Tech Stack

### Frontend

**[Next.js](https://nextjs.org)** — React framework powering the entire frontend. Built with the App Router, TypeScript, and server/client component separation.

**[Tailwind CSS](https://tailwindcss.com)** — Utility-first CSS framework used for all styling and layout throughout the app.

**[Framer Motion](https://www.framer.com/motion)** — Handles UI animations, including scroll reveals, transitions, and interactive card effects.

**[Firebase Authentication](https://firebase.google.com/products/auth)** — Manages user sign-up, sign-in, and email verification. Passwords are hashed and stored entirely within Firebase — the application never handles raw credentials.

**[Vercel](https://vercel.com)** — Hosts and deploys the Next.js frontend. Provides automatic deployments on every push and global CDN delivery.

---

### Backend

**[FastAPI](https://fastapi.tiangolo.com)** — Python web framework serving the REST API. Handles all business logic: tracking works, querying citation sources, writing notifications, and triggering email delivery.

**[Firebase Firestore](https://firebase.google.com/products/firestore)** — NoSQL cloud database storing user profiles, tracked works, and citation notifications. Each user's data lives under a `users/{uid}` document with subcollections for works and notifications.

**[Firebase Admin SDK](https://firebase.google.com/docs/admin/setup)** — Used server-side to verify user identity tokens on every API request and to manage user account data without exposing credentials to the client.

**[Resend](https://resend.com)** — Transactional email provider used to deliver citation notification emails and digest summaries. Emails are rendered from Jinja2 HTML templates and sent via the Resend Python SDK.

**[Render](https://render.com)** — Hosts the FastAPI backend as a web service. A separate Render Cron job hits the `/jobs/run` endpoint on a schedule to trigger citation checks.

---

### Data Sources

**[OpenAlex](https://openalex.org)** — Primary citation data source. An open, comprehensive index of scholarly works used to resolve DOIs to paper metadata and fetch lists of citing papers. Also the primary source for author profile lookup and publication auto-sync.

**[Semantic Scholar](https://www.semanticscholar.org)** — Secondary citation source queried in parallel with OpenAlex to broaden coverage. Also powers paper-DOI author lookup and is included in parallel author name searches during bulk import.

**[Crossref](https://www.crossref.org)** — Used for DOI resolution and metadata enrichment. Serves as the first step in the DOI resolution fallback chain (Crossref → OpenAlex → DataCite).

**[PubMed](https://pubmed.ncbi.nlm.nih.gov)** — NCBI's biomedical literature database. Queried during bulk import to supplement coverage for life-science and clinical papers.

**[NASA ADS](https://ui.adsabs.harvard.edu)** — Astrophysics Data System for space science and astronomy papers. Requires a free personal API token; gracefully skipped if not configured.

**[INSPIRE-HEP](https://inspirehep.net)** — High-energy physics literature database. Supports direct profile URL import and is queried during bulk import for physics and accelerator-science papers. No API key required.

**[DBLP](https://dblp.org)** — Computer science bibliography covering ACM, IEEE, and major CS conference proceedings. Supports direct profile URL import. No API key required.