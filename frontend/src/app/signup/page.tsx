"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import Logo from "@/components/Logo";
import { sendVerificationEmail } from "@/lib/api";
import { FirebaseError } from "firebase/app";
import { auth } from "@/lib/firebase";

function firebaseErrorMessage(err: unknown): string {
  if (err instanceof FirebaseError) {
    switch (err.code) {
      case "auth/invalid-email":
        return "Invalid email address.";
      case "auth/user-not-found":
      case "auth/wrong-password":
      case "auth/invalid-credential":
        return "Incorrect email or password.";
      case "auth/email-already-in-use":
        return "An account with this email already exists. Try signing in.";
      case "auth/weak-password":
        return "Password must be at least 6 characters.";
      case "auth/too-many-requests":
        return "Too many failed attempts. Please try again later.";
      case "auth/network-request-failed":
        return "Network error. Check your connection and try again.";
      default:
        return err.message;
    }
  }
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred.";
}

export default function SignUpPage() {
  const { signIn, signUp, user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifyScreen, setVerifyScreen] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendSent, setResendSent] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);

  // Redirect verified users away from this page; surface verify screen for unverified ones.
  useEffect(() => {
    if (authLoading) return;
    if (!user) return;
    if (user.emailVerified) {
      router.replace("/dashboard");
    } else {
      // Returning unverified user — show the verify screen with their email pre-filled.
      setEmail(user.email ?? "");
      setVerifyScreen(true);
    }
  }, [user, authLoading, router]);

  // Poll Firebase every 3 s while on the verify screen.
  // As soon as emailVerified flips to true, redirect to the dashboard.
  useEffect(() => {
    if (!verifyScreen) return;

    const interval = setInterval(async () => {
      const currentUser = auth.currentUser;
      if (!currentUser) return;
      await currentUser.reload();
      if (currentUser.emailVerified) {
        clearInterval(interval);
        router.push("/dashboard");
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [verifyScreen, router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (mode === "signup" && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      if (mode === "signup") {
        await signUp(email, password);
        // Account created — attempt verification email but don't block progress on failure
        try {
          await sendVerificationEmail();
        } catch {
          // ignore — user can resend from the verify screen
        }
        setVerifyScreen(true);
      } else {
        const credential = await signIn(email, password);
        if (!credential.user.emailVerified) {
          // Account exists but email not yet confirmed — show the verify screen.
          setVerifyScreen(true);
        } else {
          router.push("/dashboard");
        }
      }
    } catch (err) {
      setError(firebaseErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResendLoading(true);
    setResendError(null);
    try {
      await sendVerificationEmail();
      setResendSent(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("already verified")) {
        setResendError("Your email is already verified. Try signing in.");
      } else {
        setResendError("Failed to send — please try again in a moment.");
      }
    } finally {
      setResendLoading(false);
    }
  };

  const toggle = () => {
    setMode((m) => (m === "signin" ? "signup" : "signin"));
    setError(null);
    setPassword("");
    setConfirmPassword("");
  };

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-16">
      {/* Background glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
      </div>

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="rounded-2xl border border-rule bg-sheet p-8 shadow-2xl backdrop-blur-sm">
          {/* Logo */}
          <div className="mb-8 flex justify-center">
            <Link href="/" className="flex items-center gap-2">
              <Logo className="h-9 w-9" />
              <span className="text-xl font-bold text-ink" style={{ fontFamily: "var(--font-serif)", fontWeight: 400 }}>
                Citey
              </span>
            </Link>
          </div>

          {verifyScreen ? (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-rule bg-ink/5 text-2xl">
                ✉
              </div>
              <div>
                <h1 className="font-serif text-2xl font-semibold text-ink">Check your inbox</h1>
                <p className="mt-2 text-sm text-muted">
                  We sent a verification link to{" "}
                  <span className="font-medium text-ink">{email}</span>.
                  Click the link to activate your account.
                </p>
              </div>
              {resendSent ? (
                <p className="text-sm text-muted">Verification email resent.</p>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <button
                    onClick={handleResend}
                    disabled={resendLoading}
                    className="text-sm font-medium text-ink underline decoration-dotted underline-offset-2 hover:text-ink disabled:opacity-50 transition-colors"
                  >
                    {resendLoading ? "Sending…" : "Resend verification email"}
                  </button>
                  {resendError && (
                    <p className="text-xs text-danger">{resendError}</p>
                  )}
                </div>
              )}
              <Link
                href="/dashboard"
                className="mt-1 w-full rounded-xl bg-ink py-3 text-center text-sm font-bold text-paper shadow-lg transition-all hover:bg-ink-soft"
              >
                Continue to dashboard
              </Link>
            </div>
          ) : (
            <>
          <h1 className="font-serif mb-2 text-center text-2xl font-semibold text-ink">
            {mode === "signin" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="mb-8 text-center text-sm text-muted">
            {mode === "signin"
              ? "Sign in to access your citation dashboard."
              : "Start tracking citations to your research, free forever."}
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-ink"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@institution.edu"
                className="w-full rounded-lg border border-rule bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted/70 outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                disabled={loading}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-ink"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-rule bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted/70 outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                disabled={loading}
              />
            </div>

            {mode === "signup" && (
              <div>
                <label
                  htmlFor="confirm-password"
                  className="mb-1.5 block text-sm font-medium text-ink"
                >
                  Confirm password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-lg border border-rule bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted/70 outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                  disabled={loading}
                />
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-1 rounded-xl bg-ink py-3 text-sm font-bold text-paper shadow-lg transition-all hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                  </svg>
                  {mode === "signin" ? "Signing in…" : "Creating account…"}
                </span>
              ) : mode === "signin" ? (
                "Sign in"
              ) : (
                "Create account"
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-muted">
            {mode === "signin" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  onClick={toggle}
                  className="font-semibold text-ink hover:text-ink transition-colors"
                >
                  Sign up free
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={toggle}
                  className="font-semibold text-ink hover:text-ink transition-colors"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-muted">
          By using Citey you agree to our terms of service and privacy policy.
          Citation data sourced from{" "}
          <a href="https://openalex.org" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">OpenAlex</a>
          ,{" "}
          <a href="https://www.crossref.org" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">Crossref</a>
          ,{" "}
          <a href="https://www.semanticscholar.org" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">Semantic Scholar</a>
          ,{" "}
          <a href="https://pubmed.ncbi.nlm.nih.gov" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">PubMed</a>
          ,{" "}
          <a href="https://ui.adsabs.harvard.edu" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">NASA ADS</a>
          ,{" "}
          <a href="https://inspirehep.net" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">INSPIRE-HEP</a>
          , and{" "}
          <a href="https://dblp.org" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-muted">DBLP</a>
          .
        </p>
      </div>
    </div>
  );
}
