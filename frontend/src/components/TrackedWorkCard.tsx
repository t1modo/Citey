"use client";

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

export default function TrackedWorkCard({
  work,
  onRemove,
  removing = false,
}: TrackedWorkCardProps) {
  const displayedAuthors =
    work.authors.length > 3
      ? [...work.authors.slice(0, 3), `+${work.authors.length - 3} more`]
      : work.authors;

  return (
    <div className="glass-card flex flex-col gap-3 p-4 transition-all duration-200 hover:border-white/20">
      {/* Title */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="flex-1 text-sm font-semibold leading-snug text-white">
          {work.title ?? "Untitled work"}
        </h3>
        {work.year && (
          <span className="shrink-0 rounded bg-gray-800 px-2 py-0.5 text-xs font-medium text-gray-400">
            {work.year}
          </span>
        )}
      </div>

      {/* DOI */}
      <a
        href={`https://doi.org/${work.doi}`}
        target="_blank"
        rel="noopener noreferrer"
        className="w-fit rounded text-xs font-mono text-gray-400 underline decoration-dotted underline-offset-2 transition-colors hover:text-gray-300 hover:decoration-solid"
      >
        {work.doi}
      </a>

      {/* Authors */}
      {displayedAuthors.length > 0 && (
        <p className="text-xs text-gray-400 leading-relaxed">
          {displayedAuthors.join(" · ")}
        </p>
      )}

      {/* Citation stats */}
      <div className="flex items-center gap-2">
        {/* Lifetime total — best of S2 and OpenAlex */}
        {(() => {
          const best = Math.max(work.s2_citation_count ?? 0, work.openalex_citation_count ?? 0);
          const hasData = (work.s2_citation_count !== null && work.s2_citation_count !== undefined)
            || (work.openalex_citation_count !== null && work.openalex_citation_count !== undefined);
          return hasData ? (
            <span className="rounded-full border border-white/10 bg-gray-800 px-2.5 py-0.5 text-xs font-medium text-gray-300">
              Cited by {best.toLocaleString()}
            </span>
          ) : work.citation_count > 0 ? (
            <span className="rounded-full border border-white/10 bg-gray-800 px-2.5 py-0.5 text-xs font-medium text-gray-300">
              {work.citation_count} {work.citation_count === 1 ? "citation" : "citations"}
            </span>
          ) : null;
        })()}
        {work.new_citations_30d > 0 && (
          <span className="rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 text-xs font-semibold text-white">
            +{work.new_citations_30d} new
          </span>
        )}
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/5">
        {work.last_checked_at ? (
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
            Checked {formatDate(work.last_checked_at)}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-gray-600">
            <span className="h-1.5 w-1.5 rounded-full bg-gray-700" />
            Not yet checked
          </span>
        )}

        <button
          onClick={() => onRemove(work.id)}
          disabled={removing}
          className="rounded px-2.5 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {removing ? "Removing…" : "Remove"}
        </button>
      </div>
    </div>
  );
}
