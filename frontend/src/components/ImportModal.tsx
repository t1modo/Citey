"use client";

import { useState, useEffect, useRef, FormEvent } from "react";
import {
  addWorkChecked,
  getAuthorsByPaperDoi,
  importByAuthor,
  searchAuthors,
} from "@/lib/api";
import type {
  TrackedWork,
  AddWorkResult,
  AuthorCandidate,
  AuthorAffiliation,
} from "@/lib/types";

// ── Input type detection ─────────────────────────────────────────────────────

type InputType = "doi" | "arxiv" | "inspire-author" | "dblp-author" | "name";
type AuthorSource = "openalex" | "semantic_scholar" | "inspire" | "dblp";

function detectInputType(raw: string): InputType {
  const s = raw.trim();
  if (!s) return "name";
  // arXiv URL, arxiv: prefix, bare ID formats
  if (
    /arxiv\.org\/(abs|pdf)\//i.test(s) ||
    /^arxiv:/i.test(s) ||
    /^\d{4}\.\d{4,5}(v\d+)?$/.test(s) ||
    /^[a-z-]+\/\d{7}$/i.test(s)
  ) return "arxiv";
  // INSPIRE-HEP author profile URL
  if (/inspirehep\.net\/authors\//i.test(s)) return "inspire-author";
  // DBLP author profile URL
  if (/dblp\.org\/pid\//i.test(s)) return "dblp-author";
  // DOI or doi.org URL
  if (/^10\.\d{4,}\//.test(s) || /doi\.org\//i.test(s)) return "doi";
  // Anything else is treated as an author name
  return "name";
}

function parseArxivId(input: string): string | null {
  const s = input.trim();
  const urlMatch = s.match(/arxiv\.org\/(?:abs|pdf)\/([^\s?#/]+)/i);
  if (urlMatch) return urlMatch[1].replace(/v\d+$/i, "");
  const prefixMatch = s.match(/^arxiv:([^\s]+)/i);
  if (prefixMatch) return prefixMatch[1].replace(/v\d+$/i, "");
  if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(s)) return s.replace(/v\d+$/i, "");
  if (/^[a-z-]+\/\d{7}$/i.test(s)) return s;
  return null;
}

function extractInspireAuthorId(url: string): string | null {
  const m = url.match(/inspirehep\.net\/authors\/(\d+)/i);
  return m ? m[1] : null;
}

function extractDblpPid(url: string): string | null {
  const m = url.match(/dblp\.org\/pid\/([^\s?#]+)/i);
  return m ? m[1] : null;
}

// ── Phase model ──────────────────────────────────────────────────────────────

type Phase =
  | { type: "input" }
  | {
      type: "author-select";
      paper?: { title: string; year: number | null };
      candidates: AuthorCandidate[];
      resolvedDoi?: string;
    }
  | {
      type: "direct-confirm";
      source: "inspire" | "dblp";
      authorId: string;
    }
  | {
      type: "author-not-found";
      check: Extract<AddWorkResult, { status: "author_not_found" }>;
    }
  | {
      type: "merge-confirm";
      author: AuthorCandidate;
      existingAuthorName: string;
    };

// ── Props ────────────────────────────────────────────────────────────────────

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdded: (work: TrackedWork) => void;
  onImported: (count: number) => void;
  linkedAuthorId?: string | null;
  linkedAuthorName?: string | null;
}

// ── Small shared components ──────────────────────────────────────────────────

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

function normalizeAuthorId(id: string): string {
  return id.startsWith("https://openalex.org/") ? id.slice(21) : id;
}

function sourceLabel(source: AuthorSource): string {
  switch (source) {
    case "semantic_scholar": return "S2";
    case "inspire": return "INSPIRE";
    case "dblp": return "DBLP";
    default: return "OA";
  }
}

function sourceBadgeClass(source: AuthorSource): string {
  switch (source) {
    case "semantic_scholar": return "bg-teal-500/15 text-teal-400";
    case "inspire": return "bg-purple-500/15 text-purple-400";
    case "dblp": return "bg-orange-500/15 text-orange-400";
    default: return "bg-blue-500/15 text-blue-400";
  }
}

// ── Main component ───────────────────────────────────────────────────────────

export default function ImportModal({
  isOpen,
  onClose,
  onAdded,
  onImported,
  linkedAuthorId,
  linkedAuthorName,
}: ImportModalProps) {
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<Phase>({ type: "input" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [fallbackLoading, setFallbackLoading] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setQuery("");
    setPhase({ type: "input" });
    setLoading(false);
    setError(null);
    setImportingId(null);
    setImportError(null);
    setFallbackLoading(false);
  };

  useEffect(() => {
    if (isOpen) {
      reset();
      setTimeout(() => inputRef.current?.focus(), 50);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // ── Lookup handler ────────────────────────────────────────────────────────

  const handleLookup = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) { setError("Please enter a value."); return; }

    const inputType = detectInputType(trimmed);
    setError(null);
    setImportError(null);

    // ── arXiv ──────────────────────────────────────────────────────────────
    if (inputType === "arxiv") {
      const arxivId = parseArxivId(trimmed);
      if (!arxivId) {
        setError("Could not parse arXiv ID. Paste the full URL or a bare ID like 2301.12345.");
        return;
      }
      const resolvedDoi = `10.48550/arXiv.${arxivId}`;
      setLoading(true);
      try {
        const result = await getAuthorsByPaperDoi(resolvedDoi);
        setPhase({
          type: "author-select",
          paper: { title: result.paper_title, year: result.paper_year },
          candidates: result.authors,
          resolvedDoi,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Lookup failed.");
      } finally {
        setLoading(false);
      }
      return;
    }

    // ── DOI ────────────────────────────────────────────────────────────────
    if (inputType === "doi") {
      // Always look up co-authors first so the user can import their full
      // profile (same flow as arXiv). Only fall back to a direct add when
      // no author database has this paper.
      setLoading(true);
      try {
        const result = await getAuthorsByPaperDoi(trimmed);
        setPhase({
          type: "author-select",
          paper: { title: result.paper_title, year: result.paper_year },
          candidates: result.authors,
          resolvedDoi: trimmed,
        });
      } catch {
        // Paper not found in author databases — fall back to direct add.
        // Skip the author-presence check only when there is no linked author.
        try {
          const result = await addWorkChecked(trimmed, !linkedAuthorId);
          if (result.status === "added") { onAdded(result.work); onClose(); return; }
          setPhase({ type: "author-not-found", check: result });
        } catch (err2) {
          setError(err2 instanceof Error ? err2.message : "Failed to add work.");
        }
      } finally {
        setLoading(false);
      }
      return;
    }

    // ── INSPIRE author URL ─────────────────────────────────────────────────
    if (inputType === "inspire-author") {
      const authorId = extractInspireAuthorId(trimmed);
      if (!authorId) { setError("Could not extract author ID from INSPIRE URL."); return; }
      setPhase({ type: "direct-confirm", source: "inspire", authorId });
      return;
    }

    // ── DBLP author URL ───────────────────────────────────────────────────
    if (inputType === "dblp-author") {
      const pid = extractDblpPid(trimmed);
      if (!pid) { setError("Could not extract PID from DBLP URL."); return; }
      setPhase({ type: "direct-confirm", source: "dblp", authorId: pid });
      return;
    }

    // ── Author name search ────────────────────────────────────────────────
    setLoading(true);
    try {
      const candidates = await searchAuthors(trimmed);
      setPhase({ type: "author-select", candidates });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  };

  // ── Import an author ──────────────────────────────────────────────────────

  const handleImport = async (
    authorId: string,
    authorName: string | undefined,
    source: AuthorSource,
    confirmMerge = false,
  ) => {
    setImportingId(authorId);
    setImportError(null);
    try {
      const result = await importByAuthor(authorId, authorName, source, confirmMerge);
      if (result.status === "merge_required") {
        const currentPhase = phase;
        const author: AuthorCandidate = phase.type === "author-select"
          ? phase.candidates.find((c) => c.id === authorId) ?? {
              id: authorId, display_name: authorName ?? authorId,
              works_count: 0, h_index: 0, affiliations: [], topics: [], source,
            }
          : { id: authorId, display_name: authorName ?? authorId,
              works_count: 0, h_index: 0, affiliations: [], topics: [], source };
        void currentPhase;
        setPhase({
          type: "merge-confirm",
          author,
          existingAuthorName: result.existing_author_name,
        });
        setImportingId(null);
        return;
      }
      onImported(result.imported);
      onClose();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed.");
      setImportingId(null);
    }
  };

  // ── Fallback: add just this one paper ─────────────────────────────────────

  const handleFallback = async (doi: string) => {
    setFallbackLoading(true);
    setImportError(null);
    try {
      const result = await addWorkChecked(doi, true);
      if (result.status === "added") { onAdded(result.work); onClose(); }
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Failed to add work.");
    } finally {
      setFallbackLoading(false);
    }
  };

  // ── Shared: AuthorCard ────────────────────────────────────────────────────

  const AuthorCard = ({
    author,
    highlight = false,
    anyBusy,
  }: {
    author: AuthorCandidate;
    highlight?: boolean;
    anyBusy: boolean;
  }) => (
    <div className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-3 ${
      highlight ? "border-teal-500/30 bg-teal-500/10" : "border-white/10 bg-gray-800"
    }`}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-white">{author.display_name}</p>
          {highlight && (
            <span className="shrink-0 rounded-full bg-teal-500/20 px-2 py-0.5 text-[10px] font-semibold text-teal-400">
              You
            </span>
          )}
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${sourceBadgeClass(author.source)}`}>
            {sourceLabel(author.source)}
          </span>
        </div>
        {author.affiliations.length > 0 && (
          <p className="truncate text-xs text-gray-400">
            {author.affiliations
              .map((a: AuthorAffiliation) => a.year_range ? `${a.name} (${a.year_range})` : a.name)
              .join(" · ")}
          </p>
        )}
        <p className="text-xs text-gray-500">
          {author.works_count} works
          {author.h_index > 0 && <span className="ml-2">h-index {author.h_index}</span>}
        </p>
      </div>
      <button
        onClick={() => handleImport(author.id, author.display_name, author.source)}
        disabled={anyBusy}
        className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          highlight
            ? "bg-teal-500/80 text-white hover:bg-teal-500"
            : "bg-white/10 text-white hover:bg-white/15"
        }`}
      >
        {importingId === author.id ? (
          <span className="flex items-center gap-1.5"><Spinner className="h-3 w-3" /> Importing…</span>
        ) : (
          "Import"
        )}
      </button>
    </div>
  );

  // ── Hint text for the input ───────────────────────────────────────────────

  const detectedType = query.trim() ? detectInputType(query.trim()) : null;
  const hintMap: Record<InputType, string> = {
    arxiv: "Detected: arXiv paper",
    doi: "Detected: DOI",
    "inspire-author": "Detected: INSPIRE-HEP author profile",
    "dblp-author": "Detected: DBLP author profile",
    name: "Will search by author name",
  };

  // ── Render ────────────────────────────────────────────────────────────────

  const anyBusy = importingId !== null || fallbackLoading;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-modal-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div className="relative z-10 flex w-full max-w-md flex-col rounded-2xl border border-white/10 bg-gray-900 shadow-2xl max-h-[90vh] sm:max-h-[85vh]">

        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 pt-6 pb-5">
          <h2 id="import-modal-title" className="text-lg font-semibold text-white">
            Add Papers
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-6 pb-6">
          <div className="flex flex-col gap-4">

            {/* ── Input phase ─────────────────────────────────────────── */}
            {phase.type === "input" && (
              <>
                {linkedAuthorName && (
                  <div className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2.5">
                    <div className="min-w-0">
                      <p className="text-xs text-gray-400">
                        <span className="font-medium text-gray-300">Linked as:</span>{" "}
                        {linkedAuthorName}
                      </p>
                      <p className="mt-0.5 text-[11px] text-gray-600">
                        To change your linked author, visit{" "}
                        <a href="/settings" className="text-gray-500 underline underline-offset-2 hover:text-gray-300">
                          Settings
                        </a>.
                      </p>
                    </div>
                  </div>
                )}

                <form onSubmit={handleLookup} className="flex flex-col gap-3">
                  <div>
                    <input
                      ref={inputRef}
                      type="text"
                      value={query}
                      onChange={(e) => { setQuery(e.target.value); setError(null); }}
                      placeholder="DOI, arXiv URL, author URL, or name…"
                      className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                      disabled={loading}
                      autoComplete="off"
                      spellCheck={false}
                    />
                    {detectedType && !error && (
                      <p className="mt-1.5 text-xs text-teal-400/80">
                        {hintMap[detectedType]}
                      </p>
                    )}
                    {!detectedType && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] font-medium uppercase tracking-wider text-gray-600">Accepts</span>
                        <span className="inline-flex items-center rounded-full border border-sky-500/25 bg-sky-500/10 px-2.5 py-0.5 text-[11px] font-medium text-sky-400">
                          DOI
                        </span>
                        <span className="inline-flex items-center rounded-full border border-teal-500/25 bg-teal-500/10 px-2.5 py-0.5 text-[11px] font-medium text-teal-400">
                          arXiv URL
                        </span>
                        <span className="inline-flex items-center rounded-full border border-purple-500/25 bg-purple-500/10 px-2.5 py-0.5 text-[11px] font-medium text-purple-400">
                          INSPIRE profile
                        </span>
                        <span className="inline-flex items-center rounded-full border border-orange-500/25 bg-orange-500/10 px-2.5 py-0.5 text-[11px] font-medium text-orange-400">
                          DBLP profile
                        </span>
                        <span className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] font-medium text-gray-400">
                          author name
                        </span>
                      </div>
                    )}
                  </div>

                  {error && (
                    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                      {error}
                    </div>
                  )}

                  <div className="flex justify-end gap-3 pt-1">
                    <button
                      type="button"
                      onClick={onClose}
                      disabled={loading}
                      className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !query.trim()}
                      className="rounded-lg bg-white px-5 py-2 text-sm font-semibold text-gray-950 shadow-lg transition-opacity hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {loading ? (
                        <span className="flex items-center gap-2"><Spinner /> Looking up…</span>
                      ) : (
                        "Look up"
                      )}
                    </button>
                  </div>
                </form>
              </>
            )}

            {/* ── Direct confirm (INSPIRE / DBLP author URL) ──────────── */}
            {phase.type === "direct-confirm" && (
              <>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      phase.source === "inspire"
                        ? "bg-purple-500/15 text-purple-400"
                        : "bg-orange-500/15 text-orange-400"
                    }`}>
                      {phase.source === "inspire" ? "INSPIRE-HEP" : "DBLP"}
                    </span>
                    <p className="text-sm font-medium text-white">Author profile detected</p>
                  </div>
                  <p className="text-xs text-gray-400 font-mono break-all">{query.trim()}</p>
                  <p className="mt-2 text-xs text-gray-500">
                    Citey will import all papers from this profile and cross-check other sources for additional coverage.
                  </p>
                </div>

                {importError && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                    {importError}
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => { setPhase({ type: "input" }); setImportError(null); }}
                    disabled={anyBusy}
                    className="flex-1 rounded-lg border border-white/10 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                  >
                    Back
                  </button>
                  <button
                    onClick={() => handleImport(phase.authorId, undefined, phase.source)}
                    disabled={anyBusy}
                    className="flex-1 rounded-lg bg-white py-2 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:opacity-50"
                  >
                    {importingId ? (
                      <span className="flex items-center justify-center gap-2"><Spinner /> Importing…</span>
                    ) : (
                      "Import all papers"
                    )}
                  </button>
                </div>
              </>
            )}

            {/* ── Author select (arXiv, DOI no-author, name search) ───── */}
            {phase.type === "author-select" && (
              <>
                {/* Paper banner */}
                {phase.paper && (
                  <div className="flex items-start gap-2 rounded-lg border border-teal-500/25 bg-teal-500/10 px-3 py-2.5">
                    <svg className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <p className="text-xs text-teal-300 leading-relaxed">
                      <span className="font-medium">Found:</span> {phase.paper.title}
                      {phase.paper.year && (
                        <span className="ml-1 text-teal-400/70">({phase.paper.year})</span>
                      )}
                    </p>
                  </div>
                )}

                {importError && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                    {importError}
                  </div>
                )}

                {phase.candidates.length > 0 ? (() => {
                  const linkedMatch = linkedAuthorId
                    ? phase.candidates.find(
                        (a) => normalizeAuthorId(a.id) === normalizeAuthorId(linkedAuthorId)
                      )
                    : null;

                  if (linkedMatch) {
                    // Linked author found in this paper
                    return (
                      <>
                        <p className="text-xs font-medium text-gray-500">
                          Your linked author was found in this paper:
                        </p>
                        <AuthorCard author={linkedMatch} highlight anyBusy={anyBusy} />
                        {linkedAuthorId && phase.resolvedDoi && (
                          <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                            <p className="text-xs text-gray-400">
                              <span className="font-medium text-gray-300">Just this paper?</span>{" "}
                              You can{" "}
                              <button
                                onClick={() => handleFallback(phase.resolvedDoi!)}
                                disabled={anyBusy}
                                className="text-gray-300 underline underline-offset-2 hover:text-white disabled:opacity-50"
                              >
                                {fallbackLoading ? "Adding…" : "add just this paper"}
                              </button>{" "}
                              without importing your full profile.
                            </p>
                          </div>
                        )}
                      </>
                    );
                  }

                  // Linked author not found, or no linked author
                  const label = linkedAuthorId
                    ? "All co-authors for this paper:"
                    : phase.paper
                      ? "Select which author is you to link your profile and import all your papers:"
                      : "Select your profile to import all your papers:";

                  return (
                    <>
                      {linkedAuthorId && !linkedMatch && (
                        <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2.5">
                          <p className="text-xs text-amber-300">
                            <span className="font-medium">{linkedAuthorName}</span> was not found in this paper. They may publish under a different name.
                          </p>
                        </div>
                      )}
                      <p className="text-xs font-medium text-gray-500">{label}</p>
                      {phase.candidates.map((author) => (
                        <AuthorCard key={author.id} author={author} anyBusy={anyBusy} />
                      ))}
                      {phase.resolvedDoi && linkedAuthorId && (
                        <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                          <p className="text-xs text-gray-400">
                            <span className="font-medium text-gray-300">Just this paper?</span>{" "}
                            You can{" "}
                            <button
                              onClick={() => handleFallback(phase.resolvedDoi!)}
                              disabled={anyBusy}
                              className="text-gray-300 underline underline-offset-2 hover:text-white disabled:opacity-50"
                            >
                              {fallbackLoading ? "Adding…" : "add just this paper"}
                            </button>{" "}
                            without importing your full profile.
                          </p>
                        </div>
                      )}
                    </>
                  );
                })() : (
                  phase.paper ? (
                    linkedAuthorId ? (
                      <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                        <p className="text-xs text-gray-400">
                          No author profiles found for this paper. You can still{" "}
                          <button
                            onClick={() => handleFallback(phase.resolvedDoi!)}
                            disabled={fallbackLoading}
                            className="text-gray-300 underline underline-offset-2 hover:text-white disabled:opacity-50"
                          >
                            {fallbackLoading ? "Adding…" : "add just this paper"}
                          </button>{" "}
                          to your tracked list.
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2.5">
                        <p className="text-xs text-amber-300">
                          No author profiles were found for this paper. Try pasting a DOI, or link your profile first via a paper you are listed on.
                        </p>
                      </div>
                    )
                  ) : (
                    <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2.5">
                      <p className="text-xs text-amber-300">
                        No matching author profiles found. Try a different spelling or use a DOI or arXiv URL instead.
                      </p>
                    </div>
                  )
                )}

                <button
                  onClick={() => { setPhase({ type: "input" }); setImportError(null); }}
                  disabled={anyBusy}
                  className="self-start text-xs text-gray-500 transition-colors hover:text-gray-300 disabled:opacity-50"
                >
                  Back
                </button>
              </>
            )}

            {/* ── Author not found (DOI with linked author) ────────────── */}
            {phase.type === "author-not-found" && (
              <>
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
                  <p className="text-sm font-semibold text-amber-300">Author not detected</p>
                  <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
                    Your linked profile{" "}
                    <span className="font-semibold text-white">&ldquo;{phase.check.linkedAuthor}&rdquo;</span>{" "}
                    does not appear in the author list for:
                  </p>
                  <p className="mt-2 text-xs font-semibold text-white/90 leading-snug">
                    {phase.check.paperTitle || query}
                  </p>
                  {phase.check.paperAuthors.length > 0 && (
                    <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed">
                      Listed authors:{" "}
                      {phase.check.paperAuthors.slice(0, 6).join(", ")}
                      {phase.check.paperAuthors.length > 6 && <> +{phase.check.paperAuthors.length - 6} more</>}
                    </p>
                  )}
                  <p className="mt-2.5 text-xs text-amber-200/70 leading-relaxed">
                    Some authors publish under different names. If this paper is yours, click &ldquo;Add anyway&rdquo;.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPhase({ type: "input" })}
                    className="flex-1 rounded-lg border border-white/10 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={async () => {
                      setLoading(true);
                      setError(null);
                      try {
                        const result = await addWorkChecked(query.trim(), true);
                        if (result.status === "added") { onAdded(result.work); onClose(); }
                      } catch (err) {
                        setError(err instanceof Error ? err.message : "Failed to add work.");
                        setPhase({ type: "input" });
                      } finally {
                        setLoading(false);
                      }
                    }}
                    disabled={loading}
                    className="flex-1 rounded-lg bg-white py-2 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:opacity-50"
                  >
                    {loading ? (
                      <span className="flex items-center justify-center gap-2"><Spinner /> Adding…</span>
                    ) : (
                      "Add anyway"
                    )}
                  </button>
                </div>
              </>
            )}

            {/* ── Merge confirm ────────────────────────────────────────── */}
            {phase.type === "merge-confirm" && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex flex-col gap-3">
                <div>
                  <p className="text-sm font-semibold text-amber-300">Confirm profile merge</p>
                  <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
                    Your account is linked to{" "}
                    <span className="font-semibold text-amber-200">{phase.existingAuthorName}</span>.
                    Are you sure{" "}
                    <span className="font-semibold text-amber-200">{phase.author.display_name}</span>{" "}
                    is the same person? Their papers will be combined into your tracked list.
                  </p>
                </div>
                {importError && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                    {importError}
                  </div>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => { setPhase({ type: "input" }); setImportError(null); }}
                    disabled={importingId !== null}
                    className="flex-1 rounded-lg border border-white/10 py-2 text-xs font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleImport(phase.author.id, phase.author.display_name, phase.author.source, true)}
                    disabled={importingId !== null}
                    className="flex-1 rounded-lg bg-amber-500/80 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    {importingId ? (
                      <span className="flex items-center justify-center gap-1.5"><Spinner className="h-3 w-3" /> Merging…</span>
                    ) : (
                      "Yes, same person"
                    )}
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
