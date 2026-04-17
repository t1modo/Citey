"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { sendVerificationEmail } from "@/lib/api";
import { useNotifications } from "@/contexts/NotificationsContext";
import {
  getWorks,
  deleteWork,
  getNotifications,
  pruneNotifications,
  downloadBibtex,
} from "@/lib/api";
import type { TrackedWork, Notification } from "@/lib/types";

const CITATIONS_PER_PAGE = 10;
const WORKS_PER_PAGE = 10;

type WorksSort = "year" | "citations";
import TrackedWorkCard from "@/components/TrackedWorkCard";
import ImportModal from "@/components/ImportModal";
import CountUp from "@/components/CountUp";
import ScrollReveal from "@/components/ScrollReveal";
import TiltedCard from "@/components/TiltedCard";
import Galaxy from "@/components/Galaxy";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

let toastCounter = 0;

function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col gap-2 max-w-[calc(100vw-3rem)]">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-3 rounded-xl border px-4 py-3 shadow-xl backdrop-blur-sm transition-all ${
            t.type === "success"
              ? "border-white/20 bg-gray-800/80 text-gray-200"
              : t.type === "error"
              ? "border-red-500/30 bg-red-900/80 text-red-200"
              : "border-white/20 bg-gray-800/80 text-gray-200"
          }`}
        >
          <span className="mt-0.5 text-base">
            {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}
          </span>
          <p className="flex-1 text-sm font-medium">{t.message}</p>
          <button
            onClick={() => onDismiss(t.id)}
            className="ml-2 text-current opacity-60 hover:opacity-100"
            aria-label="Dismiss"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="h-5 w-5 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

function formatDate(iso: string): string {
  // Parse date-only strings as local time to avoid UTC-offset off-by-one
  const parts = iso.split("T")[0].split("-").map(Number);
  const d = new Date(parts[0], parts[1] - 1, parts[2]);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function RecentCitationCard({
  notification,
  onMarkSeen,
}: {
  notification: Notification;
  onMarkSeen: (id: string) => void;
}) {
  const citingUrl =
    notification.citing_work_url ??
    (notification.citing_work_doi
      ? `https://doi.org/${notification.citing_work_doi}`
      : null);

  const affiliations =
    notification.citing_affiliations.length > 0
      ? notification.citing_affiliations
      : ["Independent"];

  const handleClick = () => {
    if (!notification.seen) onMarkSeen(notification.id);
  };

  return (
    <div
      className={`glass-card flex flex-col gap-3 p-4 transition-all duration-200 cursor-pointer hover:border-white/20 ${
        !notification.seen ? "border-white/15 bg-white/5" : ""
      }`}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && handleClick()}
      aria-label={`Citation: ${notification.citing_work_title}`}
    >
      {/* Header row: unread dot + badge + date */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {!notification.seen && (
            <span
              className="h-2 w-2 shrink-0 rounded-full bg-white"
              aria-label="Unread"
            />
          )}
          <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
            New citation
          </span>
        </div>
        {(notification.citing_publication_date || notification.citing_year) && (
          <span className="shrink-0 text-xs text-gray-600">
            {notification.citing_publication_date
              ? formatDate(notification.citing_publication_date)
              : notification.citing_year}
          </span>
        )}
      </div>

      {/* Citing paper title — prominent headline */}
      {citingUrl ? (
        <a
          href={citingUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-sm font-bold text-white underline decoration-dotted underline-offset-2 hover:text-gray-300 hover:decoration-solid leading-snug transition-colors"
        >
          {notification.citing_work_title || "Untitled"}
        </a>
      ) : (
        <p className="text-sm font-bold text-white leading-snug">
          {notification.citing_work_title || "Untitled"}
        </p>
      )}

      {/* Authors — directly below citing title */}
      {notification.citing_authors.length > 0 && (
        <p className="text-xs text-gray-400 leading-relaxed -mt-1">
          {notification.citing_authors.slice(0, 3).join(" · ")}
          {notification.citing_authors.length > 3 && (
            <span className="text-gray-600"> +{notification.citing_authors.length - 3} more</span>
          )}
        </p>
      )}

      {/* "cites your paper" divider */}
      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-white/5" />
        <span className="text-[10px] text-gray-600 italic">cites your paper</span>
        <div className="h-px flex-1 bg-white/5" />
      </div>

      {/* Your paper */}
      <div>
        <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-400">
          Your paper
        </p>
        <p className="text-xs text-white/70 leading-snug">
          {notification.cited_work_title || notification.cited_work_id}
        </p>
      </div>

      {/* Affiliation pills */}
      <div className="flex flex-wrap gap-1.5">
        {affiliations.slice(0, 4).map((affil) => {
          const isIndependent = affil === "Independent";
          return (
            <span
              key={affil}
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${
                isIndependent
                  ? "bg-white/5 text-gray-500 ring-white/10"
                  : "bg-white/8 text-gray-300 ring-white/10"
              }`}
            >
              {affil}
            </span>
          );
        })}
        {affiliations.length > 4 && (
          <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-white/5 text-gray-500 ring-1 ring-white/10">
            +{affiliations.length - 4} more
          </span>
        )}
      </div>
    </div>
  );
}

function VerificationBanner({ onToast }: { onToast: (msg: string, type: ToastType) => void }) {
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleResend = async () => {
    setLoading(true);
    try {
      await sendVerificationEmail();
      setSent(true);
      onToast("Verification email resent. Check your inbox.", "info");
    } catch {
      onToast("Could not resend — please try again later.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
        <p>
          <span className="font-semibold">Verify your email</span> to receive citation notification emails.
          Check your inbox for the verification link.
        </p>
        {!sent && (
          <button
            onClick={handleResend}
            disabled={loading}
            className="shrink-0 font-medium underline decoration-dotted underline-offset-2 hover:text-amber-100 disabled:opacity-50 transition-colors"
          >
            {loading ? "Sending…" : "Resend"}
          </button>
        )}
      </div>
    </div>
  );
}

function FirstPaperInfoModal({ onClose }: { onClose: () => void }) {
  const chips = [
    { icon: "🔔", label: "Email alerts" },
    { icon: "📅", label: "Daily checks" },
    { icon: "⚡", label: "Auto-updates" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.88, y: 24 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 380, damping: 28 }}
        className="relative z-10 w-full max-w-sm overflow-hidden rounded-2xl border border-white/10 bg-gray-950 shadow-2xl shadow-black/60"
      >
        {/* Top accent line */}
        <div className="h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />

        <div className="p-6">
          {/* Animated icon with pulsing rings */}
          <div className="mb-5 flex justify-center">
            <div className="relative flex h-16 w-16 items-center justify-center">
              <motion.div
                animate={{ scale: [1, 1.55, 1], opacity: [0.2, 0, 0.2] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
                className="absolute inset-0 rounded-full bg-white/15"
              />
              <motion.div
                animate={{ scale: [1, 1.9, 1], opacity: [0.1, 0, 0.1] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut", delay: 0.35 }}
                className="absolute inset-0 rounded-full bg-white/10"
              />
              <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-white/10 ring-1 ring-white/20">
                <svg className="h-7 w-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>

          {/* Staggered text */}
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.07 } } }}
            className="flex flex-col items-center text-center"
          >
            <motion.p
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              className="mb-0.5 text-xs font-semibold uppercase tracking-widest text-gray-500"
            >
              You&apos;re all set
            </motion.p>
            <motion.h2
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              className="mb-3 text-xl font-bold text-white"
            >
              Citations checked daily
            </motion.h2>
            <motion.p
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              className="mb-5 text-sm leading-relaxed text-gray-400"
            >
              Papers added today will be scanned tonight at midnight. You&apos;ll get an email the moment a new citation is found.
            </motion.p>

            {/* Chips */}
            <motion.div
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              className="mb-6 flex flex-wrap justify-center gap-2"
            >
              {chips.map(({ icon, label }) => (
                <span
                  key={label}
                  className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-gray-300"
                >
                  <span>{icon}</span>
                  {label}
                </span>
              ))}
            </motion.div>

            <motion.button
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              onClick={onClose}
              className="w-full rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-gray-950 shadow-lg shadow-black/30 transition-opacity hover:bg-gray-100 active:scale-[0.98]"
            >
              Start tracking
            </motion.button>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const {
    unreadCount,
    refresh: refreshContext,
    markSeen: contextMarkSeen,
    markAllSeen,
  } = useNotifications();

  // Paginated citation state — managed independently of the context so the
  // dashboard can page through large citation histories.
  const [citations, setCitations] = useState<Notification[]>([]);

  // Optimistically clear the dot on the local citations list, then let the
  // context handle the API call and badge decrement.
  const handleMarkSeen = useCallback((id: string) => {
    setCitations((prev) =>
      prev.map((n) => (n.id === id ? { ...n, seen: true } : n))
    );
    contextMarkSeen(id);
  }, [contextMarkSeen]);

  // Listen for the "mark all as read" event dispatched by the context so the
  // local citations state stays in sync without a full refetch.
  useEffect(() => {
    const handler = () =>
      setCitations((prev) => prev.map((n) => ({ ...n, seen: true })));
    window.addEventListener("citey:markAllRead", handler);
    return () => window.removeEventListener("citey:markAllRead", handler);
  }, []);
  const [citationPage, setCitationPage] = useState(1);
  const [citationPages, setCitationPages] = useState(1);
  const [citationTotal, setCitationTotal] = useState(0);
  const [notifsLoading, setNotifsLoading] = useState(true);
  const [notifsError, setNotifsError] = useState<string | null>(null);

  const loadNotifications = useCallback(async (page = citationPage) => {
    setNotifsLoading(true);
    setNotifsError(null);
    try {
      const data = await getNotifications(page, CITATIONS_PER_PAGE);
      setCitations(data.items);
      setCitationPage(data.page);
      setCitationPages(data.pages);
      setCitationTotal(data.total);
      // Keep the context unread badge in sync.
      refreshContext();
    } catch (err) {
      setNotifsError(err instanceof Error ? err.message : "Failed to load notifications.");
    } finally {
      setNotifsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [citationPage, refreshContext]);

  const [scholarUrl, setScholarUrl] = useState<string | null>(null);
  const [linkedAuthorId, setLinkedAuthorId] = useState<string | null>(null);
  const [linkedAuthorName, setLinkedAuthorName] = useState<string | null>(null);
  const [profileDisplayName, setProfileDisplayName] = useState<string | null>(null);

  const refreshProfile = useCallback(() => {
    import("@/lib/api").then(({ getProfile }) =>
      getProfile()
        .then((p) => {
          setScholarUrl(p.scholar_url ?? null);
          setLinkedAuthorId(p.linked_author_id ?? null);
          setLinkedAuthorName(p.linked_author_name ?? null);
          setProfileDisplayName(p.display_name ?? null);
        })
        .catch(() => {})
    );
  }, []);

  useEffect(() => {
    if (user) refreshProfile();
  }, [user, refreshProfile]);

  const [works, setWorks] = useState<TrackedWork[]>([]);
  const [worksLoading, setWorksLoading] = useState(true);
  const [worksError, setWorksError] = useState<string | null>(null);
  const [removingIds, setRemovingIds] = useState<Set<string>>(new Set());
  const [worksSort, setWorksSort] = useState<WorksSort>("year");
  const [worksPage, setWorksPage] = useState(1);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [exportingBibtex, setExportingBibtex] = useState(false);
  const [showFirstPaperModal, setShowFirstPaperModal] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++toastCounter;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/signup");
    }
  }, [user, authLoading, router]);

  const loadWorks = useCallback(async () => {
    setWorksLoading(true);
    setWorksError(null);
    try {
      const data = await getWorks();
      setWorks(data);
    } catch (err) {
      setWorksError(err instanceof Error ? err.message : "Failed to load works.");
    } finally {
      setWorksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadWorks();
      loadNotifications(1);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loadWorks]);

  const handleRemoveWork = async (workId: string) => {
    setRemovingIds((prev) => new Set(prev).add(workId));
    try {
      await deleteWork(workId);
      setWorks((prev) => {
        const next = prev.filter((w) => w.id !== workId);
        // If removing the last item on the current page, step back one page.
        const newPages = Math.max(1, Math.ceil(next.length / WORKS_PER_PAGE));
        setWorksPage((p) => Math.min(p, newPages));
        return next;
      });
      // Sync Recent Citations — backend cascade-deleted the notifications.
      loadNotifications();
      addToast("Work removed successfully.", "success");
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Failed to remove work.",
        "error"
      );
    } finally {
      setRemovingIds((prev) => {
        const next = new Set(prev);
        next.delete(workId);
        return next;
      });
    }
  };

  const handleExportBibtex = async () => {
    setExportingBibtex(true);
    try {
      await downloadBibtex();
    } catch {
      addToast("Failed to export citations. Please try again.", "error");
    } finally {
      setExportingBibtex(false);
    }
  };

  const handleRefreshCitations = useCallback(async () => {
    try {
      await pruneNotifications();
    } catch {
      // Ignore — the API's display filter still hides stale items even if
      // the prune request fails.
    }
    await loadNotifications(citationPage);
  }, [citationPage, loadNotifications]);

  const handlePageChange = async (newPage: number) => {
    setCitationPage(newPage);
    await loadNotifications(newPage);
  };

  // Best citation count per work: max of S2 and OpenAlex, fallback to local count.
  const bestCount = (w: TrackedWork) =>
    Math.max(w.s2_citation_count ?? 0, w.openalex_citation_count ?? 0) || w.citation_count;

  // Sort all works client-side, then slice to the current page.
  const sortedWorks = [...works].sort((a, b) => {
    if (worksSort === "citations") {
      return bestCount(b) - bestCount(a);
    }
    // Default: year descending, null last
    if (a.year == null && b.year == null) return 0;
    if (a.year == null) return 1;
    if (b.year == null) return -1;
    return b.year - a.year;
  });
  const worksPages = Math.max(1, Math.ceil(sortedWorks.length / WORKS_PER_PAGE));
  const worksPageClamped = Math.min(worksPage, worksPages);
  const pagedWorks = sortedWorks.slice(
    (worksPageClamped - 1) * WORKS_PER_PAGE,
    worksPageClamped * WORKS_PER_PAGE
  );

  // ── Lifetime citation metrics ────────────────────────────────────────────
  // Use the best available count per paper: max(S2, OpenAlex).
  // A paper contributes once it has at least one non-null source.
  const bestCounts = works
    .filter((w) => w.s2_citation_count !== null || w.openalex_citation_count !== null)
    .map((w) => Math.max(w.s2_citation_count ?? 0, w.openalex_citation_count ?? 0));
  const hasMetricsData = bestCounts.length > 0;
  const lifetimeCitations = bestCounts.reduce((a, b) => a + b, 0);

  if (authLoading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (!user) return null;

  return (
    <>
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      {showFirstPaperModal && (
        <FirstPaperInfoModal onClose={() => setShowFirstPaperModal(false)} />
      )}
      {!user.emailVerified && <VerificationBanner onToast={addToast} />}
      <ImportModal
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        linkedAuthorId={linkedAuthorId}
        linkedAuthorName={linkedAuthorName}
        onAdded={(work) => {
          const wasEmpty = works.length === 0;
          setWorks((prev) => [work, ...prev]);
          addToast(`"${work.title ?? work.doi}" added to tracking.`, "success");
          if (wasEmpty) setShowFirstPaperModal(true);
        }}
        onImported={(count) => {
          const wasEmpty = works.length === 0;
          loadWorks();
          refreshProfile();
          addToast(`Imported ${count} paper${count !== 1 ? "s" : ""} successfully.`, "success");
          if (wasEmpty && count > 0) setShowFirstPaperModal(true);
        }}
      />

      <Galaxy speedMultiplier={3} />
      <div className="relative z-10 mx-auto max-w-7xl overflow-x-hidden px-4 py-10 sm:px-6 lg:px-8">
        {/* Header */}
        <ScrollReveal className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">
              Welcome back
              {(profileDisplayName || user.displayName)
                ? `, ${profileDisplayName || user.displayName}`
                : ""}
            </h1>
            <p className="mt-1 text-sm text-gray-400">
              Here&apos;s your citation overview.
            </p>
          </div>

        </ScrollReveal>

        {/* Stats row */}
        <ScrollReveal className="mb-10 grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
          <TiltedCard>
            <div className="glass-card p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Tracked works</p>
              <p className="mt-1 text-3xl font-bold text-white">
                {worksLoading ? "." : <CountUp end={works.length} />}
              </p>
            </div>
          </TiltedCard>
          <TiltedCard>
            <a
              href={scholarUrl ?? "https://scholar.google.com"}
              target="_blank"
              rel="noopener noreferrer"
              className="glass-card group flex flex-col gap-2 p-4 transition-all duration-200 hover:border-white/20 hover:bg-white/5"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Google Scholar</p>
              <div className="flex items-center gap-1.5">
                <svg className="h-4 w-4 shrink-0 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
                <span className="text-sm font-semibold text-gray-300 group-hover:text-white transition-colors">
                  {scholarUrl ? "View your profile" : "Open Google Scholar"}
                </span>
              </div>
              <p className="text-[10px] text-gray-600">
                {scholarUrl ? "your linked profile" : "for accurate lifetime citation counts"}
              </p>
            </a>
          </TiltedCard>
          <TiltedCard>
            <div className="glass-card p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Unread</p>
              <p className="mt-1 text-3xl font-bold text-white">
                {notifsLoading ? "." : <CountUp end={unreadCount} />}
              </p>
              <p className="mt-0.5 text-[10px] text-gray-600">new citations</p>
            </div>
          </TiltedCard>
        </ScrollReveal>

        <div className="grid gap-10 lg:grid-cols-2">
          {/* ─── Tracked Works ─────────────────────────────────────── */}
          <section>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-y-2 gap-x-3">
              <div className="flex min-w-0 items-center gap-3">
                <h2 className="text-xl font-bold text-white">Tracked Works</h2>
                {/* Sort controls */}
                {works.length > 1 && (
                  <div className="flex rounded-lg border border-white/10 bg-gray-800 p-0.5">
                    {(["year", "citations"] as WorksSort[]).map((s) => (
                      <button
                        key={s}
                        onClick={() => { setWorksSort(s); setWorksPage(1); }}
                        className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                          worksSort === s
                            ? "bg-white text-gray-950 shadow"
                            : "text-gray-400 hover:text-white"
                        }`}
                      >
                        {s === "year" ? "Year" : "Cited By"}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => setAddModalOpen(true)}
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white px-3 sm:px-4 py-2 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                <span className="hidden sm:inline">Import Papers</span>
              </button>
            </div>

            {works.length > 0 && (
              <p className="mb-3 text-xs text-gray-500">
                {works.length} paper{works.length !== 1 ? "s" : ""}
                {worksPages > 1 && ` · page ${worksPageClamped} of ${worksPages}`}
              </p>
            )}

            {worksLoading ? (
              <div className="flex items-center justify-center py-16">
                <Spinner />
              </div>
            ) : worksError ? (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-400">
                {worksError}{" "}
                <button onClick={loadWorks} className="underline hover:no-underline">
                  Retry
                </button>
              </div>
            ) : works.length === 0 ? (
              <div className="glass-card flex flex-col items-center gap-3 py-16 text-center">
                <div className="text-4xl">📄</div>
                <p className="text-sm font-semibold text-gray-300">No tracked works yet</p>
                <p className="text-xs text-gray-500">
                  Click &quot;Import Papers&quot; to start tracking citations for your publications.
                </p>
                <button
                  onClick={() => setAddModalOpen(true)}
                  className="mt-2 rounded-lg bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/15 transition-colors"
                >
                  Import your papers
                </button>
                <a
                  href="/help"
                  className="mt-1 text-xs text-gray-500 underline decoration-dotted underline-offset-2 hover:text-gray-300 transition-colors"
                >
                  Need help? Read the guide
                </a>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-3">
                  {pagedWorks.map((work) => (
                    <TiltedCard key={work.id} tiltAmount={4}>
                      <TrackedWorkCard
                        work={work}
                        onRemove={handleRemoveWork}
                        removing={removingIds.has(work.id)}
                      />
                    </TiltedCard>
                  ))}
                </div>

                {/* Pagination controls */}
                {worksPages > 1 && (
                  <div className="mt-4 flex items-center justify-between gap-2">
                    <button
                      onClick={() => setWorksPage((p) => Math.max(1, p - 1))}
                      disabled={worksPageClamped <= 1}
                      className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                      </svg>
                      Prev
                    </button>

                    <span className="text-xs text-gray-500">
                      Page {worksPageClamped} of {worksPages}
                    </span>

                    <button
                      onClick={() => setWorksPage((p) => Math.min(worksPages, p + 1))}
                      disabled={worksPageClamped >= worksPages}
                      className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      Next
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  </div>
                )}
              </>
            )}
          </section>

          {/* ─── Citations ──────────────────────────────────────────── */}
          <section>
            <div className="mb-4 flex flex-wrap items-start justify-between gap-y-2">
              <div>
                <h2 className="text-xl font-bold text-white">
                  Citations
                  {unreadCount > 0 && (
                    <span className="ml-2 rounded-full bg-white px-2 py-0.5 text-xs font-bold text-gray-950">
                      {unreadCount}
                    </span>
                  )}
                </h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  {citationTotal > 0
                    ? `${citationTotal} total · page ${citationPage} of ${citationPages}`
                    : "No citations detected yet"}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {citationTotal > 0 && (
                  <button
                    onClick={handleExportBibtex}
                    disabled={exportingBibtex}
                    className="flex items-center gap-1 text-xs font-medium text-gray-500 transition-colors hover:text-gray-300 disabled:opacity-40"
                    title="Download all citations as BibTeX"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    {exportingBibtex ? "Exporting…" : ".bib"}
                  </button>
                )}
                {unreadCount > 0 && (
                  <button
                    onClick={markAllSeen}
                    className="text-xs font-medium text-gray-500 transition-colors hover:text-gray-300"
                  >
                    <span className="hidden sm:inline">Mark all as read</span>
                    <span className="sm:hidden">Mark read</span>
                  </button>
                )}
                <button
                  onClick={handleRefreshCitations}
                  disabled={notifsLoading}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors disabled:opacity-40"
                  aria-label="Refresh citations"
                >
                  <svg className={`h-4 w-4 ${notifsLoading ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
              </div>
            </div>

            {notifsLoading ? (
              <div className="flex items-center justify-center py-16">
                <Spinner />
              </div>
            ) : notifsError ? (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-400">
                {notifsError}{" "}
                <button onClick={() => loadNotifications(citationPage)} className="underline hover:no-underline">
                  Retry
                </button>
              </div>
            ) : citations.length === 0 ? (
              <div className="glass-card flex flex-col items-center gap-3 py-16 text-center">
                <div className="text-4xl">📑</div>
                <p className="text-sm font-semibold text-gray-300">No citations yet</p>
                <p className="text-xs text-gray-500 max-w-xs">
                  Citations are checked daily.<br />New ones will appear here automatically.
                </p>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-3">
                  {citations.map((notif) => (
                    <TiltedCard key={notif.id} tiltAmount={4}>
                      <RecentCitationCard
                        notification={notif}
                        onMarkSeen={handleMarkSeen}
                      />
                    </TiltedCard>
                  ))}
                </div>

                {/* Pagination controls */}
                {citationPages > 1 && (
                  <div className="mt-4 flex items-center justify-between gap-2">
                    <button
                      onClick={() => handlePageChange(citationPage - 1)}
                      disabled={citationPage <= 1 || notifsLoading}
                      className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                      </svg>
                      Prev
                    </button>

                    <span className="text-xs text-gray-500">
                      Page {citationPage} of {citationPages}
                    </span>

                    <button
                      onClick={() => handlePageChange(citationPage + 1)}
                      disabled={citationPage >= citationPages || notifsLoading}
                      className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      Next
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </div>

    </>
  );
}
