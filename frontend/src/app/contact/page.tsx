"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { sendSupportMessage } from "@/lib/api";

const field =
  "w-full rounded-lg border border-control bg-sheet px-4 py-2.5 text-sm text-ink placeholder-muted outline-none transition-colors focus:border-ink focus:ring-1 focus:ring-ink/20";
const label = "mb-1.5 block text-sm font-medium text-ink";

export default function ContactPage() {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // trap field for bots
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");
  const openedAt = useRef(Date.now());

  useEffect(() => {
    if (user?.email && !email) setEmail(user.email);
  }, [user, email]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (message.trim().length < 10) {
      setError("Tell us a little more, at least a sentence.");
      return;
    }
    setStatus("sending");
    try {
      await sendSupportMessage({
        name: name.trim() || undefined,
        email: email.trim(),
        subject: subject.trim() || undefined,
        message: message.trim(),
        website,
        elapsed_ms: Date.now() - openedAt.current,
      });
      setStatus("sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "We couldn't send your message. Please try again.");
      setStatus("idle");
    }
  };

  return (
    <div className="mx-auto max-w-xl px-4 py-16 sm:px-6">
      <h1 className="mb-3 font-serif text-4xl font-semibold text-ink">Contact us</h1>
      <p className="mb-10 leading-relaxed text-muted">
        A question, a missing citation, or an idea? Send it here and we&apos;ll reply by email.
        Many answers are already in the <Link href="/faq" className="text-ink underline underline-offset-2">FAQ</Link>.
      </p>

      {status === "sent" ? (
        <div className="border-t border-rule pt-6" role="status">
          <p className="mb-2 font-serif text-xl font-semibold text-ink">Message sent</p>
          <p className="leading-relaxed text-muted">
            Thanks. We&apos;ll reply to {email}, usually within a couple of days.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label htmlFor="name" className={label}>Name <span className="font-normal text-muted">(optional)</span></label>
              <input id="name" autoComplete="name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={field} />
            </div>
            <div>
              <label htmlFor="email" className={label}>Your email</label>
              <input id="email" type="email" autoComplete="email" required maxLength={254} value={email}
                onChange={(e) => setEmail(e.target.value)} placeholder="you@institution.edu" className={field} />
            </div>
          </div>
          <div>
            <label htmlFor="subject" className={label}>Subject <span className="font-normal text-muted">(optional)</span></label>
            <input id="subject" maxLength={150} value={subject} onChange={(e) => setSubject(e.target.value)} className={field} />
          </div>
          <div>
            <label htmlFor="message" className={label}>Message</label>
            <textarea id="message" required rows={7} maxLength={5000} value={message}
              onChange={(e) => setMessage(e.target.value)} className={`${field} resize-y leading-relaxed`} />
          </div>

          {/* Hidden from people and screen readers; bots fill it in. */}
          <div aria-hidden="true" className="absolute left-[-9999px] h-px w-px overflow-hidden">
            <label htmlFor="website">Website</label>
            <input id="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
          </div>

          {error && <p className="text-sm text-danger" role="alert">{error}</p>}

          <button type="submit" disabled={status === "sending" || !email.trim()}
            className="self-start rounded-md bg-ink px-6 py-3 text-base font-bold text-paper transition-colors hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-50">
            {status === "sending" ? "Sending…" : "Send message"}
          </button>
        </form>
      )}
    </div>
  );
}
