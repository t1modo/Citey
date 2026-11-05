"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { unsubscribe } from "@/lib/api";

type Status = "loading" | "success" | "error";

function UnsubscribeContent() {
  const searchParams = useSearchParams();
  const uid = searchParams.get("uid") ?? "";
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!uid || !token) {
      setStatus("error");
      setMessage("This unsubscribe link is missing required parameters.");
      return;
    }

    unsubscribe(uid, token)
      .then(() => {
        setStatus("success");
        setMessage("You've been unsubscribed from all Citey notification emails.");
      })
      .catch((err: Error) => {
        setStatus("error");
        setMessage(err.message || "This link is invalid or has already been used.");
      });
  }, [uid, token]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#0a0a0f] px-4 text-center">
      <div className="w-full max-w-md rounded-2xl border border-rule bg-ink/5 p-10 shadow-xl backdrop-blur-sm">

        {status === "loading" && (
          <>
            <div className="mb-6 flex justify-center">
              <svg className="h-8 w-8 animate-spin text-muted" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
              </svg>
            </div>
            <p className="text-sm text-muted">Processing your request…</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mb-5 flex justify-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-ok/10">
                <svg className="h-7 w-7 text-ok" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </div>
            <h1 className="font-serif mb-2 text-xl font-semibold text-ink">Unsubscribed</h1>
            <p className="mb-8 text-sm leading-relaxed text-muted">{message}</p>
            <p className="mb-6 text-sm text-muted">
              Changed your mind? You can re-enable notifications at any time from{" "}
              <Link href="/settings" className="text-indigo-800 hover:underline">
                Settings
              </Link>
              .
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mb-5 flex justify-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-danger/10">
                <svg className="h-7 w-7 text-danger" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
            </div>
            <h1 className="font-serif mb-2 text-xl font-semibold text-ink">Link invalid</h1>
            <p className="mb-8 text-sm leading-relaxed text-muted">{message}</p>
            <p className="mb-6 text-sm text-muted">
              You can manage notification preferences from{" "}
              <Link href="/settings" className="text-indigo-800 hover:underline">
                Settings
              </Link>
              .
            </p>
          </>
        )}

        <Link
          href="/"
          className="text-xs text-muted hover:text-muted transition-colors"
        >
          ← Back to Citey
        </Link>
      </div>
    </main>
  );
}

export default function UnsubscribePage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-[#0a0a0f]">
          <svg className="h-8 w-8 animate-spin text-muted" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
          </svg>
        </main>
      }
    >
      <UnsubscribeContent />
    </Suspense>
  );
}
