# Citey

Get email notifications whenever one of your papers is cited by a new work.

**Want to try it out? Visit [citey.email](https://www.citey.email/)**

---

## What it does

Citey lets researchers track citations to their published papers. Add a paper by DOI, and Citey will notify you by email whenever a new citation is detected. Citation data is sourced from [OpenAlex](https://openalex.org), [Semantic Scholar](https://www.semanticscholar.org), and [Crossref](https://www.crossref.org), giving broad coverage across disciplines and publishers.

You can also bulk-import your entire publication list by searching for your author profile — by name (queried in parallel across OpenAlex and Semantic Scholar) or by entering a paper DOI to find co-authors. Citey handles duplicate detection and merge prompts if the same author appears under multiple profiles.

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

**[APScheduler](https://apscheduler.readthedocs.io)** — In-process job scheduler that runs the citation check job on a recurring schedule, querying OpenAlex and Semantic Scholar for new citing papers.

**[Render](https://render.com)** — Hosts the FastAPI backend as a web service. A separate Render Cron job hits the `/jobs/run` endpoint on a schedule to trigger citation checks without keeping the scheduler process alive indefinitely.

---

### Data Sources

**[OpenAlex](https://openalex.org)** — Primary citation data source. An open, comprehensive index of scholarly works used to resolve DOIs to paper metadata and fetch lists of citing papers.

**[Crossref](https://www.crossref.org)** — Used for DOI resolution and metadata enrichment. Crossref maintains the canonical DOI registry for academic publishing, making it reliable for identifying and validating papers.

**[Semantic Scholar](https://www.semanticscholar.org)** — Secondary citation source used alongside OpenAlex to broaden coverage across disciplines. Also powers the paper-DOI author lookup (finding a paper's co-authors by DOI) and is queried in parallel with OpenAlex during author name searches for the bulk-import feature.
