"use client";

import { useState, useEffect, useRef, FormEvent } from "react";
import { addWork } from "@/lib/api";
import type { TrackedWork } from "@/lib/types";

interface AddWorkModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdded: (work: TrackedWork) => void;
}

export default function AddWorkModal({
  isOpen,
  onClose,
  onAdded,
}: AddWorkModalProps) {
  const [doi, setDoi] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setDoi("");
      setError(null);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmedDoi = doi.trim();
    if (!trimmedDoi) {
      setError("Please enter a DOI.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const work = await addWork(trimmedDoi);
      onAdded(work);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add work.");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-work-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-md rounded-2xl border border-white/10 bg-gray-900 p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h2
            id="add-work-title"
            className="text-lg font-semibold text-white"
          >
            Track a New Work
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

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label
              htmlFor="doi-input"
              className="mb-1.5 block text-sm font-medium text-gray-300"
            >
              DOI
            </label>
            <input
              ref={inputRef}
              id="doi-input"
              type="text"
              value={doi}
              onChange={(e) => setDoi(e.target.value)}
              placeholder="e.g. 10.1038/s41586-021-03819-2"
              className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
              disabled={loading}
              autoComplete="off"
              spellCheck={false}
            />
            <p className="mt-1.5 text-xs text-gray-500">
              Enter a DOI in the format <span className="font-mono">10.xxxx/...</span>. Both bare DOIs and full URLs are accepted.
            </p>
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
              disabled={loading || !doi.trim()}
              className="rounded-lg bg-white px-5 py-2 text-sm font-semibold text-gray-950 shadow-lg transition-opacity hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                  </svg>
                  Adding…
                </span>
              ) : (
                "Add Work"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
