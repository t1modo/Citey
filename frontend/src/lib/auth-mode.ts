/**
 * Which sign-in system this build uses. Clerk when its publishable key is
 * set (Vercel previews during the move to Clerk), Firebase Auth otherwise
 * (production until the switch). Read at build time: Next.js inlines
 * NEXT_PUBLIC_ variables, so it must be referenced literally.
 */
export const CLERK_ENABLED = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
