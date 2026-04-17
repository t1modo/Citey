"use client";

export const dynamic = "force-dynamic";

import { useEffect, useState } from "react";
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
    <svg className="h-5 w-5 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}

export default function AuthActionPage() {
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
        <div className="absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute top-1/3 right-1/4 h-64 w-64 rounded-full bg-white/3 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        <div className="rounded-2xl border border-white/10 bg-gray-900/80 p-8 shadow-2xl backdrop-blur-sm">
          {/* Logo */}
          <div className="mb-8 flex justify-center">
            <Link href="/" className="flex items-center gap-2">
              <Logo className="h-9 w-9" />
              <span
                className="text-xl font-bold text-white"
                style={{ fontFamily: "var(--font-syne)" }}
              >
                Citey
              </span>
            </Link>
          </div>

          {/* Loading */}
          {stage === "loading" && (
            <div className="flex flex-col items-center gap-4 py-4 text-center">
              <Spinner />
              <p className="text-sm text-gray-400">Verifying your link…</p>
            </div>
          )}

          {/* Email verified */}
          {stage === "verified" && (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-white/5 text-2xl">
                ✓
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Email verified</h1>
                <p className="mt-2 text-sm text-gray-400">
                  Your email address has been confirmed. You can now receive citation alerts.
                </p>
              </div>
              <button
                onClick={() => router.push(destination)}
                className="mt-1 w-full rounded-xl bg-white py-3 text-sm font-bold text-gray-950 shadow-lg transition-all hover:bg-gray-100"
              >
                Go to dashboard
              </button>
            </div>
          )}

          {/* Password reset form */}
          {stage === "reset-form" && (
            <div className="flex flex-col gap-5">
              <div className="text-center">
                <h1 className="text-2xl font-bold text-white">Set new password</h1>
                {resetEmail && (
                  <p className="mt-2 text-sm text-gray-400">
                    For{" "}
                    <span className="font-medium text-gray-200">{resetEmail}</span>
                  </p>
                )}
              </div>

              <form onSubmit={handlePasswordReset} className="flex flex-col gap-4" noValidate>
                <div>
                  <label
                    htmlFor="new-password"
                    className="mb-1.5 block text-sm font-medium text-gray-300"
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
                    className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                    disabled={resetLoading}
                  />
                </div>

                <div>
                  <label
                    htmlFor="confirm-password"
                    className="mb-1.5 block text-sm font-medium text-gray-300"
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
                    className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                    disabled={resetLoading}
                  />
                </div>

                {resetError && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                    {resetError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={resetLoading}
                  className="mt-1 rounded-xl bg-white py-3 text-sm font-bold text-gray-950 shadow-lg transition-all hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {resetLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <Spinner />
                      Saving…
                    </span>
                  ) : (
                    "Set Password"
                  )}
                </button>
              </form>
            </div>
          )}

          {/* Password reset done */}
          {stage === "reset-done" && (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-white/5 text-2xl">
                ✓
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Password updated</h1>
                <p className="mt-2 text-sm text-gray-400">
                  Your password has been changed. Sign in with your new password.
                </p>
              </div>
              <Link
                href="/signup"
                className="mt-1 w-full rounded-xl bg-white py-3 text-center text-sm font-bold text-gray-950 shadow-lg transition-all hover:bg-gray-100"
              >
                Sign in
              </Link>
            </div>
          )}

          {/* Error */}
          {stage === "error" && (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-red-500/30 bg-red-500/10 text-2xl">
                ✕
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Link invalid</h1>
                <p className="mt-2 text-sm text-gray-400">{errorMessage}</p>
              </div>
              <Link
                href="/signup"
                className="mt-1 w-full rounded-xl bg-white py-3 text-center text-sm font-bold text-gray-950 shadow-lg transition-all hover:bg-gray-100"
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
