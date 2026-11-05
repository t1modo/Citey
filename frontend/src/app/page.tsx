"use client";

import Link from "next/link";
import Logo from "@/components/Logo";
import ScrollReveal from "@/components/ScrollReveal";
import HeroDemo from "@/components/HeroDemo";
import CitationField from "@/components/citation-field/CitationField";
import { useAuth } from "@/contexts/AuthContext";

const SOURCES = ["OpenAlex", "Semantic Scholar", "Crossref", "PubMed", "INSPIRE-HEP", "DBLP", "NASA ADS"];

// Written like a reference list: numbered entries with a "source" line.
const references = [
  {
    title: "Seven indexes, checked every night",
    body: "One citing paper can show up in Semantic Scholar weeks before OpenAlex, or only in INSPIRE. Citey queries all seven and merges the results, so you hear about it once, from whichever saw it first.",
    meta: SOURCES.join(" · "),
  },
  {
    title: "An email with the paper, not just a count",
    body: "Each alert carries the citing paper's title, authors, affiliations and year, with a link straight to it. No dashboard to remember to check.",
    meta: "Daily digest · one-click unsubscribe",
  },
  {
    title: "Your whole bibliography in one step",
    body: "Link an OpenAlex, INSPIRE-HEP or DBLP profile, or search by name, and every paper is imported. New papers you publish are picked up each week.",
    meta: "DOI · arXiv URL · author profile",
  },
  {
    title: "Preprints and published versions, merged",
    body: "The arXiv preprint and the journal version of the same paper are recognised as one work, so it is tracked once and you aren't alerted twice.",
    meta: "Title matching · DOI normalisation",
  },
  {
    title: "Export what you've collected",
    body: "Download every citing paper as BibTeX for a grant report, a tenure file or your CV.",
    meta: "citey-citations.bib",
  },
];

const steps = [
  { title: "Create an account", body: "Email and password. No card." },
  { title: "Add your papers", body: "Paste a DOI or arXiv link, or link an author profile to import everything." },
  { title: "We check nightly", body: "Every tracked paper is checked against seven citation indexes." },
  { title: "You get the email", body: "New citing papers land in your inbox with full details and a link." },
];

