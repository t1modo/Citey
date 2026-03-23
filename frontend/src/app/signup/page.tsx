"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { sendEmailVerification } from "firebase/auth";
import { FirebaseError } from "firebase/app";

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
  const { signIn, signUp, user } = useAuth();
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
        setVerifyScreen(true);
      } else {
        await signIn(email, password);
        router.push("/dashboard");
      }
    } catch (err) {
      setError(firebaseErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!user) return;
    setResendLoading(true);
    try {
      await sendEmailVerification(user);
      setResendSent(true);
    } catch {
      // ignore — Firebase rate-limits resends automatically
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
        <div className="absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute top-1/3 right-1/4 h-64 w-64 rounded-full bg-white/3 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="rounded-2xl border border-white/10 bg-gray-900/80 p-8 shadow-2xl backdrop-blur-sm">
          {/* Logo */}
          <div className="mb-8 flex justify-center">
            <Link href="/" className="flex items-center gap-2">
              <img src="/logo.svg" alt="Citey logo" className="h-9 w-9" />
              <span className="text-xl font-bold text-white" style={{ fontFamily: "var(--font-syne)" }}>
                Citey
              </span>
            </Link>
          </div>

          {verifyScreen ? (
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-white/5 text-2xl">
                ✉
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Check your inbox</h1>
                <p className="mt-2 text-sm text-gray-400">
                  We sent a verification link to{" "}
                  <span className="font-medium text-gray-200">{email}</span>.
                  Click the link to activate your account.
                </p>
              </div>
              {resendSent ? (
                <p className="text-sm text-gray-400">Verification email resent.</p>
              ) : (
                <button
                  onClick={handleResend}
                  disabled={resendLoading}
                  className="text-sm font-medium text-gray-300 underline decoration-dotted underline-offset-2 hover:text-white disabled:opacity-50 transition-colors"
                >
                  {resendLoading ? "Sending…" : "Resend verification email"}
                </button>
              )}
              <Link
                href="/dashboard"
                className="mt-1 w-full rounded-xl bg-white py-3 text-center text-sm font-bold text-gray-950 shadow-lg transition-all hover:bg-gray-100"
              >
                Continue to dashboard
              </Link>
            </div>
          ) : (
            <>
          <h1 className="mb-2 text-center text-2xl font-bold text-white">
            {mode === "signin" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="mb-8 text-center text-sm text-gray-400">
            {mode === "signin"
              ? "Sign in to access your citation dashboard."
              : "Start tracking citations to your research, free forever."}
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-gray-300"
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
                className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                disabled={loading}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-gray-300"
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
                className="w-full rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-white/40 focus:ring-1 focus:ring-white/20"
                disabled={loading}
              />
            </div>

            {mode === "signup" && (
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
                  disabled={loading}
                />
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-1 rounded-xl bg-white py-3 text-sm font-bold text-gray-950 shadow-lg transition-all hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
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
                "Sign In"
              ) : (
                "Create Account"
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-400">
            {mode === "signin" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  onClick={toggle}
                  className="font-semibold text-gray-300 hover:text-white transition-colors"
                >
                  Sign up free
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={toggle}
                  className="font-semibold text-gray-300 hover:text-white transition-colors"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-gray-600">
          By using Citey you agree to our terms of service and privacy policy.
          Citation data sourced from{" "}
          <a href="https://openalex.org" target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-gray-400">
            OpenAlex
          </a>{" "}
          and{" "}
          <a href="https://www.crossref.org" target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-gray-400">
            Crossref
          </a>
          .
        </p>
      </div>
    </div>
  );
}
