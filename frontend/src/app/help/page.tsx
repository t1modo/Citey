"use client";

import Link from "next/link";
import ScrollReveal from "@/components/ScrollReveal";
import TypewriterCycle from "@/components/TypewriterCycle";

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
        ? "border-white/10 text-gray-600"
        : "border-white/15 text-gray-400"
    }`}
  >
    {children}
  </span>
);

const Pill = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-block rounded bg-white/10 px-2 py-0.5 font-mono text-xs text-gray-200">
    {children}
  </span>
);

// ─── Section label ────────────────────────────────────────────────────────────

const SectionLabel = ({ children }: { children: React.ReactNode }) => (
  <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-600">
    {children}
  </p>
);

// ─── Page ────────────────────────────────────────────────────────────────────

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">

      {/* ── Header ── */}
      <ScrollReveal className="mb-14 text-center">
        <h1 className="text-4xl font-bold text-white sm:text-5xl">How Citey works</h1>
        <p className="mt-3 text-base text-gray-400">
          Everything you need to track your research impact — in one place.
        </p>
        {/* Jump links */}
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {[
            ["#what", "What is Citey?"],
            ["#start", "Getting Started"],
            ["#import", "Importing Papers"],
            ["#sources", "Data Sources"],
            ["#notifications", "Notifications"],
            ["#settings", "Settings"],
          ].map(([href, label]) => (
            <a
              key={href}
              href={href}
              className="rounded-full border border-white/10 px-3 py-1 text-xs font-medium text-gray-400 transition-colors hover:border-white/30 hover:text-white"
            >
              {label}
            </a>
          ))}
        </div>
      </ScrollReveal>

      {/* ── What is Citey ── */}
      <section id="what" className="scroll-mt-6 mb-20">
        <ScrollReveal>
          <SectionLabel>What is Citey?</SectionLabel>
          <div className="glass-card overflow-hidden p-0">
            <div className="h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
            <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/8 text-3xl">
                📡
              </div>
              <div>
                <h2 className="mb-1 text-lg font-semibold text-white">
                  Automated citation monitoring
                </h2>
                <p className="text-sm leading-relaxed text-gray-400">
                  Citey monitors your research papers across multiple academic databases and emails
                  you the moment a new paper cites your work — so you never miss an impact.
                </p>
              </div>
            </div>
            {/* Stats row */}
            <div className="grid grid-cols-3 divide-x divide-white/5 border-t border-white/5">
              {[
                { value: "7", label: "databases" },
                { value: "Daily", label: "citation checks" },
                { value: "Free", label: "always" },
              ].map(({ value, label }) => (
                <div key={label} className="flex flex-col items-center py-4">
                  <span className="text-xl font-bold text-white">{value}</span>
                  <span className="mt-0.5 text-xs text-gray-500">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </ScrollReveal>
      </section>

      {/* ── Getting Started ── */}
      <section id="start" className="scroll-mt-6 mb-20">
        <ScrollReveal>
          <SectionLabel>Getting Started</SectionLabel>
          <h2 className="mb-6 text-2xl font-bold text-white">Up and running in minutes</h2>
        </ScrollReveal>
        <div className="flex flex-col gap-6">
          {[
            {
              n: 1,
              icon: "✉️",
              title: "Create your free account",
              body: (
                <>
                  Sign up with your email on the{" "}
                  <Link href="/signup" className="text-gray-300 underline hover:text-white">
                    Sign Up
                  </Link>{" "}
                  page. No credit card, no setup fees.
                </>
              ),
            },
            {
              n: 2,
              icon: "📥",
              title: "Import your papers",
              body: (
                <>
                  Click <Pill>Add Papers</Pill> on the Dashboard. Paste a DOI, arXiv URL,
                  author profile URL, or your name — Citey resolves everything automatically.
                </>
              ),
            },
            {
              n: 3,
              icon: "🔔",
              title: "Receive citation alerts",
              body:
                "Citey scans seven citation databases every day and emails you as soon as a new paper cites your work.",
            },
          ].map(({ n, icon, title, body }, i) => (
            <ScrollReveal key={n} delay={i * 0.09}>
              <div className="glass-card flex gap-4 p-5 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-sm font-bold text-gray-950 shadow-lg">
                  {n}
                </div>
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-base">{icon}</span>
                    <h3 className="text-sm font-semibold text-white">{title}</h3>
                  </div>
                  <p className="text-sm leading-relaxed text-gray-400">{body}</p>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ── Importing Papers ── */}
      <section id="import" className="scroll-mt-6 mb-20">
        <ScrollReveal>
          <SectionLabel>Importing Papers</SectionLabel>
          <h2 className="mb-4 text-2xl font-bold text-white">Paste anything. Citey figures it out.</h2>
          {/* Animated mock input */}
          <div className="mb-6 flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3">
            <svg className="h-4 w-4 shrink-0 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
            </svg>
            <TypewriterCycle
              phrases={IMPORT_EXAMPLES}
              className="flex-1 text-sm text-gray-300"
            />
            <span className="shrink-0 rounded-lg bg-white/10 px-3 py-1 text-xs font-medium text-gray-400">
              Add
            </span>
          </div>
        </ScrollReveal>

        <div className="grid gap-3 sm:grid-cols-6">
          {[
            {
              icon: "📄",
              title: "arXiv URL or ID",
              example: "2310.06825",
              body: "Citey looks up the paper on Semantic Scholar and shows the author list so you can select yourself and import all your papers.",
              colClass: "sm:col-span-2",
            },
            {
              icon: "🔗",
              title: "DOI or doi.org link",
              example: "10.48550/arXiv.2310.06825",
              body: "If your author profile is already linked, the paper is added immediately. Otherwise Citey shows the author list for linking.",
              colClass: "sm:col-span-2",
            },
            {
              icon: "👤",
              title: "Author name",
              example: "Jane Smith",
              body: "Searches OpenAlex and Semantic Scholar in parallel, showing matching profiles with affiliation and h-index. One click to import all.",
              colClass: "sm:col-span-2",
            },
            {
              icon: "⚡",
              title: "INSPIRE-HEP profile URL",
              example: "inspirehep.net/authors/1234567",
              body: "Imports all papers from that INSPIRE profile, including JACoW proceedings that other databases miss.",
              colClass: "sm:col-span-3",
            },
            {
              icon: "💻",
              title: "DBLP profile URL",
              example: "dblp.org/pid/12/3456",
              body: "Imports all papers from that DBLP author entry — near-complete ACM and IEEE conference coverage.",
              colClass: "sm:col-span-3",
            },
          ].map(({ icon, title, example, body, colClass }, i) => (
            <ScrollReveal key={title} delay={i * 0.07} className={colClass}>
              <div className="glass-card flex h-full flex-col gap-3 p-5 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/8 text-lg">
                    {icon}
                  </div>
                  <h3 className="text-sm font-semibold text-white">{title}</h3>
                </div>
                <Pill>{example}</Pill>
                <p className="text-xs leading-relaxed text-gray-400">{body}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ── Data Sources ── */}
      <section id="sources" className="scroll-mt-6 mb-20">
        <ScrollReveal>
          <SectionLabel>Data Sources</SectionLabel>
          <h2 className="mb-2 text-2xl font-bold text-white">Seven databases. One search.</h2>
          <p className="mb-6 text-sm text-gray-400">
            Citey queries all of these automatically when checking for new citations.
          </p>
        </ScrollReveal>

        {/* Primary sources */}
        <ScrollReveal delay={0.05}>
          <p className="mb-2 text-xs font-medium uppercase tracking-widest text-gray-600">Primary sources</p>
        </ScrollReveal>
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          {[
            {
              name: "OpenAlex",
              icon: "🌐",
              scale: "~250M works",
              tags: ["Primary", "All Fields"],
              body: "The main source for author profiles and citation tracking across all disciplines.",
            },
            {
              name: "Semantic Scholar",
              icon: "🧠",
              scale: "~200M works",
              tags: ["Primary", "CS · AI · Bio"],
              body: "Strong on CS, AI/ML, and biomedical literature. Also used to resolve arXiv papers.",
            },
          ].map(({ name, icon, scale, tags, body }, i) => (
            <ScrollReveal key={name} delay={0.1 + i * 0.07}>
              <div className="glass-card flex h-full flex-col gap-2 p-5 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{icon}</span>
                  <span className="font-semibold text-white">{name}</span>
                  <span className="ml-auto text-xs text-gray-600">{scale}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {tags.map((t) => <Badge key={t}>{t}</Badge>)}
                </div>
                <p className="text-xs leading-relaxed text-gray-400">{body}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>

        {/* Cross-source boosts */}
        <ScrollReveal delay={0.15}>
          <p className="mb-2 mt-4 text-xs font-medium uppercase tracking-widest text-gray-600">
            Cross-source boosts{" "}
            <span className="normal-case tracking-normal text-gray-700">— opt-in per import</span>
          </p>
        </ScrollReveal>
        <div className="flex flex-wrap justify-center gap-3">
          {[
            {
              name: "PubMed",
              icon: "🧬",
              tags: ["Biomedical"],
              body: "35M NCBI records. Fills in clinical and life-science papers.",
            },
            {
              name: "NASA ADS",
              icon: "🔭",
              tags: ["Astrophysics · Space"],
              body: "Covers astronomy, astrophysics, and space-science literature.",
            },
            {
              name: "INSPIRE-HEP",
              icon: "⚛️",
              tags: ["HEP · Nuclear"],
              body: "Canonical database for high-energy physics. The only automated source for JACoW proceedings.",
            },
            {
              name: "DBLP",
              icon: "🖥️",
              tags: ["CS · ACM · IEEE"],
              body: "Near-complete ACM and IEEE conference and journal coverage.",
            },
            {
              name: "Crossref",
              icon: "🔀",
              tags: ["DOI resolution"],
              body: "Used as a fallback for DOI metadata when primary sources are missing a record.",
            },
          ].map(({ name, icon, tags, body }, i) => (
            <ScrollReveal key={name} delay={0.2 + i * 0.06} className="w-full sm:w-[calc(50%-6px)] lg:w-[calc(33.333%-8px)]">
              <div className="glass-card flex h-full flex-col gap-2 p-4 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex items-center gap-2">
                  <span className="text-base">{icon}</span>
                  <span className="text-sm font-semibold text-white">{name}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {tags.map((t) => <Badge key={t} dim>{t}</Badge>)}
                </div>
                <p className="text-xs leading-relaxed text-gray-500">{body}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ── Notifications ── */}
      <section id="notifications" className="scroll-mt-6 mb-20">
        <ScrollReveal>
          <SectionLabel>Notifications</SectionLabel>
          <h2 className="mb-6 text-2xl font-bold text-white">Know the moment your work is cited</h2>
        </ScrollReveal>

        {/* Mock notification card */}
        <ScrollReveal delay={0.06}>
          <div className="glass-card mb-4 overflow-hidden">
            <div className="h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
            <div className="p-5">
              <div className="mb-1 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-white" />
                <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">New citation</p>
              </div>
              <p className="mt-2 text-sm font-medium text-white">
                "Attention Is All You Need" was cited by
              </p>
              <p className="mt-0.5 text-sm text-gray-300">
                FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision
              </p>
              <p className="mt-1 text-xs text-gray-500">Tri Dao, Jay Shah · 2024 · Stanford University</p>
            </div>
          </div>
        </ScrollReveal>

        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              icon: "📧",
              title: "Email alerts",
              body: "Rich emails with title, authors, affiliations, and a direct link — toggle in Settings.",
            },
            {
              icon: "📰",
              title: "New publication alerts",
              body: "Auto-notified when a new paper from your author profile is added to your tracked list.",
            },
            {
              icon: "📬",
              title: "Custom email address",
              body: "Send alerts to any address. Defaults to your account email — override in Settings.",
            },
          ].map(({ icon, title, body }, i) => (
            <ScrollReveal key={title} delay={0.1 + i * 0.07}>
              <div className="glass-card flex h-full flex-col gap-2 p-5 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/8 text-lg">
                  {icon}
                </div>
                <p className="text-sm font-semibold text-white">{title}</p>
                <p className="text-xs leading-relaxed text-gray-400">{body}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ── Settings ── */}
      <section id="settings" className="scroll-mt-6 mb-20">
        <ScrollReveal>
          <SectionLabel>Settings</SectionLabel>
          <h2 className="mb-6 text-2xl font-bold text-white">Your account, your way</h2>
        </ScrollReveal>

        <div className="grid gap-3 sm:grid-cols-2">
          {[
            {
              icon: "📬",
              title: "Notification email",
              body: "Override the address that receives citation alerts with any email you prefer.",
            },
            {
              icon: "🎓",
              title: "Google Scholar URL",
              body: "Store a link to your Scholar profile for reference — never scraped or used for data.",
            },
            {
              icon: "📋",
              title: "Tracked Works",
              body: "Browse, search, and remove individual papers from your tracked list at any time.",
            },
            {
              icon: "🔄",
              title: "Change linked author",
              body: "Re-link a different author profile. This resets your library and re-imports from scratch.",
            },
          ].map(({ icon, title, body }, i) => (
            <ScrollReveal key={title} delay={i * 0.07}>
              <div className="glass-card flex gap-4 p-5 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/8 text-lg">
                  {icon}
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-gray-400">{body}</p>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ── FAQ CTA ── */}
      <ScrollReveal>
        <div className="glass-card overflow-hidden text-center">
          <div className="h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
          <div className="p-8">
            <div className="mb-3 flex justify-center text-3xl">💬</div>
            <h2 className="mb-2 text-xl font-bold text-white">Still have questions?</h2>
            <p className="mb-1 text-sm text-gray-400">
              Common questions about accuracy, privacy, and how it all works.
            </p>
            <p className="mb-5 text-sm text-gray-400">
              Or email us at{" "}
              <a
                href="mailto:support@citey.email"
                className="text-gray-300 underline hover:text-white"
              >
                support@citey.email
              </a>
              .
            </p>
            <Link
              href="/faq"
              className="inline-block rounded-xl bg-white px-6 py-2.5 text-sm font-semibold text-gray-950 shadow-xl shadow-white/10 transition-all hover:scale-105 hover:bg-gray-100"
            >
              View FAQ →
            </Link>
          </div>
        </div>
      </ScrollReveal>

    </div>
  );
}