export default function HomePage() {
  const { user } = useAuth();
  const ctaHref = user ? "/dashboard" : "/signup";

  return (
    <div className="flex flex-col">
      {/* ─── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative isolate flex min-h-[calc(100svh-4rem)] items-center overflow-hidden border-b border-paper/10">
        <CitationField className="-z-10" />
        {/* keep the headline legible over the field */}
        <div className="pointer-events-none absolute inset-y-0 left-0 -z-10 w-full bg-gradient-to-r from-ink via-ink/85 to-transparent md:w-[62%]" />

        <div className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="max-w-xl">
            <p className="mb-6 font-mono text-[11px] uppercase tracking-[0.18em] text-paper/50">
              Citation alerts for researchers
            </p>
            <h1 className="mb-6 text-balance font-serif text-5xl leading-[0.98] tracking-[-0.01em] text-paper sm:text-7xl">
              Know the moment your work is <em className="text-signal">cited</em>.
            </h1>
            <p className="mb-9 max-w-md text-lg leading-relaxed text-paper/65">
              Citey checks seven citation indexes every night and emails you when a new
              paper references yours.
            </p>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
              <Link
                href={ctaHref}
                className="rounded-md bg-signal px-6 py-3 text-[15px] font-semibold text-ink transition-colors hover:bg-signal-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal"
              >
                {user ? "Open your dashboard" : "Start tracking, free"}
              </Link>
              <a
                href="#how"
                className="font-mono text-xs uppercase tracking-[0.14em] text-paper/55 underline decoration-paper/20 underline-offset-4 transition-colors hover:text-paper hover:decoration-paper/60"
              >
                How it works
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Product ──────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-24 sm:px-6 lg:px-8">
        <ScrollReveal className="mb-12 grid gap-6 lg:grid-cols-[1fr_2fr] lg:items-end">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-paper/45">Fig. 1 — Your dashboard</p>
          <h2 className="font-serif text-4xl leading-tight text-paper sm:text-5xl">
            Every paper you&apos;ve written, and who has cited it since.
          </h2>
        </ScrollReveal>
        <ScrollReveal>
          <HeroDemo />
        </ScrollReveal>
      </section>

      {/* ─── References (features) ────────────────────────────────────── */}
      <section id="features" className="border-t border-paper/10">
        <div className="mx-auto grid max-w-7xl gap-12 px-4 py-24 sm:px-6 lg:grid-cols-[1fr_2fr] lg:px-8">
          <ScrollReveal className="lg:sticky lg:top-24 lg:self-start">
            <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-paper/45">References</p>
            <h2 className="font-serif text-4xl leading-tight text-paper sm:text-5xl">What Citey does for you</h2>
          </ScrollReveal>

          <ol className="divide-y divide-paper/10 border-y border-paper/10">
            {references.map(({ title, body, meta }, i) => (
              <ScrollReveal key={title} delay={i * 0.05}>
                <li className="grid gap-x-6 gap-y-2 py-8 sm:grid-cols-[3rem_1fr]">
                  <span className="font-mono text-sm text-signal">[{i + 1}]</span>
                  <div>
                    <h3 className="mb-2 font-serif text-2xl text-paper">{title}</h3>
                    <p className="mb-3 max-w-2xl leading-relaxed text-paper/60">{body}</p>
                    <p className="font-mono text-[11px] tracking-wide text-paper/35">{meta}</p>
                  </div>
                </li>
              </ScrollReveal>
            ))}
          </ol>
        </div>
      </section>

      {/* ─── How it works ─────────────────────────────────────────────── */}
      <section id="how" className="scroll-mt-16 border-t border-paper/10 bg-ink-800">
        <div className="mx-auto max-w-7xl px-4 py-24 sm:px-6 lg:px-8">
          <ScrollReveal className="mb-14 max-w-2xl">
            <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-paper/45">Method</p>
            <h2 className="font-serif text-4xl leading-tight text-paper sm:text-5xl">
              Set it up once. Hear about every citation after.
            </h2>
          </ScrollReveal>

          <ol className="grid gap-px overflow-hidden rounded-lg border border-paper/10 bg-paper/10 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(({ title, body }, i) => (
              <li key={title} className="bg-ink-800 p-6">
                <ScrollReveal delay={i * 0.06}>
                  <p className="mb-8 font-mono text-xs text-paper/40">0{i + 1}</p>
                  <h3 className="mb-2 font-serif text-2xl text-paper">{title}</h3>
                  <p className="text-sm leading-relaxed text-paper/55">{body}</p>
                </ScrollReveal>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ─── Closing CTA ──────────────────────────────────────────────── */}
      <section className="border-t border-paper/10">
        <ScrollReveal className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-24 sm:px-6 md:flex-row md:items-end md:justify-between lg:px-8">
          <h2 className="max-w-2xl font-serif text-4xl leading-tight text-paper sm:text-6xl">
            Your next citation is being written <em className="text-signal">right now</em>.
          </h2>
          <Link
            href={ctaHref}
            className="shrink-0 rounded-md bg-signal px-6 py-3 text-[15px] font-semibold text-ink transition-colors hover:bg-signal-soft"
          >
            {user ? "Open your dashboard" : "Start tracking, free"}
          </Link>
        </ScrollReveal>
      </section>

      {/* ─── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-paper/10 py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <Logo className="h-7 w-7" />
              <span className="font-serif text-xl text-paper">Citey</span>
              <span className="ml-2 font-mono text-[11px] uppercase tracking-[0.14em] text-paper/35">
                Citation alerts
              </span>
            </div>

            <nav className="flex flex-wrap gap-6 text-sm text-paper/45">
              <Link href="/" className="transition-colors hover:text-paper">Home</Link>
              {user && <Link href="/dashboard" className="transition-colors hover:text-paper">Dashboard</Link>}
              {user && <Link href="/settings" className="transition-colors hover:text-paper">Settings</Link>}
              <Link href="/faq" className="transition-colors hover:text-paper">FAQ</Link>
              <Link href="/help" className="transition-colors hover:text-paper">Help</Link>
            </nav>
          </div>

          <div className="mt-8 border-t border-paper/10 pt-8 text-xs text-paper/35">
            <p>&copy; {new Date().getFullYear()} Citey. Built for researchers, by researchers.</p>
            <p className="mt-1.5">
              Citation data from{" "}
              {[
                ["OpenAlex", "https://openalex.org"],
                ["Semantic Scholar", "https://www.semanticscholar.org"],
                ["Crossref", "https://www.crossref.org"],
                ["PubMed", "https://pubmed.ncbi.nlm.nih.gov"],
                ["INSPIRE-HEP", "https://inspirehep.net"],
                ["DBLP", "https://dblp.org"],
                ["NASA ADS", "https://ui.adsabs.harvard.edu"],
              ].map(([name, href], i, all) => (
                <span key={name}>
                  <a href={href} target="_blank" rel="noopener noreferrer" className="text-paper/55 hover:text-paper">
                    {name}
                  </a>
                  {i < all.length - 2 ? ", " : i === all.length - 2 ? ", and " : "."}
                </span>
              ))}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
