"use client";

export const dynamic = "force-dynamic";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { applyActionCode, verifyPasswordResetCode, confirmPasswordReset } from "firebase/auth";
import { auth } from "@/lib/firebase";
import Logo from "@/components/Logo";
import { FirebaseError } from "firebase/app";

type Stage =
  | "loading"
  | "verified"
  | "reset-form"
  | "reset-done"
  | "error";

function firebaseErrorMessage(err: unknown): string {
  if (err instanceof FirebaseError) {
    switch (err.code) {
      case "auth/expired-action-code":
        return "This link has expired. Please request a new one.";
      case "auth/invalid-action-code":
        return "This link is invalid or has already been used.";
      case "auth/user-disabled":
        return "This account has been disabled.";
      case "auth/user-not-found":
        return "No account found for this email.";
      case "auth/weak-password":
        return "Password must be at least 6 characters.";
      default:
        return err.message;
    }
  }
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred.";
}

function Spinner() {
  return (
    <svg className="h-5 w-5 animate-spin text-muted" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

function AuthActionContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const mode = searchParams.get("mode");
  const oobCode = searchParams.get("oobCode");
  const continueUrl = searchParams.get("continueUrl");

  const [stage, setStage] = useState<Stage>("loading");
  const [errorMessage, setErrorMessage] = useState("");

  // Password reset state
  const [resetEmail, setResetEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState("");

  useEffect(() => {
    if (!oobCode || !mode) {
      setErrorMessage("Missing or malformed link. Please request a new one.");
      setStage("error");
      return;
    }

    if (mode === "verifyEmail") {
      applyActionCode(auth, oobCode)
        .then(() => {
          // Reload the current user so emailVerified updates
          return auth.currentUser?.reload();
        })
        .then(() => setStage("verified"))
        .catch((err) => {
          setErrorMessage(firebaseErrorMessage(err));
          setStage("error");
        });
      return;
    }

    if (mode === "resetPassword") {
      verifyPasswordResetCode(auth, oobCode)
        .then((email) => {
          setResetEmail(email);
          setStage("reset-form");
        })
        .catch((err) => {
          setErrorMessage(firebaseErrorMessage(err));
          setStage("error");
        });
      return;
    }

    setErrorMessage("Unsupported action. Please try again.");
    setStage("error");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setResetError("");

    if (newPassword !== confirmPassword) {
      setResetError("Passwords do not match.");
      return;
    }
    if (newPassword.length < 6) {
      setResetError("Password must be at least 6 characters.");
      return;
    }

    setResetLoading(true);
    try {
      await confirmPasswordReset(auth, oobCode!, newPassword);
      setStage("reset-done");
    } catch (err) {
      setResetError(firebaseErrorMessage(err));
    } finally {
      setResetLoading(false);
    }
  };

  const destination = continueUrl ?? "/dashboard";

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-16">
      {/* Background glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
      </div>

      <div className="relative w-full max-w-md">
        <div className="rounded-2xl border border-rule bg-sheet p-8 shadow-2xl backdrop-blur-sm">
          {/* Logo */}
          <div className="mb-8 flex justify-center">
            <Link href="/" className="flex items-center gap-2">
              <Logo className="h-9 w-9" />
              <span
                className="text-xl font-bold text-ink"
                style={{ fontFamily: "var(--font-serif)", fontWeight: 400 }}
              >
                Citey
              </span>
            </Link>
          </div>

          {/* Loading */}
          {stage === "loading" && (
            <div className="flex flex-col items-center gap-4 py-4 text-center">
              <Spinner />
              <p className="text-sm text-muted">Verifying your link…</p>
            </div>
          )}

          {/* Email verified */}
          {stage === "verified" && (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-rule bg-ink/5 text-2xl">
                ✓
              </div>
              <div>
                <h1 className="font-serif text-2xl font-semibold text-ink">Email verified</h1>
                <p className="mt-2 text-sm text-muted">
                  Your email address has been confirmed. You can now receive citation alerts.
                </p>
              </div>
              <button
                onClick={() => router.push(destination)}
                className="mt-1 w-full rounded-xl bg-ink py-3 text-sm font-bold text-paper shadow-lg transition-all hover:bg-ink-soft"
              >
                Go to dashboard
              </button>
            </div>
          )}

          {/* Password reset form */}
          {stage === "reset-form" && (
            <div className="flex flex-col gap-5">
              <div className="text-center">
                <h1 className="font-serif text-2xl font-semibold text-ink">Set new password</h1>
                {resetEmail && (
                  <p className="mt-2 text-sm text-muted">
                    For{" "}
                    <span className="font-medium text-ink">{resetEmail}</span>
                  </p>
                )}
              </div>

              <form onSubmit={handlePasswordReset} className="flex flex-col gap-4" noValidate>
                <div>
                  <label
                    htmlFor="new-password"
                    className="mb-1.5 block text-sm font-medium text-ink"
                  >
                    New password
                  </label>
                  <input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={6}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full rounded-lg border border-control bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                    disabled={resetLoading}
                  />
                </div>

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
                    className="w-full rounded-lg border border-control bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20"
                    disabled={resetLoading}
                  />
                </div>

                {resetError && (
                  <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
                    {resetError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={resetLoading}
                  className="mt-1 rounded-xl bg-ink py-3 text-sm font-bold text-paper shadow-lg transition-all hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {resetLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <Spinner />
                      Saving…
                    </span>
                  ) : (
                    "Set password"
                  )}
                </button>
              </form>
            </div>
          )}

          {/* Password reset done */}
          {stage === "reset-done" && (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-rule bg-ink/5 text-2xl">
                ✓
              </div>
              <div>
                <h1 className="font-serif text-2xl font-semibold text-ink">Password updated</h1>
                <p className="mt-2 text-sm text-muted">
                  Your password has been changed. Sign in with your new password.
                </p>
              </div>
              <Link
                href="/signup"
                className="mt-1 w-full rounded-xl bg-ink py-3 text-center text-sm font-bold text-paper shadow-lg transition-all hover:bg-ink-soft"
              >
                Sign in
              </Link>
            </div>
          )}

          {/* Error */}
          {stage === "error" && (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-danger/40 bg-danger/10 text-2xl">
                ✕
              </div>
              <div>
                <h1 className="font-serif text-2xl font-semibold text-ink">Link invalid</h1>
                <p className="mt-2 text-sm text-muted">{errorMessage}</p>
              </div>
              <Link
                href="/signup"
                className="mt-1 w-full rounded-xl bg-ink py-3 text-center text-sm font-bold text-paper shadow-lg transition-all hover:bg-ink-soft"
              >
                Back to sign in
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AuthActionPage() {
  return (
    <Suspense>
      <AuthActionContent />
    </Suspense>
  );
}
