"use client";

import { useEffect, useState, useCallback, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import {
  getProfile,
  updateProfile,
  getWorks,
  deleteWork,
  deleteAccount,
  unlinkAuthor,
} from "@/lib/api";
import type { UserProfile, TrackedWork } from "@/lib/types";

function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="surface p-6">
      <div className="mb-5">
        <h2 className="font-serif text-lg font-semibold text-ink">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-muted">{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const { user, loading: authLoading, signOut } = useAuth();
  const router = useRouter();

  // Profile state
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Form fields
  const [notifyEnabled, setNotifyEnabled] = useState(true);
  const [notifyNewPublications, setNotifyNewPublications] = useState(true);
  const [notificationEmail, setNotificationEmail] = useState("");
  // Result of clicking the confirmation link (?email=confirmed|invalid).
  const [emailLinkStatus, setEmailLinkStatus] = useState<string | null>(null);
  useEffect(() => {
    const status = new URLSearchParams(window.location.search).get("email");
    if (status) {
      setEmailLinkStatus(status);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  const [displayName, setDisplayName] = useState("");
  const [scholarUrl, setScholarUrl] = useState("");

  // Save state
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Scholar URL confirmation — shown when URL changes and a linked author exists
  const [scholarConfirmPending, setScholarConfirmPending] = useState(false);

  // Works state
  const [works, setWorks] = useState<TrackedWork[]>([]);
  const [worksLoading, setWorksLoading] = useState(true);
  const [worksError, setWorksError] = useState<string | null>(null);
  const [removingIds, setRemovingIds] = useState<Set<string>>(new Set());
  const [worksPage, setWorksPage] = useState(1);
  const WORKS_PER_PAGE = 10;

  // Change linked author state
  const [unlinkPending, setUnlinkPending] = useState(false);
  const [unlinkLoading, setUnlinkLoading] = useState(false);
  const [unlinkError, setUnlinkError] = useState<string | null>(null);

  // Account deletion state
  const [deleteAccountPending, setDeleteAccountPending] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [deleteAccountError, setDeleteAccountError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/signup");
    }
  }, [user, authLoading, router]);

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    setProfileError(null);
    try {
      const p = await getProfile();
      setProfile(p);
      setNotifyEnabled(p.notify_enabled);
      setNotifyNewPublications(p.notify_new_publications ?? true);
      setNotificationEmail(p.notification_email ?? "");
      setDisplayName(p.display_name ?? "");
      setScholarUrl(p.scholar_url ?? "");
    } catch (err) {
      setProfileError(
        err instanceof Error ? err.message : "Failed to load profile."
      );
    } finally {
      setProfileLoading(false);
    }
  }, []);

  const loadWorks = useCallback(async () => {
    setWorksLoading(true);
    setWorksError(null);
    try {
      const data = await getWorks();
      setWorks(data);
    } catch (err) {
      setWorksError(
        err instanceof Error ? err.message : "Failed to load works."
      );
    } finally {
      setWorksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadProfile();
      loadWorks();
    }
  }, [user, loadProfile, loadWorks]);

  const doSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError(null);
    setScholarConfirmPending(false);
    try {
      const updated = await updateProfile({
        notify_enabled: notifyEnabled,
        notify_new_publications: notifyNewPublications,
        // Empty string clears a custom address (null means "unchanged").
        notification_email: notificationEmail.trim(),
        display_name: displayName.trim() || null,
        scholar_url: scholarUrl.trim(),
      });
      setProfile(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3500);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Failed to save settings."
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSave = (e: FormEvent) => {
    e.preventDefault();

    const newUrl = scholarUrl.trim();
    const currentUrl = profile?.scholar_url ?? "";
    const urlChanged = newUrl !== currentUrl && newUrl !== "";
    const hasLinkedAuthor = !!profile?.linked_author_name;

    // If a new Scholar URL is being set and there's a linked author, ask first.
    if (urlChanged && hasLinkedAuthor && !scholarConfirmPending) {
      setScholarConfirmPending(true);
      return;
    }

    doSave();
  };

  const handleRemoveWork = async (workId: string) => {
    setRemovingIds((prev) => new Set(prev).add(workId));
    try {
      await deleteWork(workId);
      setWorks((prev) => prev.filter((w) => w.id !== workId));
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to remove work.");
    } finally {
      setRemovingIds((prev) => {
        const next = new Set(prev);
        next.delete(workId);
        return next;
      });
    }
  };

  const handleSignOut = async () => {
    await signOut();
    router.replace("/");
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirmText !== "DELETE") return;
    setDeletingAccount(true);
    setDeleteAccountError(null);
    try {
      await deleteAccount();
      await signOut();
      router.replace("/");
    } catch (err) {
      setDeleteAccountError(
        err instanceof Error ? err.message : "Failed to delete account. Please try again."
      );
      setDeletingAccount(false);
    }
  };

  if (authLoading || profileLoading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
        <Spinner className="h-6 w-6 text-muted" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-10 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl font-semibold text-ink">Settings</h1>
          <p className="mt-1 text-sm text-muted">
            Manage your notification preferences and tracked works.
          </p>
        </div>
        <a
          href="/help"
          className="shrink-0 rounded-lg border border-rule px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:border-ink/40 hover:text-ink"
        >
          Help guide
        </a>
      </div>

      <div className="flex flex-col gap-6">
        {/* ─── Notifications ───────────────────────────── */}
        <SectionCard
          title="Notifications"
          description="Control how and where Citey sends you citation alerts."
        >
          {profileError ? (
            <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
              {profileError}{" "}
              <button onClick={loadProfile} className="underline hover:no-underline">
                Retry
              </button>
            </div>
          ) : (
            <form onSubmit={handleSave} className="flex flex-col gap-5">
              {/* Enable toggle */}
              <div className="flex items-center justify-between rounded-lg border border-rule bg-sheet px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-ink">New citation alerts</p>
                  <p className="text-xs text-muted">
                    Receive an email each time a new citation is detected.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={notifyEnabled}
                  aria-label="New citation alerts"
                  onClick={() => setNotifyEnabled((v) => !v)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ink/20 focus:ring-offset-2 focus:ring-offset-paper ${
                    notifyEnabled ? "bg-ink" : "bg-control"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-sheet shadow transition-transform ${
                      notifyEnabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>

              {/* New publication alerts toggle */}
              <div className="flex items-center justify-between rounded-lg border border-rule bg-sheet px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-ink">New publication alerts</p>
                  <p className="text-xs text-muted">
                    Get notified when new papers from your author profile are auto-added.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={notifyNewPublications}
                  aria-label="New publication alerts"
                  onClick={() => setNotifyNewPublications((v) => !v)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ink/20 focus:ring-offset-2 focus:ring-offset-paper ${
                    notifyNewPublications ? "bg-ink" : "bg-control"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-sheet shadow transition-transform ${
                      notifyNewPublications ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>

              {/* Notification email */}
              <div>
                <label
                  htmlFor="notification-email"
                  className="mb-1.5 block text-sm font-medium text-ink"
                >
                  Notification email
                </label>
                <input
                  id="notification-email"
                  type="email"
                  value={notificationEmail}
                  onChange={(e) => setNotificationEmail(e.target.value)}
                  placeholder={profile?.email ?? "your@email.com"}
                  className="w-full rounded-lg border border-control bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                />
                <p className="mt-1.5 text-xs text-muted">
                  Leave blank to use your account email ({profile?.email}).
                </p>
                {profile?.notification_email_pending && (
                  <p className="mt-2 rounded-md border border-mark/40 bg-mark/60 px-3 py-2 text-xs text-amber-900" role="status">
                    We sent a confirmation link to {profile.notification_email}. Alerts go to {profile.email} until you confirm it.
                  </p>
                )}
                {emailLinkStatus === "confirmed" && (
                  <p className="mt-2 rounded-md border border-ok/40 bg-ok/10 px-3 py-2 text-xs text-ok" role="status">
                    Notification email confirmed.
                  </p>
                )}
                {emailLinkStatus === "invalid" && (
                  <p className="mt-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger" role="alert">
                    That confirmation link is invalid. Save your settings again to get a new link.
                  </p>
                )}
              </div>

              {/* Display name */}
              <div>
                <label
                  htmlFor="display-name"
                  className="mb-1.5 block text-sm font-medium text-ink"
                >
                  Display name
                </label>
                <input
                  id="display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Dr. Jane Smith"
                  className="w-full rounded-lg border border-control bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                />
              </div>

              {/* Google Scholar URL */}
              <div>
                <label
                  htmlFor="scholar-url"
                  className="mb-1.5 block text-sm font-medium text-ink"
                >
                  Google Scholar profile URL
                </label>
                <input
                  id="scholar-url"
                  type="url"
                  value={scholarUrl}
                  onChange={(e) => {
                    setScholarUrl(e.target.value);
                    setScholarConfirmPending(false);
                  }}
                  placeholder="https://scholar.google.com/citations?user=..."
                  className="w-full rounded-lg border border-control bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                />
                <p className="mt-1.5 text-xs text-muted">
                  Paste your Google Scholar profile URL to add a quick link on your dashboard.
                  Your citation count is never scraped. This is a link only.
                </p>
              </div>

              {/* Scholar URL / linked-author mismatch confirmation */}
              {scholarConfirmPending && (
                <div className="rounded-lg border border-mark/40 bg-mark/60 px-4 py-4 text-sm">
                  <p className="font-semibold text-amber-900">
                    Confirm Google Scholar profile
                  </p>
                  <p className="mt-1 text-amber-900">
                    Are you certain this Google Scholar URL matches your linked
                    account{" "}
                    <span className="font-semibold text-ink">
                      {profile?.linked_author_name}
                    </span>
                    ? The app uses{" "}
                    <span className="font-semibold text-ink">
                      {profile?.linked_author_name}
                    </span>{" "}
                    to track citations. The Scholar link is for your reference
                    only and won&apos;t be verified automatically.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={doSave}
                      className="rounded-lg bg-mark/60 px-4 py-1.5 text-xs font-semibold text-amber-900 transition-colors hover:bg-mark/60"
                    >
                      Yes, save it
                    </button>
                    <button
                      type="button"
                      onClick={() => setScholarConfirmPending(false)}
                      className="rounded-lg border border-rule px-4 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-ink/5"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {saveError && (
                <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
                  {saveError}
                </div>
              )}
              {saveSuccess && (
                <div className="rounded-lg border border-rule bg-ink/5 px-4 py-3 text-sm text-ink">
                  Settings saved successfully.
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 pt-1">
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-ink px-5 py-2.5 text-sm font-semibold text-paper shadow transition-opacity hover:bg-ink-soft disabled:opacity-50"
                >
                  {saving && <Spinner className="h-4 w-4" />}
                  {saving ? "Saving…" : "Save changes"}
                </button>
              </div>
            </form>
          )}
        </SectionCard>

        {/* ─── Tracked papers ───────────────────────────────────────── */}
        <SectionCard
          title="Tracked papers"
          description="Remove papers from your tracking list."
        >
          {worksLoading ? (
            <div className="flex items-center justify-center py-8">
              <Spinner className="h-5 w-5 text-muted" />
            </div>
          ) : worksError ? (
            <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
              {worksError}{" "}
              <button onClick={loadWorks} className="underline hover:no-underline">
                Retry
              </button>
            </div>
          ) : works.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">
              No tracked works. Add papers from the{" "}
              <a href="/dashboard" className="text-muted hover:underline">
                Dashboard
              </a>
              .
            </p>
          ) : (() => {
            const totalPages = Math.max(1, Math.ceil(works.length / WORKS_PER_PAGE));
            const page = Math.min(worksPage, totalPages);
            const pageWorks = works.slice((page - 1) * WORKS_PER_PAGE, page * WORKS_PER_PAGE);
            return (
              <div className="flex flex-col gap-3">
                <p className="text-xs text-muted">
                  {works.length} paper{works.length !== 1 ? "s" : ""}
                  {totalPages > 1 && `, page ${page} of ${totalPages}`}
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-rule text-left text-xs font-medium text-muted">
                        <th className="pb-3 pr-4">Title / DOI</th>
                        <th className="pb-3 pr-4">Year</th>
                        <th className="pb-3 pr-4">Last checked</th>
                        <th className="pb-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-rule">
                      {pageWorks.map((work) => (
                        <tr key={work.id} className="group">
                          <td className="py-3 pr-4">
                            <p className="font-medium text-ink leading-snug">
                              {work.title ?? "Untitled"}
                            </p>
                            <a
                              href={`https://doi.org/${work.doi}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="mt-0.5 block font-mono text-xs text-muted underline decoration-dotted underline-offset-2 hover:text-ink transition-colors"
                            >
                              {work.doi}
                            </a>
                          </td>
                          <td className="py-3 pr-4 text-muted">
                            {work.year ?? "–"}
                          </td>
                          <td className="py-3 pr-4 text-muted">
                            {work.last_checked_at
                              ? new Date(work.last_checked_at).toLocaleDateString()
                              : "–"}
                          </td>
                          <td className="py-3 text-right">
                            <button
                              onClick={() => handleRemoveWork(work.id)}
                              disabled={removingIds.has(work.id)}
                              className="rounded px-2.5 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-40"
                            >
                              {removingIds.has(work.id) ? "Removing…" : "Remove"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <button
                      onClick={() => setWorksPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                      className="flex items-center gap-1.5 rounded-lg border border-rule px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-ink/5 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                      </svg>
                      Prev
                    </button>
                    <span className="text-xs text-muted">Page {page} of {totalPages}</span>
                    <button
                      onClick={() => setWorksPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                      className="flex items-center gap-1.5 rounded-lg border border-rule px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-ink/5 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      Next
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            );
          })()}
        </SectionCard>

        {/* ─── Account ────────────────────────────────────────── */}
        <SectionCard
          title="Account"
          description="Sign out, change your linked author, or delete your account."
        >
          <div className="flex flex-col gap-4">
            {/* Change linked author */}
            {profile?.linked_author_id && (
              <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-ink">Change linked author</p>
                    <p className="text-xs text-muted">
                      Currently linked as{" "}
                      <span className="font-medium text-ink">{profile.linked_author_name}</span>
                      . Changing this will permanently delete all tracked papers.
                    </p>
                  </div>
                  {!unlinkPending && (
                    <button
                      onClick={() => { setUnlinkPending(true); setUnlinkError(null); }}
                      className="shrink-0 rounded-lg border border-danger/40 px-4 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/10 hover:border-danger/40"
                    >
                      Change
                    </button>
                  )}
                </div>
                {unlinkPending && (
                  <div className="mt-4 flex flex-col gap-3">
                    <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-xs text-danger">
                      <p className="font-semibold text-danger">This will permanently delete:</p>
                      <ul className="mt-1.5 list-disc pl-4 space-y-0.5 text-danger">
                        <li>All {works.length} tracked paper{works.length !== 1 ? "s" : ""} and their citation history</li>
                        <li>Your linked author profile ({profile.linked_author_name})</li>
                      </ul>
                      <p className="mt-2 font-medium text-danger">This cannot be undone.</p>
                      <p className="mt-1.5 text-danger">
                        After resetting, use <span className="font-medium text-danger">Add by arXiv</span> on the dashboard to link a new author profile.
                      </p>
                    </div>
                    {unlinkError && (
                      <p className="text-xs text-danger">{unlinkError}</p>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => { setUnlinkPending(false); setUnlinkError(null); }}
                        disabled={unlinkLoading}
                        className="flex-1 rounded-lg border border-rule py-2 text-sm font-medium text-ink transition-colors hover:bg-ink/5 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={async () => {
                          setUnlinkLoading(true);
                          setUnlinkError(null);
                          try {
                            await unlinkAuthor();
                            setUnlinkPending(false);
                            setWorks([]);
                            setProfile((p) => p ? { ...p, linked_author_id: null, linked_author_name: null } : p);
                          } catch (err) {
                            setUnlinkError(err instanceof Error ? err.message : "Failed to unlink author.");
                          } finally {
                            setUnlinkLoading(false);
                          }
                        }}
                        disabled={unlinkLoading}
                        className="flex-1 rounded-lg bg-danger/10 py-2 text-sm font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-50"
                      >
                        {unlinkLoading ? (
                          <span className="flex items-center justify-center gap-2">
                            <Spinner className="h-3.5 w-3.5" /> Resetting…
                          </span>
                        ) : (
                          "Yes, reset author"
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Sign out: not destructive, so not styled as a danger action */}
            <div className="flex items-center justify-between rounded-lg border border-rule bg-sheet px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-ink">Sign out</p>
                <p className="text-xs text-muted">
                  Sign out of your Citey account on this device.
                </p>
              </div>
              <button
                onClick={handleSignOut}
                className="rounded-lg border border-rule px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-ink/40"
              >
                Sign out
              </button>
            </div>

            {/* Delete account */}
            <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-ink">Delete account</p>
                  <p className="text-xs text-muted">
                    Permanently remove your account and all tracked papers.
                  </p>
                </div>
                {!deleteAccountPending && (
                  <button
                    onClick={() => {
                      setDeleteAccountPending(true);
                      setDeleteConfirmText("");
                      setDeleteAccountError(null);
                    }}
                    className="rounded-lg border border-danger/40 px-4 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/10 hover:border-danger/40"
                  >
                    Delete account
                  </button>
                )}
              </div>

              {deleteAccountPending && (
                <div className="mt-4 flex flex-col gap-3">
                  <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-xs text-danger">
                    <p className="mb-1.5 font-semibold text-danger">
                      This will permanently delete:
                    </p>
                    <ul className="list-disc pl-4 space-y-0.5 text-danger">
                      <li>All {works.length} tracked paper{works.length !== 1 ? "s" : ""} and their citation history</li>
                      <li>All notifications and alerts</li>
                      <li>Your profile, settings, and linked author</li>
                      <li>Your login — you will not be able to sign in again</li>
                    </ul>
                    <p className="mt-2 font-medium text-danger">
                      This action cannot be undone.
                    </p>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted">
                      Type <span className="font-mono font-bold text-danger">DELETE</span> to confirm
                    </label>
                    <input
                      type="text"
                      value={deleteConfirmText}
                      onChange={(e) => setDeleteConfirmText(e.target.value)}
                      placeholder="DELETE"
                      className="w-full rounded-lg border border-danger bg-sheet px-3 py-2 font-mono text-sm text-ink placeholder-muted outline-none focus:border-danger focus:ring-1 focus:ring-danger/40"
                    />
                  </div>

                  {deleteAccountError && (
                    <p className="text-xs text-danger">{deleteAccountError}</p>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={handleDeleteAccount}
                      disabled={deleteConfirmText !== "DELETE" || deletingAccount}
                      className="flex items-center gap-2 rounded-lg bg-danger/10 px-4 py-2 text-sm font-semibold text-ink transition-colors hover:bg-danger disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {deletingAccount && <Spinner className="h-3.5 w-3.5" />}
                      {deletingAccount ? "Deleting…" : "Delete my account"}
                    </button>
                    <button
                      onClick={() => {
                        setDeleteAccountPending(false);
                        setDeleteConfirmText("");
                        setDeleteAccountError(null);
                      }}
                      disabled={deletingAccount}
                      className="rounded-lg border border-rule px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-ink/5 disabled:opacity-40"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
