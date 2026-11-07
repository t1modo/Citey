"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, ReactNode } from "react";
import { ClerkProvider, useClerk, useUser } from "@clerk/nextjs";
import posthog from "posthog-js";

/**
 * The signed-in user as the site uses it. ``uid`` is their Clerk user ID,
 * the same ID the API and the database know them by.
 */
export interface AppUser {
  uid: string;
  email: string | null;
  emailVerified: boolean;
  displayName: string | null;
}

interface AuthContextValue {
  user: AppUser | null;
  loading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function identify(user: AppUser) {
  // Tie analytics to the account. Only when PostHog was initialised, i.e.
  // the token is configured.
  if (posthog.__loaded) {
    posthog.identify(user.uid, {
      email: user.email ?? undefined,
      email_verified: user.emailVerified,
    });
  }
}

function resetAnalytics() {
  // Start a fresh anonymous identity so the next person on this browser
  // isn't merged into the account that just signed out.
  if (posthog.__loaded) posthog.reset();
}

function ClerkAuthBridge({ children }: { children: ReactNode }) {
  const { isLoaded, user: clerkUser } = useUser();
  const clerk = useClerk();

  const user = useMemo<AppUser | null>(() => {
    if (!clerkUser) return null;
    const email = clerkUser.primaryEmailAddress;
    return {
      uid: clerkUser.id,
      email: email?.emailAddress ?? null,
      // Clerk verifies the address (by emailed code) before sign-up completes.
      emailVerified: email?.verification?.status === "verified",
      displayName: clerkUser.fullName || null,
    };
  }, [clerkUser]);

  useEffect(() => {
    if (user) identify(user);
  }, [user]);

  const signOut = useCallback(async () => {
    await clerk.signOut();
    resetAnalytics();
  }, [clerk]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading: !isLoaded, signOut }),
    [user, isLoaded, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider signInUrl="/signup" signUpUrl="/signup?mode=signup" afterSignOutUrl="/">
      <ClerkAuthBridge>{children}</ClerkAuthBridge>
    </ClerkProvider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
