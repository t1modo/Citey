interface ClerkGlobal {
  session?: { getToken: () => Promise<string | null> } | null;
}

/**
 * The signed-in user's Clerk session token for API calls, or null when
 * signed out. Clerk's browser SDK keeps it fresh (tokens last 60 s).
 */
export async function getSessionToken(): Promise<string | null> {
  const clerk = (globalThis as { Clerk?: ClerkGlobal }).Clerk;
  return (await clerk?.session?.getToken()) ?? null;
}
