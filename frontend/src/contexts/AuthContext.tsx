"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from "react";
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  type User as FirebaseUser,
} from "firebase/auth";
import { ClerkProvider, useClerk, useUser } from "@clerk/nextjs";
import posthog from "posthog-js";
import { auth } from "@/lib/firebase";
import { CLERK_ENABLED } from "@/lib/auth-mode";

/**
 * The signed-in user as the site uses it, whichever sign-in system is on.
 * ``uid`` is the ID the API knows them by: the Firebase UID, which imported
 * Clerk users keep as their external ID, or the Clerk ID for new users.
 */
export interface AppUser {
  uid: string;
  email: string | null;
  emailVerified: boolean;
  displayName: string | null;
}

/** What email and password sign-in returns (Firebase only). */
export interface SignInResult {
  user: { emailVerified: boolean };
}

interface AuthContextValue {
  user: AppUser | null;
  loading: boolean;
  /** Which system is signing people in, so the sign-in page can show the right form. */
  provider: "clerk" | "firebase";
  signIn: (email: string, password: string) => Promise<SignInResult>;
  signUp: (email: string, password: string) => Promise<SignInResult>;
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

// ---------------------------------------------------------------------------
// Firebase Auth
// ---------------------------------------------------------------------------

function fromFirebase(user: FirebaseUser): AppUser {
  return {
    uid: user.uid,
    email: user.email,
    emailVerified: user.emailVerified,
    displayName: user.displayName,
  };
}

function FirebaseAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      const next = firebaseUser ? fromFirebase(firebaseUser) : null;
      setUser(next);
      setLoading(false);
      if (next) identify(next);
    });
    return unsubscribe;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      provider: "firebase",
      signIn: (email, password) => signInWithEmailAndPassword(auth, email, password),
      signUp: (email, password) => createUserWithEmailAndPassword(auth, email, password),
      signOut: async () => {
        await firebaseSignOut(auth);
        resetAnalytics();
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---------------------------------------------------------------------------
// Clerk
// ---------------------------------------------------------------------------

function ClerkAuthBridge({ children }: { children: ReactNode }) {
  const { isLoaded, user: clerkUser } = useUser();
  const clerk = useClerk();

  const user = useMemo<AppUser | null>(() => {
    if (!clerkUser) return null;
    const email = clerkUser.primaryEmailAddress;
    return {
      uid: clerkUser.externalId || clerkUser.id,
      email: email?.emailAddress ?? null,
      // Clerk verifies the address before an account can be used.
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
    () => ({
      user,
      loading: !isLoaded,
      provider: "clerk",
      // Clerk's own components on the sign-in page handle both.
      signIn: () => Promise.reject(new Error("Sign in with the Clerk form.")),
      signUp: () => Promise.reject(new Error("Sign up with the Clerk form.")),
      signOut,
    }),
    [user, isLoaded, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function ClerkAuthProvider({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider signInUrl="/signup" signUpUrl="/signup?mode=signup" afterSignOutUrl="/">
      <ClerkAuthBridge>{children}</ClerkAuthBridge>
    </ClerkProvider>
  );
}

// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  return CLERK_ENABLED ? (
    <ClerkAuthProvider>{children}</ClerkAuthProvider>
  ) : (
    <FirebaseAuthProvider>{children}</FirebaseAuthProvider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
