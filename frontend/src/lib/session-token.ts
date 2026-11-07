import { auth } from "@/lib/firebase";
import { CLERK_ENABLED } from "@/lib/auth-mode";

interface ClerkGlobal {
  session?: { getToken: () => Promise<string | null> } | null;
}

/**
 * The signed-in user's token for API calls, or null when signed out. A
 * Clerk session token under Clerk, a Firebase ID token otherwise; the API
 * accepts both.
 */
export async function getSessionToken(): Promise<string | null> {
  if (CLERK_ENABLED) {
    const clerk = (globalThis as { Clerk?: ClerkGlobal }).Clerk;
    return (await clerk?.session?.getToken()) ?? null;
  }
  const user = auth.currentUser;
  return user ? await user.getIdToken() : null;
}
