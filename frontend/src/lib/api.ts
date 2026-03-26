import { auth } from "@/lib/firebase";
import type {
  UserProfile,
  TrackedWork,
  Notification,
  PaginatedNotifications,
  UpdateProfileData,
  AuthorCandidate,
  PaperAuthorsResult,
  AddWorkResult,
  LinkedAuthorEntry,
} from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = `Request failed: ${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data?.detail) {
        message = typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
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

  const res = await fetch(`${BASE_URL}/works`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${idToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ doi, force }),
  });

  if (res.ok) {
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
}

export async function deleteAccount(): Promise<void> {
  await authFetch("/profile", { method: "DELETE" });
}

export async function deleteWork(workId: string): Promise<void> {
  await authFetch(`/works/${workId}`, { method: "DELETE" });
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

export async function runJob(dryRun: boolean = false): Promise<{ message: string }> {
  const res = await authFetch("/jobs/run", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun }),
  });
  return res.json();
}

export async function sendVerificationEmail(): Promise<void> {
  await authFetch("/auth/send-verification", { method: "POST" });
}

export async function sendTestEmail(): Promise<{ message: string }> {
  const res = await authFetch("/jobs/email-test", { method: "POST" });
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
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Paper not found.");
  }
  return res.json();
}

export async function searchAuthors(query: string): Promise<AuthorCandidate[]> {
  const res = await authFetch(`/works/author-search?query=${encodeURIComponent(query)}`);
  return res.json();
}

export type ImportByAuthorResult =
  | { status: "imported"; imported: number; skipped: number }
  | { status: "merge_required"; existing_author_name: string };

export async function importByAuthor(
  authorId: string,
  authorName?: string,
  source: "openalex" | "semantic_scholar" = "openalex",
  confirmMerge = false
): Promise<ImportByAuthorResult> {
  const currentUser = auth.currentUser;
  if (!currentUser) throw new Error("Not authenticated");
  const idToken = await currentUser.getIdToken();

  const res = await fetch(`${BASE_URL}/works/import`, {
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
    }),
  });

  let data: Record<string, unknown> = {};
  try {
    data = await res.json();
  } catch {
    // ignore
  }

  if (res.status === 409) {
    const detail = data?.detail as Record<string, unknown> | undefined;
    if (detail?.code === "merge_required") {
      return { status: "merge_required", existing_author_name: String(detail.existing_author_name ?? "") };
    }
    throw new Error(typeof detail === "string" ? detail : (detail?.code ? String(detail.code) : "Conflict error."));
  }

  if (!res.ok) {
    const detail = (data as Record<string, unknown>)?.detail;
    throw new Error(typeof detail === "string" ? detail : "Import failed.");
  }

  return { status: "imported", ...data } as ImportByAuthorResult;
}
