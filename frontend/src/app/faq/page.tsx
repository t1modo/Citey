"use client";

import { useState } from "react";
import Link from "next/link";

interface FaqItem {
  question: string;
  answer: React.ReactNode;
}

const faqItems: FaqItem[] = [
  {
    question: "What citation sources does Citey use?",
    answer: (
      <>
        <p>
          Citey uses seven scholarly databases in two roles:
        </p>
        <p className="mt-3 text-xs font-semibold text-muted">
          Checked for new citations every night
        </p>
        <ul className="mt-2 list-disc space-y-2 pl-5">
          <li>
            <strong className="text-ink">OpenAlex</strong>: a free, open index of
            over 250 million scholarly works updated daily. The main source for citation
            tracking across all disciplines. Learn more at{" "}
            <a href="https://openalex.org" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">openalex.org</a>.
          </li>
          <li>
            <strong className="text-ink">Semantic Scholar</strong>: an AI powered
            index of over 200 million papers from the Allen Institute for AI. Provides
            strong additional coverage for computer science, AI/ML, and biomedical
            literature. Learn more at{" "}
            <a href="https://www.semanticscholar.org" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">semanticscholar.org</a>.
          </li>
        </ul>
        <p className="mt-4 text-xs font-semibold text-muted">
          Used when you add or import papers
        </p>
        <ul className="mt-2 list-disc space-y-2 pl-5">
          <li>
            <strong className="text-ink">Crossref</strong>: the canonical DOI
            registration agency, aggregating reference lists from thousands of publishers.
            Used to look up DOIs when you add a paper. Learn more at{" "}
            <a href="https://www.crossref.org" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">crossref.org</a>.
          </li>
          <li>
            <strong className="text-ink">PubMed</strong>: 35 million biomedical and
            life science records from the NCBI. Learn more at{" "}
            <a href="https://pubmed.ncbi.nlm.nih.gov" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">pubmed.ncbi.nlm.nih.gov</a>.
          </li>
          <li>
            <strong className="text-ink">NASA ADS</strong>: astronomy, astrophysics,
            and space science literature. Learn more at{" "}
            <a href="https://ui.adsabs.harvard.edu" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">ui.adsabs.harvard.edu</a>.
          </li>
          <li>
            <strong className="text-ink">INSPIRE-HEP</strong>: the canonical database
            for high-energy physics, including JACoW conference proceedings. Learn more at{" "}
            <a href="https://inspirehep.net" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">inspirehep.net</a>.
          </li>
          <li>
            <strong className="text-ink">DBLP</strong>: nearly complete ACM and IEEE
            conference and journal coverage for computer science. Learn more at{" "}
            <a href="https://dblp.org" target="_blank" rel="noopener noreferrer" className="text-muted underline hover:text-ink">dblp.org</a>.
          </li>
        </ul>
        <p className="mt-3">
          Because all sources rely on publisher submissions and indexing pipelines,
          coverage is not 100% universal. Conference papers, preprints, and grey literature
          may have limited citation data.
        </p>
      </>
    ),
  },
  {
    question: "How often are citations checked?",
    answer: (
      <>
        <p>
          Citey runs a citation scan job <strong className="text-ink">once per day</strong>.
          It looks up every tracked paper in OpenAlex and Semantic Scholar and records
          any citing papers it hasn't seen before.
        </p>
        <p className="mt-3">
          Email notifications are dispatched immediately after new citations are found, so
          you should receive an alert within a day of a citing paper appearing in OpenAlex
          or Semantic Scholar. New citations appear automatically on your{" "}
          <Link href="/dashboard" className="text-muted underline hover:text-ink">
            Dashboard
          </Link>
          , with nothing for you to do.
        </p>
      </>
    ),
  },
  {
    question: "Why is a paper I expect to be cited missing?",
    answer: (
      <>
        <p>There are several reasons a citation might not appear in Citey:</p>
        <ul className="mt-3 list-disc space-y-2 pl-5">
          <li>
            <strong className="text-ink">Indexing lag.</strong> OpenAlex, Crossref, and
            Semantic Scholar rely on publishers depositing metadata and their own crawling
            pipelines. Newly published papers may take days to weeks to be fully indexed.
          </li>
          <li>
            <strong className="text-ink">Missing reference lists.</strong> Not all
            publishers deposit complete reference lists with Crossref. Open access
            publishers tend to have better coverage.
          </li>
          <li>
            <strong className="text-ink">DOI mismatch.</strong> If the citing paper
            references your work without the correct DOI (e.g., using a URL or an
            informal citation), the automated system cannot link it to your tracked work.
          </li>
          <li>
            <strong className="text-ink">Conference papers and books.</strong> These
            are often less well-covered than journal articles. Preprints on arXiv or
            bioRxiv may also have limited citation data.
          </li>
        </ul>
        <p className="mt-3">
          If you believe a citation is genuinely missing, verify that the citing paper
          itself has a DOI and that it is indexed on{" "}
          <a
            href="https://openalex.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted underline hover:text-ink"
          >
            OpenAlex
          </a>
          {" "}or{" "}
          <a
            href="https://www.semanticscholar.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted underline hover:text-ink"
          >
            Semantic Scholar
          </a>
          .
        </p>
      </>
    ),
  },
  {
    question: "How do I unsubscribe from email notifications?",
    answer: (
      <>
        <p>
          You can disable email notifications at any time without deleting your account:
        </p>
        <ol className="mt-3 list-decimal space-y-2 pl-5">
          <li>
            Go to{" "}
            <Link href="/settings" className="text-muted underline hover:text-ink">
              Settings
            </Link>
            .
          </li>
          <li>
            In the <strong className="text-ink">Notifications</strong> section,
            toggle off <strong className="text-ink">Email notifications</strong>.
          </li>
          <li>Click <strong className="text-ink">Save changes</strong>.</li>
        </ol>
        <p className="mt-3">
          You will no longer receive email alerts, but your tracked works and notification
          history will remain intact. You can re-enable notifications at any time.
        </p>
      </>
    ),
  },
  {
    question: "Is my data private?",
    answer: (
      <>
        <p>
          Yes. Citey takes data privacy seriously. Here is what we store and why:
        </p>
        <ul className="mt-3 list-disc space-y-2 pl-5">
          <li>
            <strong className="text-ink">Email address</strong>: for account
            authentication (via Firebase Auth) and sending you citation alerts.
          </li>
          <li>
            <strong className="text-ink">DOIs of tracked works</strong>: to know which
            papers to monitor.
          </li>
          <li>
            <strong className="text-ink">Notification records</strong>: to display your
            citation history in the dashboard and avoid sending duplicate alerts.
          </li>
        </ul>
        <p className="mt-3">
          We do not sell your data. We do not use it for advertising. Citation metadata is
          fetched from publicly available APIs (OpenAlex, Crossref, Semantic Scholar) and
          is not considered private.
        </p>
      </>
    ),
  },
  {
    question: "What DOI formats are supported?",
    answer: (
      <>
        <p>
          Citey accepts DOIs in several common formats when you add a tracked work:
        </p>
        <ul className="mt-3 list-disc space-y-2 pl-5">
          <li>
            <strong className="text-ink">Bare DOI:</strong>{" "}
            <code className="rounded bg-sheet px-1 py-0.5 font-mono text-xs text-muted">
              10.1038/s41586-021-03819-2
            </code>
          </li>
          <li>
            <strong className="text-ink">HTTPS URL:</strong>{" "}
            <code className="rounded bg-sheet px-1 py-0.5 font-mono text-xs text-muted">
              https://doi.org/10.1038/s41586-021-03819-2
            </code>
          </li>
          <li>
            <strong className="text-ink">HTTP URL:</strong>{" "}
            <code className="rounded bg-sheet px-1 py-0.5 font-mono text-xs text-muted">
              http://doi.org/10.1038/s41586-021-03819-2
            </code>
          </li>
          <li>
            <strong className="text-ink">Protocol-free URL:</strong>{" "}
            <code className="rounded bg-sheet px-1 py-0.5 font-mono text-xs text-muted">
              doi.org/10.1038/s41586-021-03819-2
            </code>
          </li>
        </ul>
        <p className="mt-3">
          All valid DOIs begin with{" "}
          <code className="rounded bg-sheet px-1 py-0.5 font-mono text-xs text-muted">10.</code>{" "}
          followed by a registrant code and suffix. Citey resolves DOIs through a
          fallback chain of{" "}
          <a
            href="https://www.crossref.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted underline hover:text-ink"
          >
            Crossref
          </a>
          ,{" "}
          <a
            href="https://datacite.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted underline hover:text-ink"
          >
            DataCite
          </a>
          , and{" "}
          <a
            href="https://openalex.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted underline hover:text-ink"
          >
            OpenAlex
          </a>
          , so publisher DOIs, arXiv preprints, and institutional repository records
          are all supported. If your DOI is not recognised, double-check it at{" "}
          <a
            href="https://search.crossref.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted underline hover:text-ink"
          >
            search.crossref.org
          </a>
          .
        </p>
      </>
    ),
  },
];

