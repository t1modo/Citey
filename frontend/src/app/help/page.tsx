"use client";

import Link from "next/link";

const IMPORT_EXAMPLES = [
  "2310.06825",
  "https://arxiv.org/abs/2310.06825",
  "10.48550/arXiv.2310.06825",
  "Jane Smith",
  "https://inspirehep.net/authors/1234567",
  "https://dblp.org/pid/12/3456",
];

// ─── Shared mini-components ──────────────────────────────────────────────────

const Badge = ({ children, dim = false }: { children: React.ReactNode; dim?: boolean }) => (
  <span
    className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${
      dim
        ? "border-rule text-muted"
        : "border-rule text-muted"
    }`}
  >
    {children}
  </span>
);

const Pill = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-block rounded bg-ink/10 px-2 py-0.5 font-mono text-xs text-ink">
    {children}
  </span>
);

// ─── Section label ────────────────────────────────────────────────────────────


// ─── Page ────────────────────────────────────────────────────────────────────

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">

      {/* ── Header ── */}
      <div className="mb-14 text-center">
        <h1 className="font-serif text-4xl font-semibold text-ink sm:text-5xl">How Citey works</h1>
        <p className="mt-3 text-base text-muted">
          Everything you need to track your research impact — in one place.
        </p>
        {/* Jump links */}
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {[
            ["#what", "What is Citey?"],
            ["#start", "Getting started"],
            ["#import", "Importing papers"],
            ["#sources", "Data sources"],
            ["#notifications", "Notifications"],
            ["#settings", "Settings"],
          ].map(([href, label]) => (
            <a
              key={href}
              href={href}
              className="rounded-full border border-rule px-3 py-1 text-xs font-medium text-muted transition-colors hover:border-ink/40 hover:text-ink"
            >
              {label}
            </a>
          ))}
        </div>
      </div>

      {/* ── What is Citey ── */}
      <section id="what" className="scroll-mt-6 mb-20">
        <div>
          <div className="surface overflow-hidden p-0">
            <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center">
              <div>
                <h2 className="font-serif mb-1 text-lg font-semibold text-ink">
                  Automated citation monitoring
                </h2>
                <p className="text-sm leading-relaxed text-muted">
                  Citey monitors your research papers across multiple academic databases and emails
                  you the moment a new paper cites your work — so you never miss an impact.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Getting started ── */}
      <section id="start" className="scroll-mt-6 mb-20">
        <div>
          <h2 className="font-serif mb-6 text-2xl font-semibold text-ink">Up and running in minutes</h2>
        </div>
        <div className="flex flex-col gap-6">
          {[
            {
              n: 1,
              title: "Create your free account",
              body: (
                <>
                  Sign up with your email on the{" "}
                  <Link href="/signup" className="text-ink underline hover:text-ink">
                    Sign up
                  </Link>{" "}
                  page. No credit card, no setup fees.
                </>
              ),
            },
            {
              n: 2,
              title: "Import your papers",
              body: (
                <>
                  Click <Pill>Add papers</Pill> on the Dashboard. Paste a DOI, arXiv URL,
                  author profile URL, or your name — Citey resolves everything automatically.
                </>
              ),
            },
            {
              n: 3,
              title: "Receive citation alerts",
              body:
                "Citey scans seven citation databases every day and emails you as soon as a new paper cites your work.",
            },
          ].map(({ n, title, body }, i) => (
            <div key={n}>
              <div className="surface flex gap-4 p-5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-sm font-bold text-paper shadow-lg">
                  {n}
                </div>
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="font-serif text-sm font-semibold text-ink">{title}</h3>
                  </div>
                  <p className="text-sm leading-relaxed text-muted">{body}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Importing papers ── */}
      <section id="import" className="scroll-mt-6 mb-20">
        <div>
          <h2 className="font-serif mb-4 text-2xl font-semibold text-ink">Paste anything. Citey figures it out.</h2>
          {/* Animated mock input */}
          <div className="mb-6 flex items-center gap-2 rounded-xl border border-rule bg-ink/5 px-4 py-3">
            <svg className="h-4 w-4 shrink-0 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
            </svg>
            <span className="flex-1 truncate font-mono text-sm text-ink">{IMPORT_EXAMPLES[0]}</span>
            <span className="shrink-0 rounded-lg bg-ink/10 px-3 py-1 text-xs font-medium text-ink">
              Add
            </span>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-6">
          {[
            {
              title: "arXiv URL or ID",
              example: "2310.06825",
              body: "Citey looks up the paper on Semantic Scholar and shows the author list so you can select yourself and import all your papers.",
              colClass: "sm:col-span-2",
            },
            {
              title: "DOI or doi.org link",
              example: "10.48550/arXiv.2310.06825",
              body: "If your author profile is already linked, the paper is added immediately. Otherwise Citey shows the author list for linking.",
              colClass: "sm:col-span-2",
            },
            {
              title: "Author name",
              example: "Jane Smith",
              body: "Searches OpenAlex and Semantic Scholar in parallel, showing matching profiles with affiliation and h-index. One click to import all.",
              colClass: "sm:col-span-2",
            },
            {
              title: "INSPIRE-HEP profile URL",
              example: "inspirehep.net/authors/1234567",
              body: "Imports all papers from that INSPIRE profile, including JACoW proceedings that other databases miss.",
              colClass: "sm:col-span-3",
            },
            {
              title: "DBLP profile URL",
              example: "dblp.org/pid/12/3456",
              body: "Imports all papers from that DBLP author entry — near-complete ACM and IEEE conference coverage.",
              colClass: "sm:col-span-3",
            },
          ].map(({ title, example, body, colClass }, i) => (
            <div key={title} className={colClass}>
              <div className="surface flex h-full flex-col gap-3 p-5">
                <div className="flex items-center gap-3">
                  <h3 className="font-serif text-sm font-semibold text-ink">{title}</h3>
                </div>
                <Pill>{example}</Pill>
                <p className="text-xs leading-relaxed text-muted">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Data sources ── */}
      <section id="sources" className="scroll-mt-6 mb-20">
        <div>
          <h2 className="font-serif mb-2 text-2xl font-semibold text-ink">Seven databases. One search.</h2>
          <p className="mb-6 text-sm text-muted">
            Citey queries all of these automatically when checking for new citations.
          </p>
        </div>

        {/* Primary sources */}
        <div>
          <p className="mb-2 text-xs font-medium text-muted">Primary sources</p>
        </div>
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          {[
            {
              name: "OpenAlex",
              scale: "~250M works",
              tags: ["Primary", "All fields"],
              body: "The main source for author profiles and citation tracking across all disciplines.",
            },
            {
              name: "Semantic Scholar",
              scale: "~200M works",
              tags: ["Primary", "CS, AI, biology"],
              body: "Strong on CS, AI/ML, and biomedical literature. Also used to resolve arXiv papers.",
            },
          ].map(({ name, scale, tags, body }, i) => (
            <div key={name}>
              <div className="surface flex h-full flex-col gap-2 p-5">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-ink">{name}</span>
                  <span className="ml-auto text-xs text-muted">{scale}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {tags.map((t) => <Badge key={t}>{t}</Badge>)}
                </div>
                <p className="text-xs leading-relaxed text-muted">{body}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Cross-source boosts */}
        <div>
          <p className="mb-2 mt-4 text-xs font-medium text-muted">
            Cross-source boosts{" "}
            <span className="normal-case tracking-normal text-muted">— opt-in per import</span>
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-3">
          {[
            {
              name: "PubMed",
              tags: ["Biomedical"],
              body: "35M NCBI records. Fills in clinical and life-science papers.",
            },
            {
              name: "NASA ADS",
              tags: ["Astrophysics"],
              body: "Covers astronomy, astrophysics, and space-science literature.",
            },
            {
              name: "INSPIRE-HEP",
              tags: ["High-energy and nuclear physics"],
              body: "Canonical database for high-energy physics. The only automated source for JACoW proceedings.",
            },
            {
              name: "DBLP",
              tags: ["Computer science"],
              body: "Near-complete ACM and IEEE conference and journal coverage.",
            },
            {
              name: "Crossref",
              tags: ["DOI resolution"],
              body: "Used as a fallback for DOI metadata when primary sources are missing a record.",
            },
          ].map(({ name, tags, body }, i) => (
            <div key={name} className="w-full sm:w-[calc(50%-6px)] lg:w-[calc(33.333%-8px)]">
              <div className="surface flex h-full flex-col gap-2 p-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-ink">{name}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {tags.map((t) => <Badge key={t} dim>{t}</Badge>)}
                </div>
                <p className="text-xs leading-relaxed text-muted">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Notifications ── */}
      <section id="notifications" className="scroll-mt-6 mb-20">
        <div>
          <h2 className="font-serif mb-6 text-2xl font-semibold text-ink">Know the moment your work is cited</h2>
        </div>

        {/* Mock notification card */}
        <div>
          <div className="surface mb-4 overflow-hidden">
            <div className="p-5">
              <div className="mb-1 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-ink" />
                <p className="text-xs font-semibold text-muted">New citation</p>
              </div>
              <p className="mt-2 text-sm font-medium text-ink">
                "Attention Is All You Need" was cited by
              </p>
              <p className="mt-0.5 text-sm text-ink">
                FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision
              </p>
              <p className="mt-1 text-xs text-muted">Tri Dao and Jay Shah, Stanford University, 2024</p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              title: "Email alerts",
              body: "Rich emails with title, authors, affiliations, and a direct link — toggle in Settings.",
            },
            {
              title: "New publication alerts",
              body: "Auto-notified when a new paper from your author profile is added to your tracked list.",
            },
            {
              title: "Custom email address",
              body: "Send alerts to any address. Defaults to your account email — override in Settings.",
            },
          ].map(({ title, body }) => (
            <div key={title}>
              <div className="surface flex h-full flex-col gap-2 p-5">
                <p className="text-sm font-semibold text-ink">{title}</p>
                <p className="text-xs leading-relaxed text-muted">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Settings ── */}
      <section id="settings" className="scroll-mt-6 mb-20">
        <div>
          <h2 className="font-serif mb-6 text-2xl font-semibold text-ink">Your account, your way</h2>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {[
            {
              title: "Notification email",
              body: "Override the address that receives citation alerts with any email you prefer.",
            },
            {
              title: "Google Scholar URL",
              body: "Store a link to your Scholar profile for reference — never scraped or used for data.",
            },
            {
              title: "Tracked papers",
              body: "Browse, search, and remove individual papers from your tracked list at any time.",
            },
            {
              title: "Change linked author",
              body: "Re-link a different author profile. This resets your library and re-imports from scratch.",
            },
          ].map(({ title, body }) => (
            <div key={title}>
              <div className="surface flex gap-4 p-5">
                <div>
                  <p className="text-sm font-semibold text-ink">{title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">{body}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── FAQ CTA ── */}
      <div>
        <div className="surface overflow-hidden text-center">
          <div className="p-8">
            <h2 className="font-serif mb-2 text-xl font-semibold text-ink">Still have questions?</h2>
            <p className="mb-1 text-sm text-muted">
              Common questions about accuracy, privacy, and how it all works.
            </p>
            <p className="mb-5 text-sm text-muted">
              Or email us at{" "}
              <a
                href="mailto:support@citey.email"
                className="text-ink underline hover:text-ink"
              >
                support@citey.email
              </a>
              .
            </p>
            <Link
              href="/faq"
              className="inline-block rounded-xl bg-ink px-6 py-2.5 text-sm font-semibold text-paper shadow-xl shadow-ink/10 transition-all hover:scale-105 hover:bg-ink-soft"
            >
              Read the FAQ
            </Link>
          </div>
        </div>
      </div>

    </div>
  );
}
