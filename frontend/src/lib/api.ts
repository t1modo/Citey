import { auth } from "@/lib/firebase";
import { track } from "@/lib/analytics";
import type {
  UserProfile,
  TrackedWork,
  Notification,
  PaginatedNotifications,
  UpdateProfileData,
  AddWorkResult,
  AuthorCandidate,
  PaperAuthorsResult,
} from "@/lib/types";

// Every backend route is under /api. On Vercel the site and API share a
// domain, so this is just "/api"; locally it is the API container's address.
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

// Render free-tier instances spin down after inactivity. The first request(s)
// after a cold start return a 502/503 while the service is booting. Retrying
// automatically means users never need to click "Look up" more than once.
const COLD_START_STATUSES = new Set([502, 503, 504]);
// A 502/503 from the host means the request never reached the app (it was
// still booting), so even a POST is safe to resend. A 504 or a dropped
// connection may mean the server already did the work, so those are only
// retried for idempotent methods.
const SAFE_TO_RESEND_STATUSES = new Set([502, 503]);
const IDEMPOTENT_METHODS = new Set(["GET", "HEAD", "PUT", "DELETE", "OPTIONS"]);
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(
  url: string,
  init: RequestInit = {}
): Promise<Response> {
  const idempotent = IDEMPOTENT_METHODS.has((init.method ?? "GET").toUpperCase());
  const retryable = idempotent ? COLD_START_STATUSES : SAFE_TO_RESEND_STATUSES;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const res = await fetch(url, init);
      if (retryable.has(res.status) && attempt < MAX_RETRIES) {
        await sleep(RETRY_DELAY_MS * (attempt + 1));
        continue;
      }
      return res;
    } catch (err) {
      if (idempotent && attempt < MAX_RETRIES) {
        await sleep(RETRY_DELAY_MS * (attempt + 1));
        continue;
      }
      throw err;
    }
  }
  // unreachable, but TypeScript needs a return path
  throw new Error("Request failed after retries.");
}

/**
 * Turn a FastAPI `detail` payload into a sentence a person can read.
 * Handles plain strings, our {message, retry_after_seconds} rate limit
 * objects, and Pydantic validation error lists.
 */
export function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    return first?.msg ? first.msg.replace(/^Value error, /, "") : fallback;
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: unknown; retry_after_seconds?: unknown };
    if (typeof d.message === "string") {
      const wait = Number(d.retry_after_seconds);
      if (Number.isFinite(wait) && wait > 0) {
        const mins = Math.ceil(wait / 60);
        return `${d.message} You can try again in ${wait < 60 ? `${Math.ceil(wait)} seconds` : `${mins} minute${mins === 1 ? "" : "s"}`}.`;
      }
      return d.message;
    }
  }
  return fallback;
}

