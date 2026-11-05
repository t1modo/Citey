"use client";

import Link from "next/link";
import Logo from "@/components/Logo";
import HeroDemo from "@/components/HeroDemo";
import CitationField from "@/components/citation-field/CitationField";
import { useAuth } from "@/contexts/AuthContext";

const SOURCES: [string, string][] = [
  ["OpenAlex", "https://openalex.org"],
  ["Semantic Scholar", "https://www.semanticscholar.org"],
  ["Crossref", "https://www.crossref.org"],
  ["PubMed", "https://pubmed.ncbi.nlm.nih.gov"],
  ["INSPIRE-HEP", "https://inspirehep.net"],
  ["DBLP", "https://dblp.org"],
  ["NASA ADS", "https://ui.adsabs.harvard.edu"],
];

// What a researcher actually asks before signing up, answered plainly.
const questions = [
  {
    q: "Where does Citey look?",
    a: "OpenAlex and Semantic Scholar, every night, the two largest open citation indexes. A citing paper often appears in one weeks before the other; Citey merges them so you hear about it once. Crossref, PubMed, NASA ADS, INSPIRE and DBLP help find your papers when you import them.",
  },
  {
    q: "What's in the email?",
    a: "The citing paper's title, authors, affiliations and year, with a link to it. You don't need to open the dashboard to know what happened.",
  },
  {
    q: "Do I have to add papers one by one?",
    a: "No. Link your OpenAlex, INSPIRE-HEP or DBLP profile, or search your name, and your publications are imported. Papers you publish later are picked up each week.",
  },
  {
    q: "What about my preprint and the published version?",
    a: "They're recognised as one paper, so it's tracked once and you only hear about it once.",
  },
  {
    q: "Can I get the list out?",
    a: "Yes. Export every citing paper as BibTeX for your CV, a tenure file or a grant report.",
  },
];


export default function HomePage() {
  const { user } = useAuth();
  const ctaHref = user ? "/dashboard" : "/signup";
  const ctaLabel = user ? "Open your dashboard" : "Start tracking, free";

  return (
    <div className="flex flex-col">
      {/* Hero: the citation timeline is the page's one moment of motion. */}
      <section className="relative isolate flex min-h-[calc(100svh-4rem)] items-center overflow-hidden border-b border-rule">
        <CitationField className="-z-10" />
        <div className="pointer-events-none absolute inset-y-0 left-0 -z-10 w-full bg-gradient-to-r from-paper via-paper/90 to-transparent md:w-[60%]" />

        <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="max-w-lg">
            <h1 className="mb-6 text-balance font-serif text-[2.75rem] font-semibold leading-[1.05] tracking-[-0.015em] text-ink sm:text-[4rem]">
              Know when your work is cited.
            </h1>
            <p className="mb-9 max-w-md text-lg leading-relaxed text-muted">
              Citey checks OpenAlex and Semantic Scholar every night and emails you when a new
              paper references yours.
            </p>
            <div className="flex flex-wrap items-center gap-x-7 gap-y-4">
              <Link
                href={ctaHref}
                className="rounded-md bg-ink px-6 py-3 text-base font-bold text-paper transition-colors hover:bg-ink-soft"
              >
                {ctaLabel}
              </Link>
              <a
                href="#how"
                className="text-base text-ink underline decoration-rule decoration-2 underline-offset-[6px] transition-colors hover:decoration-ink"
              >
                How it works
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* The product, shown rather than described. */}
      <section id="how" className="mx-auto w-full max-w-6xl scroll-mt-16 px-4 py-24 sm:px-6 lg:px-8">
        <h2 className="mb-12 max-w-xl font-serif text-4xl font-semibold leading-tight text-ink">
          From a DOI to your inbox
        </h2>
        <HeroDemo />
      </section>

      {/* Questions, answered. Not a sequence, so not numbered. */}
      <section id="features" className="border-t border-rule bg-sheet">
        <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6 lg:px-8">
          <h2 className="mb-14 max-w-xl font-serif text-4xl font-semibold leading-tight text-ink">
            Questions researchers ask
          </h2>
          <dl className="grid gap-x-16 gap-y-12 md:grid-cols-2">
            {questions.map(({ q, a }) => (
              <div key={q} className="border-t border-rule pt-6">
                <dt className="mb-3 font-serif text-[1.375rem] font-semibold leading-snug text-ink">{q}</dt>
                <dd className="max-w-prose leading-relaxed text-muted">{a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Closing */}
      <section className="border-t border-rule bg-ink text-paper">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-20 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <h2 className="font-serif text-3xl font-semibold leading-tight sm:text-4xl lg:whitespace-nowrap">
            Your next citation is being written now.
          </h2>
          <Link
            href={ctaHref}
            className="shrink-0 self-start rounded-md bg-paper px-6 py-3 text-base font-bold text-ink transition-colors hover:bg-sheet focus-visible:outline-paper lg:self-auto"
          >
            {ctaLabel}
          </Link>
        </div>
      </section>

      <footer className="py-12">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
            <Link href="/" className="flex items-center gap-2 text-ink">
              <Logo className="h-6 w-6" />
              <span className="font-serif text-lg font-semibold">Citey</span>
            </Link>
            <nav className="flex flex-wrap gap-6 text-sm text-muted">
              {user && <Link href="/dashboard" className="hover:text-ink">Dashboard</Link>}
              {user && <Link href="/settings" className="hover:text-ink">Settings</Link>}
              <Link href="/faq" className="hover:text-ink">FAQ</Link>
              <Link href="/help" className="hover:text-ink">Help</Link>
            </nav>
          </div>
          <p className="mt-8 border-t border-rule pt-8 text-sm leading-relaxed text-muted">
            Citation data from{" "}
            {SOURCES.map(([name, href], i) => (
              <span key={name}>
                <a href={href} target="_blank" rel="noopener noreferrer" className="text-ink underline decoration-rule underline-offset-2 hover:decoration-ink">
                  {name}
                </a>
                {i < SOURCES.length - 2 ? ", " : i === SOURCES.length - 2 ? " and " : "."}
              </span>
            ))}{" "}
            &copy; {new Date().getFullYear()} Citey.
          </p>
        </div>
      </footer>
    </div>
  );
}
