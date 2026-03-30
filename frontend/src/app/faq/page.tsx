"use client";

import { useState } from "react";
import Link from "next/link";
import SplitText from "@/components/SplitText";
import ScrollReveal from "@/components/ScrollReveal";

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
          Citey queries three major open scholarly databases to find citations to your
          tracked works:
        </p>
        <ul className="mt-3 list-disc space-y-2 pl-5">
          <li>
            <strong className="text-white">OpenAlex</strong>, a free, open index of
            over 250 million scholarly works, authors, institutions, and sources. OpenAlex
            provides rich reference and citation data and is updated daily. Learn more at{" "}
            <a
              href="https://openalex.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 underline hover:text-gray-300"
            >
              openalex.org
            </a>
            .
          </li>
          <li>
            <strong className="text-white">Crossref</strong>, a digital object
            identifier (DOI) registration agency that aggregates metadata from thousands of
            publishers. Crossref provides reference lists submitted by publishers and is the
            canonical source of DOI resolution. Learn more at{" "}
            <a
              href="https://www.crossref.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 underline hover:text-gray-300"
            >
              crossref.org
            </a>
            .
          </li>
          <li>
            <strong className="text-white">Semantic Scholar</strong>, a free, AI-powered
            research tool from the Allen Institute for AI that indexes over 200 million
            papers across all fields of science. Semantic Scholar provides additional
            citation coverage, particularly for computer science and biomedical literature.
            Learn more at{" "}
            <a
              href="https://www.semanticscholar.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 underline hover:text-gray-300"
            >
              semanticscholar.org
            </a>
            .
          </li>
        </ul>
        <p className="mt-3">
          Because these sources rely on publisher submissions and indexing pipelines,
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
          Citey runs a citation scan job <strong className="text-white">once per day</strong>.
          The job iterates over every tracked work in the database, queries OpenAlex,
          Crossref, and Semantic Scholar for new citing papers, and records any newly
          discovered citations.
        </p>
        <p className="mt-3">
          Email notifications are dispatched immediately after new citations are found, so
          you should receive an alert within 24 hours of a paper being indexed by OpenAlex,
          Crossref, or Semantic Scholar. You can also trigger a manual check from the{" "}
          <Link href="/dashboard" className="text-gray-400 underline hover:text-gray-300">
            Dashboard
          </Link>{" "}
          using the &ldquo;Run Citation Check&rdquo; button.
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
            <strong className="text-white">Indexing lag.</strong> OpenAlex, Crossref, and
            Semantic Scholar rely on publishers depositing metadata and their own crawling
            pipelines. Newly published papers may take days to weeks to be fully indexed.
          </li>
          <li>
            <strong className="text-white">Missing reference lists.</strong> Not all
            publishers deposit complete reference lists with Crossref. Open access
            publishers tend to have better coverage.
          </li>
          <li>
            <strong className="text-white">DOI mismatch.</strong> If the citing paper
            references your work without the correct DOI (e.g., using a URL or an
            informal citation), the automated system cannot link it to your tracked work.
          </li>
          <li>
            <strong className="text-white">Conference papers and books.</strong> These
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
            className="text-gray-400 underline hover:text-gray-300"
          >
            OpenAlex
          </a>
          {" "}or{" "}
          <a
            href="https://www.semanticscholar.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 underline hover:text-gray-300"
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
            <Link href="/settings" className="text-gray-400 underline hover:text-gray-300">
              Settings
            </Link>
            .
          </li>
          <li>
            In the <strong className="text-white">Notification Preferences</strong> section,
            toggle off <strong className="text-white">Email notifications</strong>.
          </li>
          <li>Click <strong className="text-white">Save Changes</strong>.</li>
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
            <strong className="text-white">Email address</strong>: for account
            authentication (via Firebase Auth) and sending you citation alerts.
          </li>
          <li>
            <strong className="text-white">DOIs of tracked works</strong>: to know which
            papers to monitor.
          </li>
          <li>
            <strong className="text-white">Notification records</strong>: to display your
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
            <strong className="text-white">Bare DOI:</strong>{" "}
            <code className="rounded bg-gray-800 px-1 py-0.5 font-mono text-xs text-gray-500">
              10.1038/s41586-021-03819-2
            </code>
          </li>
          <li>
            <strong className="text-white">DOI.org URL:</strong>{" "}
            <code className="rounded bg-gray-800 px-1 py-0.5 font-mono text-xs text-gray-500">
              https://doi.org/10.1038/s41586-021-03819-2
            </code>
          </li>
          <li>
            <strong className="text-white">HTTP DOI URL:</strong>{" "}
            <code className="rounded bg-gray-800 px-1 py-0.5 font-mono text-xs text-gray-500">
              http://dx.doi.org/10.1038/s41586-021-03819-2
            </code>
          </li>
        </ul>
        <p className="mt-3">
          All valid DOIs begin with <code className="rounded bg-gray-800 px-1 py-0.5 font-mono text-xs text-gray-500">10.</code> followed
          by a registrant code and suffix. DOIs are resolved via{" "}
          <a
            href="https://www.doi.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 underline hover:text-gray-300"
          >
            doi.org
          </a>{" "}
          to retrieve paper metadata. If your DOI is not recognised, double-check it at{" "}
          <a
            href="https://search.crossref.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 underline hover:text-gray-300"
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
    <div className="border-b border-white/10">
      <button
        className="flex w-full items-center justify-between gap-4 px-0 py-5 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`faq-answer-${index}`}
        id={`faq-question-${index}`}
      >
        <span className="text-base font-semibold text-white leading-snug">
          {item.question}
        </span>
        <span
          className={`shrink-0 rounded-full border border-white/10 p-1 text-gray-400 transition-transform ${
            open ? "rotate-180 border-white/20 bg-white/10 text-white" : ""
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
          className="pb-6 text-sm leading-relaxed text-gray-400"
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
      <ScrollReveal className="mb-12 text-center">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs font-medium text-gray-300">
          Help Center
        </div>
        <h1 className="mb-4 text-4xl font-bold text-white">
          <SplitText text="Frequently Asked Questions" charDelay={0.025} />
        </h1>
        <p className="text-gray-400">
          Everything you need to know about Citey and how citation tracking works.
        </p>
      </ScrollReveal>

      {/* Accordion */}
      <ScrollReveal delay={0.15}>
      <div className="rounded-2xl border border-white/10 bg-gray-900/50 px-6 py-2">
        {faqItems.map((item, i) => (
          <AccordionItem key={i} item={item} index={i} />
        ))}
      </div>
      </ScrollReveal>

      {/* Still have questions */}
      <ScrollReveal delay={0.1}>
      <div className="mt-12 rounded-2xl border border-white/10 bg-white/5 p-8 text-center">
        <h2 className="mb-2 text-xl font-bold text-white">
          Still have questions?
        </h2>
        <p className="mb-6 text-sm text-gray-400">
          If you can&apos;t find the answer you need, check the dashboard or reach out
          via your notification email settings.
        </p>
        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/dashboard"
            className="rounded-xl bg-white px-6 py-2.5 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100"
          >
            Go to Dashboard
          </Link>
          <Link
            href="/settings"
            className="rounded-xl border border-white/10 px-6 py-2.5 text-sm font-semibold text-gray-300 transition-colors hover:bg-white/5 hover:text-white"
          >
            Settings
          </Link>
        </div>
      </div>
      </ScrollReveal>

      {/* Data sources attribution */}
      <p className="mt-10 text-center text-xs text-gray-600">
        Citation data provided by{" "}
        <a
          href="https://openalex.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-gray-500 hover:text-gray-400"
        >
          OpenAlex
        </a>
        ,{" "}
        <a
          href="https://www.crossref.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-gray-500 hover:text-gray-400"
        >
          Crossref
        </a>
        , and{" "}
        <a
          href="https://www.semanticscholar.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-gray-500 hover:text-gray-400"
        >
          Semantic Scholar
        </a>
        .
      </p>
    </div>
  );
}
