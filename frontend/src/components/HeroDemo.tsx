"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

type Phase = 0 | 1 | 2;

const PHASE_LABELS = ["Track a paper", "Citey scans", "You're cited"];
const PHASE_MS = [3800, 3000, 3800];

const DOI = "10.18653/v1/2024.emnlp-main.291";

// ─── Phase 0: Add DOI ────────────────────────────────────────────────────────
function PhaseAddDoi() {
  const [typed, setTyped] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let idx = 0;
    setTyped("");
    setSubmitted(false);

    const typeInterval = setInterval(() => {
      idx++;
      setTyped(DOI.slice(0, idx));
      if (idx >= DOI.length) {
        clearInterval(typeInterval);
        setTimeout(() => setSubmitted(true), 500);
      }
    }, 55);

    return () => clearInterval(typeInterval);
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
        Step 1. Add your paper
      </p>
      <div>
        <label className="mb-2 block text-sm font-medium text-gray-400">
          DOI
        </label>
        <div className="flex items-center gap-2 rounded-lg border border-white/15 bg-gray-900 px-4 py-3">
          <span className="flex-1 font-mono text-base text-white">
            {typed}
            <span className="inline-block w-px bg-white animate-pulse">&nbsp;</span>
          </span>
        </div>
      </div>
      <motion.button
        className="w-full rounded-lg bg-white py-3 text-base font-semibold text-gray-950 shadow transition-opacity"
        animate={submitted ? { scale: [1, 0.97, 1], opacity: [1, 0.8, 1] } : {}}
        transition={{ duration: 0.3 }}
      >
        {submitted ? "✓ Paper added" : "Track Paper"}
      </motion.button>
      {submitted && (
        <motion.p
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center text-sm text-gray-400"
        >
          Monitoring for new citations daily.
        </motion.p>
      )}
    </div>
  );
}

// ─── Phase 1: Scanning ───────────────────────────────────────────────────────
function PhaseScanning() {
  const [progress, setProgress] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    setProgress(0);
    const start = performance.now();
    const animate = (now: number) => {
      const t = Math.min((now - start) / 2200, 1);
      setProgress(Math.round(t * 100));
      if (t < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <div className="flex flex-col items-center gap-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
        Step 2. Daily scan
      </p>

      {/* Pulsing rings */}
      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white/10" />
        <span className="absolute inline-flex h-20 w-20 animate-ping rounded-full bg-white/8 [animation-delay:0.3s]" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-white/20 bg-white/5 text-3xl">
          🔍
        </div>
      </div>

      <div className="w-full">
        <div className="mb-2 flex justify-between text-sm text-gray-500">
          <span>Scanning OpenAlex &amp; Crossref</span>
          <span className="text-white">{progress}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
          <motion.div
            className="h-full rounded-full bg-white"
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.1 }}
          />
        </div>
      </div>

      <p className="text-center text-sm text-gray-500">
        Checking 250M+ scholarly works
      </p>
    </div>
  );
}

// ─── Phase 2: Citation found ─────────────────────────────────────────────────
function PhaseCited() {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
        Step 3. Email alert
      </p>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="rounded-xl border border-white/15 bg-white/5 p-5"
      >
        {/* Badge */}
        <div className="mb-3 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-white" />
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            New citation detected
          </span>
        </div>

        {/* Citing paper */}
        <p className="mb-1 text-base font-bold leading-snug text-white">
          Attention Is All You Need
        </p>
        <p className="mb-3 text-sm text-gray-400">
          Vaswani et al. &nbsp;&middot;&nbsp; 2017
        </p>

        {/* Divider */}
        <div className="mb-3 flex items-center gap-2">
          <div className="h-px flex-1 bg-white/8" />
          <span className="text-xs italic text-gray-600">cites your paper</span>
          <div className="h-px flex-1 bg-white/8" />
        </div>

        {/* Affiliation pills */}
        <div className="flex flex-wrap justify-center gap-2">
          {["Google Brain", "University of Toronto"].map((lab) => (
            <span
              key={lab}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-gray-300"
            >
              {lab}
            </span>
          ))}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.5 }}
        className="flex items-center justify-center gap-2 text-sm text-gray-500"
      >
        <span>📬</span>
        <span>Email sent to your inbox</span>
      </motion.div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function HeroDemo() {
  const [phase, setPhase] = useState<Phase>(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setPhase((p) => (((p + 1) % 3) as Phase));
    }, PHASE_MS[phase]);
    return () => clearTimeout(timer);
  }, [phase]);

  return (
    <div className="relative z-10 w-full max-w-xl lg:max-w-2xl mx-auto">
      {/* Window chrome */}
      <div className="rounded-2xl border border-white/15 bg-gray-950/80 shadow-2xl shadow-black/50 backdrop-blur-xl overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center justify-between border-b border-white/8 px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          </div>
          <span className="text-xs font-semibold text-gray-400" style={{ fontFamily: "var(--font-syne)" }}>Citey</span>
          <div className="w-14" />
        </div>

        {/* Content */}
        <div className="relative min-h-[300px] px-8 py-7">
          <AnimatePresence mode="wait">
            <motion.div
              key={phase}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            >
              {phase === 0 && <PhaseAddDoi />}
              {phase === 1 && <PhaseScanning />}
              {phase === 2 && <PhaseCited />}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Step indicators */}
        <div className="border-t border-white/8 px-5 py-3">
          <div className="flex items-center justify-center gap-3">
            {PHASE_LABELS.map((label, i) => (
              <button
                key={i}
                onClick={() => setPhase(i as Phase)}
                className="flex items-center gap-1.5 group"
              >
                <span
                  className={`h-1.5 w-6 rounded-full transition-all duration-300 ${
                    phase === i ? "bg-white" : "bg-white/20"
                  }`}
                />
                <span
                  className={`text-[10px] font-medium transition-colors ${
                    phase === i ? "text-gray-300" : "text-gray-600"
                  }`}
                >
                  {label}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
