import posthog from "posthog-js";

// Product analytics, session replay and error tracking. Next.js runs this file
// once in the browser before the app becomes interactive.
//
// Requests go to /cyrelay on our own domain, which next.config.ts forwards to
// PostHog, so tracker blockers don't silently drop them. Without a token (local
// development, previews without the variable) nothing is initialised.
const token = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN;

if (token) {
  posthog.init(token, {
    api_host: "/cyrelay",
    ui_host: "https://us.posthog.com",
    defaults: "2026-08-30",
    capture_exceptions: true,
    // Replays never record what people type (passwords, emails, DOIs).
    session_recording: { maskAllInputs: true },
  });
}
