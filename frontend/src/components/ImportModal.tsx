"use client";

import { useState, useEffect, useRef, FormEvent, KeyboardEvent } from "react";
import { addWorkChecked, searchAuthors, getAuthorsByPaperDoi, importByAuthor, unlinkAuthor, updateProfile } from "@/lib/api";
import type { TrackedWork, AuthorCandidate, AuthorAffiliation, AddWorkResult, LinkedAuthorEntry } from "@/lib/types";

type Tab = "import" | "doi";

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdded: (work: TrackedWork) => void;
  onImported: (count: number) => void;
  onUnlinked: () => void;
  onAliasesUpdated: (aliases: string[]) => void;
  linkedAuthorId?: string | null;
  linkedAuthorName?: string | null;
  additionalLinkedAuthors?: LinkedAuthorEntry[];
  nameAliases?: string[];
  worksCount?: number;
}

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

export default function ImportModal({
  isOpen,
  onClose,
  onAdded,
  onImported,
  onUnlinked,
  onAliasesUpdated,
  linkedAuthorId,
  linkedAuthorName,
  additionalLinkedAuthors = [],
  nameAliases = [],
  worksCount = 0,
}: ImportModalProps) {
  const [tab, setTab] = useState<Tab>("import");

  // Import tab state
  type SearchMode = "name" | "paper_doi";
  const [searchMode, setSearchMode] = useState<SearchMode>("name");
  const [authorQuery, setAuthorQuery] = useState("");
  const [paperDoiQuery, setPaperDoiQuery] = useState("");
  const [paperDoiLoading, setPaperDoiLoading] = useState(false);
  const [paperDoiError, setPaperDoiError] = useState<string | null>(null);
  const [foundPaper, setFoundPaper] = useState<{ title: string; year: number | null } | null>(null);
  const [showDoiHelp, setShowDoiHelp] = useState(false);
  const [authorResults, setAuthorResults] = useState<AuthorCandidate[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [mergeConfirm, setMergeConfirm] = useState<{
    author: AuthorCandidate;
    existingAuthorName: string;
  } | null>(null);
  const [resultsPage, setResultsPage] = useState(1);
  const [authorFilter, setAuthorFilter] = useState("");
  const RESULTS_PER_PAGE = 7;

  // Change-author confirmation
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [unlinkLoading, setUnlinkLoading] = useState(false);

  // Aliases editor
  const [aliasInput, setAliasInput] = useState("");
  const [aliases, setAliases] = useState<string[]>(nameAliases);
  const [aliasesSaving, setAliasesSaving] = useState(false);

  // DOI tab state
  const [doi, setDoi] = useState("");
  const [doiLoading, setDoiLoading] = useState(false);
  const [doiError, setDoiError] = useState<string | null>(null);
  // When the linked author isn't found in the paper, hold the check result here.
  const [doiAuthorCheck, setDoiAuthorCheck] = useState<Extract<AddWorkResult, { status: "author_not_found" }> | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const doiInputRef = useRef<HTMLInputElement>(null);
  const aliasInputRef = useRef<HTMLInputElement>(null);

  // Sync aliases when prop changes (e.g. after save).
  useEffect(() => {
    setAliases(nameAliases);
  }, [nameAliases]);

  useEffect(() => {
    if (isOpen) {
      setTab("import");
      setSearchMode("name");
      setAuthorQuery("");
      setPaperDoiQuery("");
      setPaperDoiError(null);
      setFoundPaper(null);
      setShowDoiHelp(false);
      setAuthorResults([]);
      setAuthorFilter("");
      setSearchError(null);
      setImportError(null);
      setMergeConfirm(null);
      setImportingId(null);
      setDoi("");
      setDoiError(null);
      setDoiAuthorCheck(null);
      setConfirmUnlink(false);
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
  }, [isOpen]);

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
    if (tab === "import") setTimeout(() => searchInputRef.current?.focus(), 50);
  }, [tab]);

  // ── Import tab handlers ──────────────────────────────────────────────────

  const handleAuthorSearch = async (e: FormEvent) => {
    e.preventDefault();
    const q = authorQuery.trim();
    if (!q) return;
    setSearchLoading(true);
    setSearchError(null);
    setAuthorResults([]);
    setAuthorFilter("");
    setImportError(null);
    setResultsPage(1);
    try {
      const results = await searchAuthors(q);
      setAuthorResults(results);
      if (results.length === 0) setSearchError("No authors found. Try a different name.");
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearchLoading(false);
    }
  };

  const handlePaperDoiLookup = async (e: FormEvent) => {
    e.preventDefault();
    const q = paperDoiQuery.trim();
    if (!q) return;
    setPaperDoiLoading(true);
    setPaperDoiError(null);
    setFoundPaper(null);
    setShowDoiHelp(false);
    setAuthorResults([]);
    setAuthorFilter("");
    setImportError(null);
    setResultsPage(1);
    try {
      const result = await getAuthorsByPaperDoi(q);
      setFoundPaper({ title: result.paper_title, year: result.paper_year });
      setAuthorResults(result.authors);
      if (result.authors.length === 0) setPaperDoiError("No authors found for this paper.");
    } catch (err) {
      setPaperDoiError(err instanceof Error ? err.message : "Lookup failed.");
    } finally {
      setPaperDoiLoading(false);
    }
  };

  const handleImportAuthor = async (author: AuthorCandidate, confirmMerge = false) => {
    setImportingId(author.id);
    setImportError(null);
    setMergeConfirm(null);
    try {
      const result = await importByAuthor(author.id, author.display_name, author.source, confirmMerge);
      if (result.status === "merge_required") {
        setMergeConfirm({ author, existingAuthorName: result.existing_author_name });
        setImportingId(null);
        return;
      }
      setImportingId(null);
      onImported(result.imported);
      onClose();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed.");
      setImportingId(null);
    }
  };

  type AuthorRelation = "free" | "linked" | "merge_candidate";
  const getAuthorRelation = (authorId: string): AuthorRelation => {
    if (!linkedAuthorId) return "free";
    const short = (id: string) =>
      id.startsWith("https://openalex.org/") ? id.slice("https://openalex.org/".length) : id;
    const shortIncoming = short(authorId);
    if (short(linkedAuthorId) === shortIncoming) return "linked";
    if (additionalLinkedAuthors.some((e) => short(e.id) === shortIncoming)) return "linked";
    return "merge_candidate";
  };

  const handleConfirmUnlink = async () => {
    setUnlinkLoading(true);
    try {
      await unlinkAuthor();
      onUnlinked();
      onClose();
    } catch {
      // stay open; error surfaced via toast in parent
    } finally {
      setUnlinkLoading(false);
    }
  };

  // ── Alias editor handlers ────────────────────────────────────────────────

  const commitAlias = async (newAliases: string[]) => {
    setAliasesSaving(true);
    try {
      await updateProfile({ name_aliases: newAliases });
      onAliasesUpdated(newAliases);
    } finally {
      setAliasesSaving(false);
    }
  };

  const handleAddAlias = async () => {
    const trimmed = aliasInput.trim();
    if (!trimmed || aliases.includes(trimmed)) {
      setAliasInput("");
      return;
    }
    const next = [...aliases, trimmed];
    setAliases(next);
    setAliasInput("");
    await commitAlias(next);
  };

  const handleRemoveAlias = async (alias: string) => {
    const next = aliases.filter((a) => a !== alias);
    setAliases(next);
    await commitAlias(next);
  };

  const handleAliasKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddAlias();
    }
  };

  // ── DOI tab handlers ─────────────────────────────────────────────────────

  const handleAddDoi = async (e: FormEvent, force = false) => {
    e?.preventDefault();
    const trimmed = doi.trim();
    if (!trimmed) {
      setDoiError("Please enter a DOI.");
      return;
    }
    setDoiLoading(true);
    setDoiError(null);
    setDoiAuthorCheck(null);
    try {
      const result = await addWorkChecked(trimmed, force);
      if (result.status === "added") {
        onAdded(result.work);
        onClose();
      } else {
        // Author not found — surface the confirmation prompt.
        setDoiAuthorCheck(result);
      }
    } catch (err) {
      setDoiError(err instanceof Error ? err.message : "Failed to add work.");
    } finally {
      setDoiLoading(false);
    }
  };

  if (!isOpen) return null;

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
      <div className="relative z-10 flex w-full max-w-md flex-col rounded-2xl border border-white/10 bg-gray-900 shadow-2xl
                      max-h-[90vh] sm:max-h-[85vh]">
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

        {/* Tabs */}
        <div className="shrink-0 mb-5 mx-6 flex rounded-lg border border-white/10 bg-gray-800 p-1">
          {(["import", "doi"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setConfirmUnlink(false); setDoiAuthorCheck(null); }}
              className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-white text-gray-950 shadow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {t === "import" ? "Import Papers" : "Add by DOI"}
            </button>
          ))}
        </div>

        {/* ── Scrollable tab content ── */}
        <div className="flex-1 overflow-y-auto px-6 pb-6">

        {/* ── Import tab ── */}
        {tab === "import" && (
          <div className="flex flex-col gap-4">
            {/* Change-author confirmation panel */}
            {confirmUnlink ? (
              <div className="flex flex-col gap-4">
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
                  <p className="text-sm font-semibold text-amber-300">Change linked author?</p>
                  <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
                    This will permanently delete{" "}
                    <span className="font-semibold">
                      {worksCount} tracked work{worksCount !== 1 ? "s" : ""}
                    </span>{" "}
                    and all their citation notifications. You&apos;ll be able to link a different
                    author profile and re-import from scratch.
                  </p>
                  <p className="mt-2 text-xs text-amber-400 font-medium">This cannot be undone.</p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setConfirmUnlink(false)}
                    disabled={unlinkLoading}
                    className="flex-1 rounded-lg border border-white/10 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleConfirmUnlink}
                    disabled={unlinkLoading}
                    className="flex-1 rounded-lg bg-red-500/80 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    {unlinkLoading ? (
                      <span className="flex items-center justify-center gap-1.5">
                        <Spinner className="h-3.5 w-3.5" /> Deleting…
                      </span>
                    ) : (
                      "Yes, delete and change"
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* Linked author banner */}
                {linkedAuthorId ? (
                  <div className="rounded-lg border border-white/15 bg-white/5 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-xs font-semibold text-gray-300">Linked author: </span>
                        <span className="text-xs text-gray-200">
                          {linkedAuthorName || (linkedAuthorId ? "Unknown author" : "")}
                        </span>
                        {additionalLinkedAuthors.length > 0 && (
                          <span className="text-xs text-gray-400">
                            {" "}+ {additionalLinkedAuthors.map((e) => e.name || "Unknown").join(", ")}
                          </span>
                        )}
                        <p className="mt-0.5 text-[11px] text-gray-500">
                          This account is locked to this author. Only their papers can be imported.
                        </p>
                      </div>
                      <button
                        onClick={() => setConfirmUnlink(true)}
                        className="shrink-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-400 transition-colors hover:bg-amber-500/20"
                      >
                        Change
                      </button>
                    </div>

                    {/* Name aliases chip editor */}
                    <div className="mt-3 border-t border-white/5 pt-3">
                      <p className="mb-1.5 text-[11px] font-semibold text-gray-400">
                        Accepted name aliases{" "}
                        <span className="font-normal text-gray-600">
                          , add alternate names you publish under
                        </span>
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {aliases.map((alias) => (
                          <span
                            key={alias}
                            className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-gray-800 pl-2.5 pr-1.5 py-0.5 text-[11px] text-gray-300"
                          >
                            {alias}
                            <button
                              onClick={() => handleRemoveAlias(alias)}
                              disabled={aliasesSaving}
                              className="rounded-full p-0.5 text-gray-500 hover:text-red-400 transition-colors disabled:opacity-40"
                              aria-label={`Remove alias ${alias}`}
                            >
                              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </span>
                        ))}
                      </div>
                      <div className="mt-2 flex gap-1.5">
                        <input
                          ref={aliasInputRef}
                          type="text"
                          value={aliasInput}
                          onChange={(e) => setAliasInput(e.target.value)}
                          onKeyDown={handleAliasKeyDown}
                          placeholder="e.g. Jane Doe"
                          className="flex-1 rounded-md border border-white/10 bg-gray-800 px-2.5 py-1 text-xs text-white placeholder-gray-600 outline-none focus:border-white/40 focus:ring-1 focus:ring-white/20"
                          disabled={aliasesSaving}
                        />
                        <button
                          onClick={handleAddAlias}
                          disabled={!aliasInput.trim() || aliasesSaving}
                          className="rounded-md bg-white/10 px-2.5 py-1 text-xs font-semibold text-white transition-colors hover:bg-white/15 disabled:opacity-40"
                        >
                          {aliasesSaving ? <Spinner className="h-3 w-3" /> : "Add"}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-gray-400">
                    Search your author profile on{" "}
                    <span className="font-medium text-gray-300">OpenAlex</span> to bulk-import
                    all your publications at once. Your account will be linked to the first
                    author you import.
                  </p>
                )}

                {/* Search mode toggle */}
                <div className="flex rounded-lg border border-white/10 bg-gray-800/60 p-0.5">
                  {(["name", "paper_doi"] as SearchMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => {
                        setSearchMode(mode);
                        setAuthorResults([]);
                        setSearchError(null);
                        setPaperDoiError(null);
                        setFoundPaper(null);
                        setResultsPage(1);
                      }}
                      className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-colors ${
                        searchMode === mode
                          ? "bg-white/10 text-white"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {mode === "name" ? "Search by name" : "Find via paper DOI"}
                    </button>
                  ))}
                </div>

                {/* ── Name search form ── */}
                {searchMode === "name" && (
                  <>
                    <form onSubmit={handleAuthorSearch} className="flex gap-2">
                      <input
                        ref={searchInputRef}
                        type="text"
                        value={authorQuery}
                        onChange={(e) => setAuthorQuery(e.target.value)}
                        placeholder="Your name or ORCID (e.g. Jane Doe)"
                        className="flex-1 rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                        disabled={searchLoading || importingId !== null}
                      />
                      <button
                        type="submit"
                        disabled={searchLoading || !authorQuery.trim() || importingId !== null}
                        className="rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {searchLoading ? <Spinner /> : "Search"}
                      </button>
                    </form>
                    <p className="text-xs text-gray-500">
                      Have an ORCID?{" "}
                      <a
                        href="https://orcid.org"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline underline-offset-2 hover:text-gray-300"
                      >
                        Paste it in the name field
                      </a>{" "}
                      for an exact match.
                    </p>
                  </>
                )}

                {/* ── Paper DOI lookup form ── */}
                {searchMode === "paper_doi" && (
                  <>
                    <p className="text-xs text-gray-400">
                      Paste the DOI of any paper the author published. We&apos;ll look it up
                      and show the exact co-authors so you can pick the right person.
                    </p>
                    <form onSubmit={handlePaperDoiLookup} className="flex gap-2">
                      <input
                        type="text"
                        value={paperDoiQuery}
                        onChange={(e) => setPaperDoiQuery(e.target.value)}
                        placeholder="e.g. 10.1038/s41586-021-03819-2"
                        className="flex-1 rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                        disabled={paperDoiLoading || importingId !== null}
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <button
                        type="submit"
                        disabled={paperDoiLoading || !paperDoiQuery.trim() || importingId !== null}
                        className="rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {paperDoiLoading ? <Spinner /> : "Look up"}
                      </button>
                    </form>
                    {foundPaper && (
                      <div className="flex items-start gap-2 rounded-lg border border-teal-500/25 bg-teal-500/10 px-3 py-2.5">
                        <svg className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <p className="text-xs text-teal-300 leading-relaxed">
                          <span className="font-medium">Found:</span> {foundPaper.title}
                          {foundPaper.year && <span className="ml-1 text-teal-400/70">({foundPaper.year})</span>}
                        </p>
                      </div>
                    )}
                    {paperDoiError && (
                      <div className="flex flex-col gap-2">
                        <p className="text-sm text-red-400">{paperDoiError}</p>
                        <button
                          type="button"
                          onClick={() => setShowDoiHelp((v) => !v)}
                          className="self-start rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:border-white/20 hover:text-gray-300"
                        >
                          {showDoiHelp ? "Hide tips" : "Need help?"}
                        </button>
                        {showDoiHelp && (
                          <div className="rounded-xl border border-white/10 bg-gray-800/60 p-4 text-xs text-gray-400 leading-relaxed space-y-2">
                            <p className="font-semibold text-gray-300">Tips for finding a valid DOI</p>
                            <p>
                              Not all papers are indexed on Semantic Scholar. For best results,
                              find the paper directly on{" "}
                              <a
                                href="https://www.semanticscholar.org"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-teal-400 underline underline-offset-2 hover:text-teal-300"
                              >
                                semanticscholar.org
                              </a>
                              {" "}and copy the DOI from there.
                            </p>
                            <p>
                              DOIs look like{" "}
                              <span className="font-mono text-gray-300">10.1234/example</span>{" "}
                              or as a full URL{" "}
                              <span className="font-mono text-gray-300">https://doi.org/10.1234/example</span>.
                              Both formats are accepted.
                            </p>
                            <p>
                              For arXiv papers, you can also use the arXiv DOI format:{" "}
                              <span className="font-mono text-gray-300">10.48550/arXiv.2408.14845</span>.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}

                {searchMode === "name" && searchError && <p className="text-sm text-red-400">{searchError}</p>}
                {importError && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                    {importError}
                  </div>
                )}

                {mergeConfirm && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex flex-col gap-3">
                    <div>
                      <p className="text-sm font-semibold text-amber-300">Confirm profile merge</p>
                      <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
                        Your account is linked to{" "}
                        <span className="font-semibold text-amber-200">{mergeConfirm.existingAuthorName}</span>.
                        Are you sure{" "}
                        <span className="font-semibold text-amber-200">{mergeConfirm.author.display_name}</span>{" "}
                        is the same person? Their papers will be combined into your tracked list.
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setMergeConfirm(null)}
                        disabled={importingId !== null}
                        className="flex-1 rounded-lg border border-white/10 py-2 text-xs font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => handleImportAuthor(mergeConfirm.author, true)}
                        disabled={importingId !== null}
                        className="flex-1 rounded-lg bg-amber-500/80 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                      >
                        {importingId === mergeConfirm.author.id ? (
                          <span className="flex items-center justify-center gap-1.5">
                            <Spinner className="h-3 w-3" /> Merging…
                          </span>
                        ) : (
                          "Yes, they're the same person"
                        )}
                      </button>
                    </div>
                  </div>
                )}

                {authorResults.length > 0 && (() => {
                  const filtered = authorFilter.trim()
                    ? authorResults.filter((a) =>
                        a.display_name.toLowerCase().includes(authorFilter.toLowerCase())
                      )
                    : authorResults;
                  const totalPages = Math.ceil(filtered.length / RESULTS_PER_PAGE);
                  const paginated = filtered.slice(
                    (resultsPage - 1) * RESULTS_PER_PAGE,
                    resultsPage * RESULTS_PER_PAGE
                  );
                  return (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs font-medium text-gray-500">
                      {searchMode === "paper_doi"
                        ? "Select the author to import all their papers:"
                        : "Select your profile to import all papers:"}
                    </p>
                    {searchMode === "paper_doi" && authorResults.length > 8 && (
                      <input
                        type="text"
                        value={authorFilter}
                        onChange={(e) => { setAuthorFilter(e.target.value); setResultsPage(1); }}
                        placeholder="Filter by name…"
                        className="w-full rounded-lg border border-white/10 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                      />
                    )}
                    {paginated.map((author) => {
                      const relation = getAuthorRelation(author.id);
                      return (
                        <div
                          key={author.id}
                          className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-gray-800 px-4 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <p className="truncate text-sm font-medium text-white">{author.display_name}</p>
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
                            {author.topics.length > 0 && (
                              <p className="truncate text-xs text-indigo-400/80">{author.topics.join(" · ")}</p>
                            )}
                            <p className="text-xs text-gray-500">
                              {author.works_count} works
                              {author.h_index > 0 && <span className="ml-2">h-index {author.h_index}</span>}
                            </p>
                            {relation === "merge_candidate" && (
                              <p className="mt-0.5 text-[11px] text-amber-400/80">Different profile — confirm to merge</p>
                            )}
                          </div>
                          {relation === "merge_candidate" ? (
                            <button
                              onClick={() => handleImportAuthor(author)}
                              disabled={importingId !== null}
                              className="shrink-0 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300 transition-colors hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {importingId === author.id ? (
                                <span className="flex items-center gap-1.5"><Spinner className="h-3 w-3" /> Checking…</span>
                              ) : "Merge"}
                            </button>
                          ) : (
                            <button
                              onClick={() => handleImportAuthor(author)}
                              disabled={importingId !== null}
                              className="shrink-0 rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {importingId === author.id ? (
                                <span className="flex items-center gap-1.5"><Spinner className="h-3 w-3" /> Importing…</span>
                              ) : "Import"}
                            </button>
                          )}
                        </div>
                      );
                    })}
                    {filtered.length === 0 && authorFilter && (
                      <p className="text-xs text-gray-500">No authors match &ldquo;{authorFilter}&rdquo;.</p>
                    )}
                    {totalPages > 1 && (
                      <div className="mt-1 flex items-center justify-between gap-2">
                        <button
                          onClick={() => setResultsPage((p) => p - 1)}
                          disabled={resultsPage === 1}
                          className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:border-white/20 hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-30"
                        >
                          ← Prev
                        </button>
                        <span className="text-xs text-gray-500">
                          Page {resultsPage} of {totalPages}
                        </span>
                        <button
                          onClick={() => setResultsPage((p) => p + 1)}
                          disabled={resultsPage >= totalPages}
                          className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:border-white/20 hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-30"
                        >
                          Next →
                        </button>
                      </div>
                    )}
                  </div>
                  );
                })()}
              </>
            )}
          </div>
        )}

        {/* ── DOI tab ── */}
        {tab === "doi" && (
          <div className="flex flex-col gap-4">
            {/* Author-not-found confirmation */}
            {doiAuthorCheck ? (
              <div className="flex flex-col gap-4">
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
                  <p className="text-sm font-semibold text-amber-300">Author not detected</p>
                  <p className="mt-1.5 text-xs text-amber-200/80 leading-relaxed">
                    Your linked profile{" "}
                    <span className="font-semibold text-white">
                      &ldquo;{doiAuthorCheck.linkedAuthor}&rdquo;
                    </span>{" "}
                    doesn&apos;t appear in the author list for:
                  </p>
                  <p className="mt-2 text-xs font-semibold text-white/90 leading-snug">
                    {doiAuthorCheck.paperTitle || doi}
                  </p>
                  {doiAuthorCheck.paperAuthors.length > 0 && (
                    <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed">
                      Listed authors:{" "}
                      {doiAuthorCheck.paperAuthors.slice(0, 6).join(", ")}
                      {doiAuthorCheck.paperAuthors.length > 6 && (
                        <> +{doiAuthorCheck.paperAuthors.length - 6} more</>
                      )}
                    </p>
                  )}
                  <p className="mt-2.5 text-xs text-amber-200/70 leading-relaxed">
                    Some authors publish under different names. If this paper is yours, click
                    &ldquo;Add anyway&rdquo;. You can also add an alias in the Import tab so
                    this won&apos;t be flagged in future.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setDoiAuthorCheck(null)}
                    className="flex-1 rounded-lg border border-white/10 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={(e) => handleAddDoi(e as unknown as FormEvent, true)}
                    disabled={doiLoading}
                    className="flex-1 rounded-lg bg-white py-2 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:opacity-50"
                  >
                    {doiLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <Spinner /> Adding…
                      </span>
                    ) : (
                      "Add anyway"
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleAddDoi} className="flex flex-col gap-4">
                <div>
                  <label
                    htmlFor="doi-input"
                    className="mb-1.5 block text-sm font-medium text-gray-300"
                  >
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
                      <span className="flex items-center gap-2">
                        <Spinner /> Adding…
                      </span>
                    ) : (
                      "Add Work"
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}

        </div>{/* end scrollable content */}
      </div>
    </div>
  );
}
