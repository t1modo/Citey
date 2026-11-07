import { clerkMiddleware } from "@clerk/nextjs/server";

// Clerk's middleware keeps the session cookie in step on page requests.
export default clerkMiddleware();

export const config = {
  // Vercel Services can't deploy Edge Functions, which is where Next.js puts
  // middleware by default.
  runtime: "nodejs",
  // Pages only: not Next.js internals, static files, the PostHog relay, or
  // /api (served by the FastAPI backend, which checks tokens itself).
  matcher: [
    "/((?!_next|api|cyrelay|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|wgsl)).*)",
  ],
};
