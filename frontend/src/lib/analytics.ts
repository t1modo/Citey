import posthog from "posthog-js";

/**
 * Product events. Names are snake_case, past tense, one per user action, so
 * they read naturally in PostHog ("papers_imported where source = dblp").
 * A no-op when PostHog isn't initialised (no token configured).
 */
export type AnalyticsEvent =
  | "signed_up"
  | "paper_added"
  | "papers_imported"
  | "paper_removed"
  | "citations_exported"
  | "citation_check_requested"
  | "test_email_requested"
  | "author_unlinked"
  | "account_deleted"
  | "unsubscribed";

export function track(event: AnalyticsEvent, properties?: Record<string, unknown>): void {
  if (typeof window === "undefined" || !posthog.__loaded) return;
  posthog.capture(event, properties);
}
