"use client";

import { useState, useEffect, useRef, FormEvent, KeyboardEvent } from "react";
import { addWorkChecked, searchAuthors, importByAuthor, unlinkAuthor, updateProfile } from "@/lib/api";
import type { TrackedWork, AuthorCandidate, AddWorkResult } from "@/lib/types";

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
  nameAliases = [],
  worksCount = 0,
}: ImportModalProps) {
  const [tab, setTab] = useState<Tab>("import");

  // Import tab state
  const [authorQuery, setAuthorQuery] = useState("");
  const [authorResults, setAuthorResults] = useState<AuthorCandidate[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

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
      setAuthorQuery("");
      setAuthorResults([]);
      setSearchError(null);
      setImportError(null);
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
    setImportError(null);
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

  const handleImportAuthor = async (author: AuthorCandidate) => {
    setImportingId(author.id);
    setImportError(null);
    try {
      const result = await importByAuthor(author.id, author.display_name);
      onImported(result.imported);
      onClose();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed.");
      setImportingId(null);
    }
  };

  const isLockedOut = (authorId: string): boolean => {
    if (!linkedAuthorId) return false;
    const short = (id: string) =>
      id.startsWith("https://openalex.org/") ? id.slice("https://openalex.org/".length) : id;
    return short(linkedAuthorId) !== short(authorId);
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
      <div className="relative z-10 w-full max-w-md rounded-2xl border border-white/10 bg-gray-900 p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
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
        <div className="mb-5 flex rounded-lg border border-white/10 bg-gray-800 p-1">
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
                        <span className="text-xs text-gray-200">{linkedAuthorName ?? linkedAuthorId}</span>
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

                <form onSubmit={handleAuthorSearch} className="flex gap-2">
                  <input
                    ref={searchInputRef}
                    type="text"
                    value={authorQuery}
                    onChange={(e) => setAuthorQuery(e.target.value)}
                    placeholder="Your name, e.g. Jane Doe"
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

                {searchError && <p className="text-sm text-red-400">{searchError}</p>}
                {importError && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                    {importError}
                  </div>
                )}

                {authorResults.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs font-medium text-gray-500">
                      Select your profile to import all papers:
                    </p>
                    {authorResults.map((author) => {
                      const locked = isLockedOut(author.id);
                      return (
                        <div
                          key={author.id}
                          className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-3 ${
                            locked ? "border-white/5 bg-gray-800/40 opacity-50" : "border-white/10 bg-gray-800"
                          }`}
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-white">{author.display_name}</p>
                            {author.affiliations.length > 0 && (
                              <p className="truncate text-xs text-gray-400">{author.affiliations.join(" · ")}</p>
                            )}
                            <p className="text-xs text-gray-500">{author.works_count} works</p>
                            {locked && <p className="mt-0.5 text-xs text-amber-500">Not your linked author</p>}
                          </div>
                          <button
                            onClick={() => handleImportAuthor(author)}
                            disabled={importingId !== null || locked}
                            className="shrink-0 rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {importingId === author.id ? (
                              <span className="flex items-center gap-1.5">
                                <Spinner className="h-3 w-3" /> Importing…
                              </span>
                            ) : (
                              "Import"
                            )}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
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
      </div>
    </div>
  );
}
