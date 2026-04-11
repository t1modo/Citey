"use client";

import { useState, useEffect, useRef, FormEvent } from "react";
import {
  addWorkChecked,
  getAuthorsByPaperDoi,
  importByAuthor,
} from "@/lib/api";
import type {
  TrackedWork,
  AddWorkResult,
  AuthorCandidate,
  AuthorAffiliation,
} from "@/lib/types";

type Tab = "doi" | "arxiv";

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdded: (work: TrackedWork) => void;
  onImported: (count: number) => void;
  linkedAuthorId?: string | null;
  linkedAuthorName?: string | null;
}

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

/** Normalise an OpenAlex or S2 author ID for comparison. */
function normalizeAuthorId(id: string): string {
  return id.startsWith("https://openalex.org/") ? id.slice(21) : id;
}

export default function ImportModal({
  isOpen,
  onClose,
  onAdded,
  onImported,
  linkedAuthorId,
  linkedAuthorName,
}: ImportModalProps) {
  const [tab, setTab] = useState<Tab>("doi");

  // ── DOI tab ──────────────────────────────────────────────────────────────
  const [doi, setDoi] = useState("");
  const [doiLoading, setDoiLoading] = useState(false);
  const [doiError, setDoiError] = useState<string | null>(null);
  const [doiAuthorCheck, setDoiAuthorCheck] = useState<
    Extract<AddWorkResult, { status: "author_not_found" }> | null
  >(null);

  // ── arXiv tab — phase 1: paper lookup ────────────────────────────────────
  const [arxivQuery, setArxivQuery] = useState("");
  const [arxivLookupLoading, setArxivLookupLoading] = useState(false);
  const [arxivLookupError, setArxivLookupError] = useState<string | null>(null);
  const [arxivFoundPaper, setArxivFoundPaper] = useState<{
    title: string;
    year: number | null;
  } | null>(null);
  const [arxivAuthors, setArxivAuthors] = useState<AuthorCandidate[]>([]);
  const [arxivResolvedDoi, setArxivResolvedDoi] = useState<string | null>(null);

  // ── arXiv tab — phase 2: author import ───────────────────────────────────
  const [arxivImportingId, setArxivImportingId] = useState<string | null>(null);
  const [arxivImportError, setArxivImportError] = useState<string | null>(null);
  const [arxivMergeConfirm, setArxivMergeConfirm] = useState<{
    author: AuthorCandidate;
    existingAuthorName: string;
  } | null>(null);

  // ── arXiv tab — fallback: add just this paper ────────────────────────────
  const [arxivFallbackLoading, setArxivFallbackLoading] = useState(false);

  const doiInputRef = useRef<HTMLInputElement>(null);
  const arxivInputRef = useRef<HTMLInputElement>(null);

  // ── Reset on open ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (isOpen) {
      setTab("doi");
      setDoi("");
      setDoiError(null);
      setDoiAuthorCheck(null);
      resetArxiv();
      setTimeout(() => doiInputRef.current?.focus(), 50);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const resetArxiv = () => {
    setArxivQuery("");
    setArxivLookupLoading(false);
    setArxivLookupError(null);
    setArxivFoundPaper(null);
    setArxivAuthors([]);
    setArxivResolvedDoi(null);
    setArxivImportingId(null);
    setArxivImportError(null);
    setArxivMergeConfirm(null);
    setArxivFallbackLoading(false);
  };

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (tab === "doi") setTimeout(() => doiInputRef.current?.focus(), 50);
    if (tab === "arxiv") setTimeout(() => arxivInputRef.current?.focus(), 50);
  }, [tab]);

  // ── DOI handler ───────────────────────────────────────────────────────────

  const handleAddDoi = async (e: FormEvent | null, force = false) => {
    e?.preventDefault();
    const trimmed = doi.trim();
    if (!trimmed) { setDoiError("Please enter a DOI."); return; }
    setDoiLoading(true);
    setDoiError(null);
    setDoiAuthorCheck(null);
    try {
      const result = await addWorkChecked(trimmed, force);
      if (result.status === "added") { onAdded(result.work); onClose(); }
      else { setDoiAuthorCheck(result); }
    } catch (err) {
      setDoiError(err instanceof Error ? err.message : "Failed to add work.");
    } finally {
      setDoiLoading(false);
    }
  };

  // ── arXiv helpers ─────────────────────────────────────────────────────────

  const parseArxivId = (input: string): string | null => {
    const trimmed = input.trim();
    const urlMatch = trimmed.match(/arxiv\.org\/(?:abs|pdf)\/([^\s?#/]+)/i);
    if (urlMatch) return urlMatch[1].replace(/v\d+$/i, "");
    const prefixMatch = trimmed.match(/^arxiv:([^\s]+)/i);
    if (prefixMatch) return prefixMatch[1].replace(/v\d+$/i, "");
    if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(trimmed)) return trimmed.replace(/v\d+$/i, "");
    if (/^[a-z-]+\/\d{7}$/i.test(trimmed)) return trimmed;
    return null;
  };

  // Phase 1 — look up paper + co-authors
  const handleArxivLookup = async (e: FormEvent) => {
    e.preventDefault();
    const arxivId = parseArxivId(arxivQuery);
    if (!arxivId) {
      setArxivLookupError(
        "Could not parse arXiv ID. Paste the full URL (e.g. https://arxiv.org/abs/2301.12345) or a bare ID like 2301.12345."
      );
      return;
    }
    const resolvedDoi = `10.48550/arXiv.${arxivId}`;
    setArxivLookupLoading(true);
    setArxivLookupError(null);
    setArxivFoundPaper(null);
    setArxivAuthors([]);
    setArxivResolvedDoi(null);
    setArxivImportError(null);
    setArxivMergeConfirm(null);
    setArxivFallbackCheck(null);
    try {
      const result = await getAuthorsByPaperDoi(resolvedDoi);
      setArxivFoundPaper({ title: result.paper_title, year: result.paper_year });
      setArxivAuthors(result.authors);
      setArxivResolvedDoi(resolvedDoi);
    } catch (err) {
      setArxivLookupError(err instanceof Error ? err.message : "Lookup failed.");
    } finally {
      setArxivLookupLoading(false);
    }
  };

  // Phase 2 — import all papers by a chosen author
  const handleArxivImport = async (author: AuthorCandidate, confirmMerge = false) => {
    setArxivImportingId(author.id);
    setArxivImportError(null);
    setArxivMergeConfirm(null);
    try {
      const result = await importByAuthor(author.id, author.display_name, author.source, confirmMerge);
      if (result.status === "merge_required") {
        setArxivMergeConfirm({ author, existingAuthorName: result.existing_author_name });
        setArxivImportingId(null);
        return;
      }
      onImported(result.imported);
      onClose();
    } catch (err) {
      setArxivImportError(err instanceof Error ? err.message : "Import failed.");
      setArxivImportingId(null);
    }
  };

  // Fallback — add just this one arXiv paper.
  // Always uses force=true: the user has already made their explicit intent
  // clear by clicking "add just this paper", so a second author-check
  // confirmation would be unnecessary friction.
  const handleArxivFallback = async () => {
    if (!arxivResolvedDoi) return;
    setArxivFallbackLoading(true);
    try {
      const result = await addWorkChecked(arxivResolvedDoi, true);
      if (result.status === "added") { onAdded(result.work); onClose(); }
    } catch (err) {
      setArxivImportError(err instanceof Error ? err.message : "Failed to add work.");
    } finally {
      setArxivFallbackLoading(false);
    }
  };

  // Find the linked author in the co-author list (if any)
  const linkedMatch = linkedAuthorId
    ? arxivAuthors.find(
        (a) => normalizeAuthorId(a.id) === normalizeAuthorId(linkedAuthorId)
      )
    : null;

  const busy = arxivImportingId !== null || arxivFallbackLoading;

  if (!isOpen) return null;

  // ── Shared: author-not-found confirmation ────────────────────────────────

  const AuthorNotFoundPanel = ({
    check,
    label,
    loading,
    onCancel,
    onConfirm,
  }: {
    check: Extract<AddWorkResult, { status: "author_not_found" }>;
    label: string;
    loading: boolean;
    onCancel: () => void;
    onConfirm: () => void;
  }) => (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
        <p className="text-sm font-semibold text-amber-300">Author not detected</p>
        <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
          Your linked profile{" "}
          <span className="font-semibold text-white">&ldquo;{check.linkedAuthor}&rdquo;</span>{" "}
          doesn&apos;t appear in the author list for:
        </p>
        <p className="mt-2 text-xs font-semibold text-white/90 leading-snug">
          {check.paperTitle || label}
        </p>
        {check.paperAuthors.length > 0 && (
          <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed">
            Listed authors:{" "}
            {check.paperAuthors.slice(0, 6).join(", ")}
            {check.paperAuthors.length > 6 && <> +{check.paperAuthors.length - 6} more</>}
          </p>
        )}
        <p className="mt-2.5 text-xs text-amber-200/70 leading-relaxed">
          Some authors publish under different names. If this paper is yours, click &ldquo;Add anyway&rdquo;.
        </p>
      </div>
      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="flex-1 rounded-lg border border-white/10 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
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
    </div>
  );

  // ── Shared: author card row ───────────────────────────────────────────────

  const AuthorCard = ({ author, highlight = false }: { author: AuthorCandidate; highlight?: boolean }) => (
    <div className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-3 ${
      highlight
        ? "border-teal-500/30 bg-teal-500/10"
        : "border-white/10 bg-gray-800"
    }`}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-white">{author.display_name}</p>
          {highlight && (
            <span className="shrink-0 rounded-full bg-teal-500/20 px-2 py-0.5 text-[10px] font-semibold text-teal-400">
              You
            </span>
          )}
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
            author.source === "semantic_scholar"
              ? "bg-teal-500/15 text-teal-400"
              : "bg-blue-500/15 text-blue-400"
          }`}>
            {author.source === "semantic_scholar" ? "S2" : "OA"}
          </span>
        </div>
        {author.affiliations.length > 0 && (
          <p className="truncate text-xs text-gray-400">
            {author.affiliations
              .map((a: AuthorAffiliation) =>
                a.year_range ? `${a.name} (${a.year_range})` : a.name
              )
              .join(" · ")}
          </p>
        )}
        <p className="text-xs text-gray-500">
          {author.works_count} works
          {author.h_index > 0 && <span className="ml-2">h-index {author.h_index}</span>}
        </p>
      </div>
      <button
        onClick={() => handleArxivImport(author)}
        disabled={busy}
        className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          highlight
            ? "bg-teal-500/80 text-white hover:bg-teal-500"
            : "bg-white/10 text-white hover:bg-white/15"
        }`}
      >
        {arxivImportingId === author.id ? (
          <span className="flex items-center gap-1.5"><Spinner className="h-3 w-3" /> Importing…</span>
        ) : (
          "Import"
        )}
      </button>
    </div>
  );

  // ── "add just this paper" fallback ──────────────────────────────────────
  // Only shown when a linked author already exists.  Without a linked author
  // the arXiv flow should always go through full author-linking — the fallback
  // would let users build a collection of papers with no author attached, which
  // isn't the intended use of this app.

  const FallbackPanel = () => {
    if (!linkedAuthorId) return null;
    return (
      <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
        <p className="text-xs text-gray-400">
          <span className="font-medium text-gray-300">Just this paper?</span>{" "}
          You can{" "}
          <button
            onClick={handleArxivFallback}
            disabled={busy}
            className="text-gray-300 underline underline-offset-2 hover:text-white disabled:opacity-50"
          >
            {arxivFallbackLoading ? "Adding…" : "add just this paper"}
          </button>{" "}
          without importing your full profile.
        </p>
      </div>
    );
  };

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
            Add a Paper
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

        {/* Tabs */}
        <div className="shrink-0 mb-5 mx-6 flex rounded-lg border border-white/10 bg-gray-800 p-1">
          {(["doi", "arxiv"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => {
                setTab(t);
                setDoiAuthorCheck(null);
                resetArxiv();
              }}
              className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
                tab === t ? "bg-white text-gray-950 shadow" : "text-gray-400 hover:text-white"
              }`}
            >
              {t === "doi" ? "Add by DOI" : "Add by arXiv"}
            </button>
          ))}
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-6 pb-6">

          {/* ── DOI tab ───────────────────────────────────────────────────── */}
          {tab === "doi" && (
            <div className="flex flex-col gap-4">
              {doiAuthorCheck ? (
                <AuthorNotFoundPanel
                  check={doiAuthorCheck}
                  label={doi}
                  loading={doiLoading}
                  onCancel={() => setDoiAuthorCheck(null)}
                  onConfirm={() => handleAddDoi(null, true)}
                />
              ) : (
                <form onSubmit={handleAddDoi} className="flex flex-col gap-4">
                  <div>
                    <label htmlFor="doi-input" className="mb-1.5 block text-sm font-medium text-gray-300">
                      DOI
                    </label>
                    <input
                      ref={doiInputRef}
                      id="doi-input"
                      type="text"
                      value={doi}
                      onChange={(e) => setDoi(e.target.value)}
                      placeholder="e.g. 10.1038/s41586-021-03819-2"
                      className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                      disabled={doiLoading}
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <p className="mt-1.5 text-xs text-gray-500">
                      Bare DOIs and full{" "}
                      <span className="font-mono">https://doi.org/…</span> URLs are both accepted.
                    </p>
                  </div>

                  {doiError && (
                    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                      {doiError}
                    </div>
                  )}

                  <div className="flex justify-end gap-3 pt-1">
                    <button
                      type="button"
                      onClick={onClose}
                      disabled={doiLoading}
                      className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={doiLoading || !doi.trim()}
                      className="rounded-lg bg-white px-5 py-2 text-sm font-semibold text-gray-950 shadow-lg transition-opacity hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {doiLoading ? (
                        <span className="flex items-center gap-2"><Spinner /> Adding…</span>
                      ) : (
                        "Add Work"
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* ── arXiv tab ─────────────────────────────────────────────────── */}
          {tab === "arxiv" && (
            <div className="flex flex-col gap-4">

              {/* Linked author banner */}
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
                      </a>
                      .
                    </p>
                  </div>
                </div>
              )}

              {/* Lookup form */}
              <form onSubmit={handleArxivLookup} className="flex gap-2">
                <input
                  ref={arxivInputRef}
                  type="text"
                  value={arxivQuery}
                  onChange={(e) => setArxivQuery(e.target.value)}
                  placeholder="e.g. https://arxiv.org/abs/2301.12345"
                  className="flex-1 rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                  disabled={arxivLookupLoading || busy}
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  type="submit"
                  disabled={arxivLookupLoading || !arxivQuery.trim() || busy}
                  className="rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {arxivLookupLoading ? <Spinner /> : "Look up"}
                </button>
              </form>
              <p className="text-xs text-gray-500">
                Accepts full URLs or bare IDs like{" "}
                <span className="font-mono text-gray-400">2301.12345</span>.{" "}
                {!linkedAuthorName && "We\u2019ll find the paper\u2019s authors so you can link your profile and import all your work."}
              </p>

              {/* Lookup error */}
              {arxivLookupError && (
                <p className="text-sm text-red-400">{arxivLookupError}</p>
              )}

              {/* Found paper banner */}
              {arxivFoundPaper && (
                <div className="flex items-start gap-2 rounded-lg border border-teal-500/25 bg-teal-500/10 px-3 py-2.5">
                  <svg className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <p className="text-xs text-teal-300 leading-relaxed">
                    <span className="font-medium">Found:</span> {arxivFoundPaper.title}
                    {arxivFoundPaper.year && (
                      <span className="ml-1 text-teal-400/70">({arxivFoundPaper.year})</span>
                    )}
                  </p>
                </div>
              )}

              {/* Merge confirmation */}
              {arxivMergeConfirm && (
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex flex-col gap-3">
                  <div>
                    <p className="text-sm font-semibold text-amber-300">Confirm profile merge</p>
                    <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
                      Your account is linked to{" "}
                      <span className="font-semibold text-amber-200">{arxivMergeConfirm.existingAuthorName}</span>.
                      Are you sure{" "}
                      <span className="font-semibold text-amber-200">{arxivMergeConfirm.author.display_name}</span>{" "}
                      is the same person? Their papers will be combined into your tracked list.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setArxivMergeConfirm(null)}
                      disabled={arxivImportingId !== null}
                      className="flex-1 rounded-lg border border-white/10 py-2 text-xs font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleArxivImport(arxivMergeConfirm.author, true)}
                      disabled={arxivImportingId !== null}
                      className="flex-1 rounded-lg bg-amber-500/80 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    >
                      {arxivImportingId ? (
                        <span className="flex items-center justify-center gap-1.5"><Spinner className="h-3 w-3" /> Merging…</span>
                      ) : (
                        "Yes, same person"
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Import error */}
              {arxivImportError && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                  {arxivImportError}
                </div>
              )}

              {/* ── Author results ── */}
              {arxivAuthors.length > 0 && (() => {
                // Case A: user has a linked author AND they appear in this paper
                if (linkedAuthorId && linkedMatch) {
                  return (
                    <>
                      <p className="text-xs font-medium text-gray-500">
                        Your linked author was found in this paper:
                      </p>
                      <AuthorCard author={linkedMatch} highlight />
                      <FallbackPanel />
                    </>
                  );
                }

                // Case B: user has a linked author but they're NOT in this paper
                if (linkedAuthorId && !linkedMatch) {
                  return (
                    <>
                      <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2.5">
                        <p className="text-xs text-amber-300">
                          <span className="font-medium">{linkedAuthorName}</span> wasn&apos;t found
                          in this paper&apos;s author list. They may publish under a different name.
                        </p>
                      </div>
                      <p className="text-xs font-medium text-gray-500">All co-authors for this paper:</p>
                      {arxivAuthors.map((author) => (
                        <AuthorCard key={author.id} author={author} />
                      ))}
                      <FallbackPanel />
                    </>
                  );
                }

                // Case C: no linked author yet — full pick-your-author flow
                return (
                  <>
                    <p className="text-xs font-medium text-gray-500">
                      Select which author is you to link your profile and import all your papers:
                    </p>
                    {arxivAuthors.map((author) => (
                      <AuthorCard key={author.id} author={author} />
                    ))}
                    <FallbackPanel />
                  </>
                );
              })()}

              {/* Edge case: paper found but no author profiles available */}
              {arxivFoundPaper && arxivAuthors.length === 0 && !arxivLookupLoading && (
                linkedAuthorId ? (
                  <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                    <p className="text-xs text-gray-400">
                      No author profiles were found for this paper. You can still{" "}
                      <button
                        onClick={handleArxivFallback}
                        disabled={arxivFallbackLoading}
                        className="text-gray-300 underline underline-offset-2 hover:text-white disabled:opacity-50"
                      >
                        {arxivFallbackLoading ? "Adding…" : "add just this paper"}
                      </button>{" "}
                      to your tracked list.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2.5">
                    <p className="text-xs text-amber-300">
                      No author profiles were found for this paper. Try searching by DOI instead,
                      or link your author profile first via a paper you&apos;re listed on.
                    </p>
                  </div>
                )
              )}

            </div>
          )}

        </div>
      </div>
    </div>
  );
}