async function authFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const currentUser = auth.currentUser;
  if (!currentUser) {
    throw new Error("Not authenticated");
  }

  const idToken = await currentUser.getIdToken();

  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${idToken}`);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetchWithRetry(`${BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = `Request failed: ${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data?.detail) {
        message = detailMessage(data.detail, message);
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(message);
  }

  return response;
}

export async function getProfile(): Promise<UserProfile> {
  const res = await authFetch("/profile");
  return res.json();
}

export async function updateProfile(
  data: UpdateProfileData
): Promise<UserProfile> {
  const res = await authFetch("/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function getWorks(): Promise<TrackedWork[]> {
  const res = await authFetch("/works");
  return res.json();
}

export async function addWork(doi: string): Promise<TrackedWork> {
  const res = await authFetch("/works", {
    method: "POST",
    body: JSON.stringify({ doi }),
  });
  return res.json();
}

/**
 * Adds a work by DOI with an author-presence check.
 * Returns { status: "added", work } on success or
 * { status: "author_not_found", ... } when the linked author isn't in the
 * paper's author list (the caller can re-invoke with force=true to bypass).
 */
export async function addWorkChecked(
  doi: string,
  force = false
): Promise<AddWorkResult> {
  const currentUser = auth.currentUser;
  if (!currentUser) throw new Error("Not authenticated");
  const idToken = await currentUser.getIdToken();

  const res = await fetchWithRetry(`${BASE_URL}/works`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${idToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ doi, force }),
  });

  if (res.ok) {
    track("paper_added", { method: "doi", author_check_skipped: force });
    return { status: "added", work: await res.json() };
  }

  let data: Record<string, unknown> = {};
  try {
    data = await res.json();
  } catch {
    // ignore
  }

  const detail = data?.detail as Record<string, unknown> | undefined;
  if (res.status === 422 && detail?.code === "author_not_found") {
    return {
      status: "author_not_found",
      linkedAuthor: String(detail.linked_author ?? ""),
      paperTitle: String(detail.paper_title ?? ""),
      paperAuthors: (detail.paper_authors as string[]) ?? [],
    };
  }

  const message =
    detail && typeof detail === "string"
      ? detail
      : detail?.code
      ? String(detail.code)
      : `Request failed: ${res.status}`;
  throw new Error(message);
}

export async function unlinkAuthor(): Promise<void> {
  await authFetch("/profile/linked-author", { method: "DELETE" });
  track("author_unlinked");
}

export async function deleteAccount(): Promise<void> {
  await authFetch("/profile", { method: "DELETE" });
  track("account_deleted");
}

export async function deleteWork(workId: string): Promise<void> {
  await authFetch(`/works/${workId}`, { method: "DELETE" });
  track("paper_removed");
}

export async function getNotifications(
  page = 1,
  limit = 20
): Promise<PaginatedNotifications> {
  const res = await authFetch(`/notifications?page=${page}&limit=${limit}`);
  return res.json();
}

export async function markSeen(notificationId: string): Promise<Notification> {
  const res = await authFetch(`/notifications/${notificationId}/seen`, {
    method: "POST",
  });
  return res.json();
}

export async function markAllSeen(): Promise<void> {
  await authFetch("/notifications/seen/all", { method: "POST" });
}

export async function pruneNotifications(): Promise<{ deleted: number }> {
  const res = await authFetch("/notifications/prune", { method: "POST" });
  return res.json();
}

export async function downloadBibtex(): Promise<void> {
  const res = await authFetch("/notifications/export.bib");
  const text = await res.text();
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "citey-citations.bib";
  track("citations_exported", { format: "bibtex" });
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function runJob(dryRun: boolean = false): Promise<{ message: string }> {
  const res = await authFetch("/jobs/run", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun }),
  });
  if (!dryRun) track("citation_check_requested");
  return res.json();
}

export async function sendVerificationEmail(): Promise<void> {
  await authFetch("/auth/send-verification", { method: "POST" });
}

export async function sendTestEmail(): Promise<{ message: string }> {
  const res = await authFetch("/jobs/email-test", { method: "POST" });
  track("test_email_requested");
  return res.json();
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function sendChatMessage(messages: ChatMessage[]): Promise<string> {
  const res = await authFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ messages }),
  });
  const data = await res.json();
  return data.message as string;
}

export async function getAuthorsByPaperDoi(doi: string): Promise<PaperAuthorsResult> {
  const res = await authFetch(`/works/paper-authors?doi=${encodeURIComponent(doi)}`);
  return res.json();
}

export async function searchAuthors(name: string): Promise<AuthorCandidate[]> {
  const res = await authFetch(`/works/author-search?query=${encodeURIComponent(name)}`);
  return res.json();
}

export type ImportByAuthorResult =
  | { status: "imported"; imported: number; skipped: number }
  | { status: "merge_required"; existing_author_name: string };

export async function importByAuthor(
  authorId: string,
  authorName?: string,
  source: "openalex" | "semantic_scholar" | "inspire" | "dblp" = "openalex",
  confirmMerge = false,
  extraSources: string[] = [],
): Promise<ImportByAuthorResult> {
  const currentUser = auth.currentUser;
  if (!currentUser) throw new Error("Not authenticated");
  const idToken = await currentUser.getIdToken();

  const res = await fetchWithRetry(`${BASE_URL}/works/import`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${idToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      author_id: authorId,
      author_name: authorName,
      source,
      confirm_merge: confirmMerge,
      extra_sources: extraSources,
    }),
  });

  let data: Record<string, unknown> = {};
  try { data = await res.json(); } catch { /* ignore */ }

  if (res.status === 409) {
    const detail = data?.detail as Record<string, unknown> | undefined;
    if (detail?.code === "merge_required") {
      return { status: "merge_required", existing_author_name: String(detail.existing_author_name ?? "") };
    }
    throw new Error(typeof detail === "string" ? detail : (detail?.code ? String(detail.code) : "Conflict error."));
  }

  if (!res.ok) {
    const detail = (data as Record<string, unknown>)?.detail;
    throw new Error(detailMessage(detail, "Import failed."));
  }

  const result = { status: "imported", ...data } as ImportByAuthorResult;
  if (result.status === "imported") {
    track("papers_imported", {
      source,
      imported: result.imported,
      skipped: result.skipped,
      extra_sources: extraSources,
      merged_profiles: confirmMerge,
    });
  }
  return result;
}

export async function unsubscribe(uid: string, token: string): Promise<{ message: string }> {
  const res = await fetch(`${BASE_URL}/profile/unsubscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid, token }),
  });

  let data: Record<string, unknown> = {};
  try { data = await res.json(); } catch { /* ignore */ }

  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : "Unsubscribe failed.");
  }
  track("unsubscribed");
  return data as { message: string };
}

// Re-export type for consumers
export type { AuthorCandidate };


export interface SupportMessageInput {
  name?: string;
  email: string;
  subject?: string;
  message: string;
  website?: string; // hidden trap field; people leave it empty
  elapsed_ms: number;
}

/** Send a contact form message. Works signed in or out; rate limited server side. */
export async function sendSupportMessage(input: SupportMessageInput): Promise<string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = await auth.currentUser?.getIdToken().catch(() => undefined);
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetchWithRetry(`${BASE_URL}/support`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  let data: Record<string, unknown> = {};
  try { data = await res.json(); } catch { /* ignore */ }
  if (!res.ok) {
    const detail = data?.detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      throw new Error(first?.msg?.replace(/^Value error, /, "") ?? "Please check the form and try again.");
    }
    throw new Error(typeof detail === "string" ? detail : "We couldn't send your message. Please try again.");
  }
  track("support_message_sent");
  return String(data.message ?? "Thanks. We'll reply to your email.");
}
