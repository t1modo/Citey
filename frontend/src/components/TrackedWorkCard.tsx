"use client";

import { useState } from "react";
import type { TrackedWork } from "@/lib/types";

interface TrackedWorkCardProps {
  work: TrackedWork;
  onRemove: (workId: string) => void;
  removing?: boolean;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function authorLine(authors: string[]): string {
  if (authors.length === 0) return "";
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} and ${authors.length - 3} more`;
}

/** One tracked paper, set like an entry in a reference list. */
export default function TrackedWorkCard({ work, onRemove, removing = false }: TrackedWorkCardProps) {
  const hasCounts = work.s2_citation_count != null || work.openalex_citation_count != null;
  const lifetime = Math.max(work.s2_citation_count ?? 0, work.openalex_citation_count ?? 0);
  const source = [work.venue, work.year].filter(Boolean).join(", ");
  // Stopping removes the paper and its citation history, so confirm first.
  const [confirming, setConfirming] = useState(false);

  return (
    <article className="py-5">
      <h3 className="mb-1.5 font-serif text-lg font-semibold leading-snug text-ink">
        {work.title ?? "Untitled work"}
      </h3>
      <p className="text-sm leading-relaxed text-muted">
        {authorLine(work.authors)}
        {source && (
          <>
            {work.authors.length > 0 && ". "}
            <i>{source}</i>.
          </>
        )}
      </p>
      {work.doi && (
        <a
          href={`https://doi.org/${work.doi}`}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 block max-w-full truncate font-mono text-xs text-muted underline decoration-rule underline-offset-2 hover:text-ink hover:decoration-ink"
        >
          doi:{work.doi}
        </a>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        {/* Lifetime total from the indexes. The 30 day alert count is a
            different number and is shown separately as "new this month". */}
        {hasCounts && (
          <span
            className="text-ink"
            title="Lifetime citations, the higher of OpenAlex and Semantic Scholar. Google Scholar often shows more because it also counts theses, slides and duplicate versions."
          >
            Cited by {lifetime.toLocaleString()}
          </span>
        )}
        {work.new_citations_30d > 0 && (
          <span className="highlight font-bold text-ink">
            {work.new_citations_30d} new this month
          </span>
        )}
        <span className="text-muted">
          {work.last_checked_at ? `Checked ${formatDate(work.last_checked_at)}` : "Not checked yet"}
        </span>
        {confirming ? (
          <span className="ml-auto flex items-center gap-3" role="group" aria-label="Confirm stop tracking">
            <span className="text-muted">Remove it and its citations?</span>
            <button
              onClick={() => onRemove(work.id)}
              disabled={removing}
              className="font-bold text-danger underline underline-offset-2 disabled:opacity-40"
            >
              {removing ? "Removing…" : "Stop tracking"}
            </button>
            <button onClick={() => setConfirming(false)} className="text-ink underline decoration-rule underline-offset-2">
              Keep
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="ml-auto text-sm text-muted underline decoration-rule underline-offset-2 hover:text-danger hover:decoration-danger"
          >
            Stop tracking
          </button>
        )}
      </div>
    </article>
  );
}
