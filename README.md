# Citey

Get email notifications whenever one of your papers is cited by a new work.

**Want to try it out? Visit [citey.app](https://citey.app)**

---

## What it does

Citey lets researchers track citations to their published papers. Add a paper by DOI, and Citey will notify you by email whenever a new citation is detected — powered by [OpenAlex](https://openalex.org) and [Crossref](https://www.crossref.org).

---

## Tech Stack

**Frontend**
- Next.js 16 (React 19, TypeScript)
- Tailwind CSS, Framer Motion
- Firebase Auth

**Backend**
- FastAPI (Python 3.11+)
- Firebase Firestore
- Resend (transactional email)
- Deployed on Railway

