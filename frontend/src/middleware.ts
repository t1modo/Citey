import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Clerk's middleware only when this build signs people in with Clerk (see
// lib/auth-mode). Firebase builds pass every request straight through.
const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default clerkEnabled ? clerkMiddleware() : () => NextResponse.next();

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