function AccordionItem({ item, index }: { item: FaqItem; index: number }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-rule">
      <button
        className="flex w-full items-center justify-between gap-4 px-0 py-5 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`faq-answer-${index}`}
        id={`faq-question-${index}`}
      >
        <span className="text-base font-semibold text-ink leading-snug">
          {item.question}
        </span>
        <span
          className={`shrink-0 rounded-full border border-rule p-1 text-muted transition-transform ${
            open ? "rotate-180 border-rule bg-ink/10 text-ink" : ""
          }`}
          aria-hidden
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      {open && (
        <div
          id={`faq-answer-${index}`}
          role="region"
          aria-labelledby={`faq-question-${index}`}
          className="pb-6 text-sm leading-relaxed text-muted"
        >
          {item.answer}
        </div>
      )}
    </div>
  );
}

export default function FaqPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-12 text-center">
        <h1 className="font-serif mb-4 text-4xl font-semibold text-ink">
          Frequently asked questions
        </h1>
        <p className="text-muted">
          Everything you need to know about Citey and how citation tracking works.
        </p>
      </div>

      {/* Accordion */}
      <div>
      <div className="rounded-2xl border border-rule bg-sheet px-6 py-2">
        {faqItems.map((item, i) => (
          <AccordionItem key={i} item={item} index={i} />
        ))}
      </div>
      </div>

      {/* Still have questions */}
      <div>
      <div className="mt-12 rounded-2xl border border-rule bg-ink/5 p-8 text-center">
        <h2 className="font-serif mb-2 text-xl font-semibold text-ink">
          Still have questions?
        </h2>
        <p className="mb-1 text-sm text-muted">
          Check the dashboard or update your preferences in Settings.
        </p>
        <p className="mb-6 text-sm text-muted">
          For anything else,{" "}
          <Link href="/contact" className="text-ink underline hover:text-ink">
            send us a message
          </Link>
          .
        </p>
        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/dashboard"
            className="rounded-xl bg-ink px-6 py-2.5 text-sm font-semibold text-paper shadow transition-opacity hover:bg-ink-soft"
          >
            Go to dashboard
          </Link>
          <Link
            href="/settings"
            className="rounded-xl border border-rule px-6 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-ink/5 hover:text-ink"
          >
            Settings
          </Link>
        </div>
      </div>
      </div>

      {/* Data sources attribution */}
      <p className="mt-10 text-center text-xs text-muted">
        Citation data provided by{" "}
        <a
          href="https://openalex.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          OpenAlex
        </a>
        ,{" "}
        <a
          href="https://www.crossref.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          Crossref
        </a>
        ,{" "}
        <a
          href="https://www.semanticscholar.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          Semantic Scholar
        </a>
        ,{" "}
        <a
          href="https://pubmed.ncbi.nlm.nih.gov"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          PubMed
        </a>
        ,{" "}
        <a
          href="https://ui.adsabs.harvard.edu"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          NASA ADS
        </a>
        ,{" "}
        <a
          href="https://inspirehep.net"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          INSPIRE-HEP
        </a>
        , and{" "}
        <a
          href="https://dblp.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted hover:text-muted"
        >
          DBLP
        </a>
        .
      </p>
    </div>
  );
}
