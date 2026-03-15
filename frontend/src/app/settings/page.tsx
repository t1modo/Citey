"use client";

import { useEffect, useState, useCallback, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import {
  getProfile,
  updateProfile,
  getWorks,
  deleteWork,
  sendTestEmail,
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
    <div className="glass-card p-6">
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-gray-400">{description}</p>
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
  const [notificationEmail, setNotificationEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [scholarUrl, setScholarUrl] = useState("");

  // Save state
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Scholar URL confirmation — shown when URL changes and a linked author exists
  const [scholarConfirmPending, setScholarConfirmPending] = useState(false);

  // Test email state
  const [testEmailSending, setTestEmailSending] = useState(false);
  const [testEmailResult, setTestEmailResult] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Works state
  const [works, setWorks] = useState<TrackedWork[]>([]);
  const [worksLoading, setWorksLoading] = useState(true);
  const [worksError, setWorksError] = useState<string | null>(null);
  const [removingIds, setRemovingIds] = useState<Set<string>>(new Set());

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
        notification_email: notificationEmail.trim() || null,
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

  const handleTestEmail = async () => {
    setTestEmailSending(true);
    setTestEmailResult(null);
    try {
      const result = await sendTestEmail();
      setTestEmailResult({ type: "success", message: result.message ?? "Test email sent!" });
    } catch (err) {
      setTestEmailResult({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to send test email.",
      });
    } finally {
      setTestEmailSending(false);
    }
  };

  const handleRemoveWork = async (workId: string) => {
    setRemovingIds((prev) => new Set(prev).add(workId));
    try {
      await deleteWork(workId);
      setWorks((prev) => prev.filter((w) => w.id !== workId));
    } catch {
      // ignore — could add toast here
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

  if (authLoading || profileLoading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
        <Spinner className="h-6 w-6 text-gray-400" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white">Settings</h1>
        <p className="mt-1 text-sm text-gray-400">
          Manage your notification preferences and tracked works.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        {/* ─── Notification Preferences ───────────────────────────── */}
        <SectionCard
          title="Notification Preferences"
          description="Control how and where Citey sends you citation alerts."
        >
          {profileError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {profileError}{" "}
              <button onClick={loadProfile} className="underline hover:no-underline">
                Retry
              </button>
            </div>
          ) : (
            <form onSubmit={handleSave} className="flex flex-col gap-5">
              {/* Enable toggle */}
              <div className="flex items-center justify-between rounded-lg border border-white/10 bg-gray-800/50 px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-white">Email notifications</p>
                  <p className="text-xs text-gray-400">
                    Receive an email each time a new citation is detected.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={notifyEnabled}
                  onClick={() => setNotifyEnabled((v) => !v)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-white/30 focus:ring-offset-2 focus:ring-offset-gray-900 ${
                    notifyEnabled ? "bg-gray-300" : "bg-gray-700"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      notifyEnabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>

              {/* Notification email */}
              <div>
                <label
                  htmlFor="notification-email"
                  className="mb-1.5 block text-sm font-medium text-gray-300"
                >
                  Notification email
                </label>
                <input
                  id="notification-email"
                  type="email"
                  value={notificationEmail}
                  onChange={(e) => setNotificationEmail(e.target.value)}
                  placeholder={profile?.email ?? "your@email.com"}
                  className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                />
                <p className="mt-1.5 text-xs text-gray-500">
                  Leave blank to use your account email ({profile?.email}).
                </p>
              </div>

              {/* Display name */}
              <div>
                <label
                  htmlFor="display-name"
                  className="mb-1.5 block text-sm font-medium text-gray-300"
                >
                  Display name
                </label>
                <input
                  id="display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Dr. Jane Smith"
                  className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                />
              </div>

              {/* Google Scholar URL */}
              <div>
                <label
                  htmlFor="scholar-url"
                  className="mb-1.5 block text-sm font-medium text-gray-300"
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
                  className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                />
                <p className="mt-1.5 text-xs text-gray-500">
                  Paste your Google Scholar profile URL to add a quick link on your dashboard.
                  Your citation count is never scraped. This is a link only.
                </p>
              </div>

              {/* Scholar URL / linked-author mismatch confirmation */}
              {scholarConfirmPending && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-4 text-sm">
                  <p className="font-semibold text-amber-300">
                    Confirm Google Scholar profile
                  </p>
                  <p className="mt-1 text-amber-200/80">
                    Are you certain this Google Scholar URL matches your linked
                    account{" "}
                    <span className="font-semibold text-white">
                      {profile?.linked_author_name}
                    </span>
                    ? The app uses{" "}
                    <span className="font-semibold text-white">
                      {profile?.linked_author_name}
                    </span>{" "}
                    to track citations. The Scholar link is for your reference
                    only and won&apos;t be verified automatically.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={doSave}
                      className="rounded-lg bg-amber-500/20 px-4 py-1.5 text-xs font-semibold text-amber-300 transition-colors hover:bg-amber-500/30"
                    >
                      Yes, save it
                    </button>
                    <button
                      type="button"
                      onClick={() => setScholarConfirmPending(false)}
                      className="rounded-lg border border-white/10 px-4 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:bg-white/5"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {saveError && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                  {saveError}
                </div>
              )}
              {saveSuccess && (
                <div className="rounded-lg border border-white/20 bg-white/5 px-4 py-3 text-sm text-gray-300">
                  Settings saved successfully.
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 pt-1">
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-gray-950 shadow transition-opacity hover:bg-gray-100 disabled:opacity-50"
                >
                  {saving && <Spinner className="h-4 w-4" />}
                  {saving ? "Saving…" : "Save Changes"}
                </button>

                <button
                  type="button"
                  onClick={handleTestEmail}
                  disabled={testEmailSending}
                  className="flex items-center gap-2 rounded-lg border border-white/10 px-5 py-2.5 text-sm font-medium text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                >
                  {testEmailSending && <Spinner className="h-4 w-4 text-current" />}
                  {testEmailSending ? "Sending…" : "Send Test Email"}
                </button>
              </div>

              {testEmailResult && (
                <div
                  className={`rounded-lg border px-4 py-3 text-sm ${
                    testEmailResult.type === "success"
                      ? "border-white/20 bg-white/5 text-gray-300"
                      : "border-red-500/30 bg-red-500/10 text-red-400"
                  }`}
                >
                  {testEmailResult.message}
                </div>
              )}
            </form>
          )}
        </SectionCard>

        {/* ─── Tracked Works ───────────────────────────────────────── */}
        <SectionCard
          title="Tracked Works"
          description="Remove papers from your tracking list."
        >
          {worksLoading ? (
            <div className="flex items-center justify-center py-8">
              <Spinner className="h-5 w-5 text-gray-400" />
            </div>
          ) : worksError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {worksError}{" "}
              <button onClick={loadWorks} className="underline hover:no-underline">
                Retry
              </button>
            </div>
          ) : works.length === 0 ? (
            <p className="py-6 text-center text-sm text-gray-500">
              No tracked works. Add papers from the{" "}
              <a href="/dashboard" className="text-gray-400 hover:underline">
                Dashboard
              </a>
              .
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                    <th className="pb-3 pr-4">Title / DOI</th>
                    <th className="pb-3 pr-4">Year</th>
                    <th className="pb-3 pr-4">Last checked</th>
                    <th className="pb-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {works.map((work) => (
                    <tr key={work.id} className="group">
                      <td className="py-3 pr-4">
                        <p className="font-medium text-white leading-snug">
                          {work.title ?? "Untitled"}
                        </p>
                        <a
                          href={`https://doi.org/${work.doi}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-0.5 block font-mono text-xs text-gray-400 underline decoration-dotted underline-offset-2 hover:text-gray-300 transition-colors"
                        >
                          {work.doi}
                        </a>
                      </td>
                      <td className="py-3 pr-4 text-gray-400">
                        {work.year ?? "."}
                      </td>
                      <td className="py-3 pr-4 text-gray-400">
                        {work.last_checked_at
                          ? new Date(work.last_checked_at).toLocaleDateString()
                          : "."}
                      </td>
                      <td className="py-3 text-right">
                        <button
                          onClick={() => handleRemoveWork(work.id)}
                          disabled={removingIds.has(work.id)}
                          className="rounded px-2.5 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-40"
                        >
                          {removingIds.has(work.id) ? "Removing…" : "Remove"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        {/* ─── Danger Zone ────────────────────────────────────────── */}
        <SectionCard
          title="Danger Zone"
          description="Irreversible actions for your account."
        >
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-white">Sign out</p>
                <p className="text-xs text-gray-400">
                  Sign out of your Citey account on this device.
                </p>
              </div>
              <button
                onClick={handleSignOut}
                className="rounded-lg border border-red-500/30 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/10 hover:border-red-500/50"
              >
                Sign Out
              </button>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
