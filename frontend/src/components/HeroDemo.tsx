"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

type Phase = 0 | 1 | 2 | 3;

const PHASE_LABELS = ["Dashboard", "Add papers", "Citey scans", "You're cited"];
const PHASE_MS = [6400, 8500, 4000, 6500];

const DOI = "10.18653/v1/2024.emnlp-main.291";

// ─── Windows arrow cursor ─────────────────────────────────────────────────────
// Tip of the arrow path sits at (1, 0.5). marginLeft/Top aligns that point with
// the waypoint coordinate so the hotspot is always the tip, not the bounding box.
interface CursorPos { lp: string; tp: string }

function DemoCursor({ pos, clicking }: { pos: CursorPos; clicking: boolean }) {
  return (
    <motion.div
      className="pointer-events-none absolute z-50"
      animate={{ left: pos.lp, top: pos.tp }}
      transition={{ type: "spring", stiffness: 90, damping: 22 }}
      style={{ marginLeft: "-1px", marginTop: "-1px" }}
    >
      <motion.svg
        width="16"
        height="25"
        viewBox="0 0 16 25"
        animate={clicking ? { scale: [1, 0.58, 1.28, 1] } : {}}
        transition={{ duration: 0.38 }}
        style={{
          transformOrigin: "1px 0.5px",
          filter: "drop-shadow(1px 2px 2px rgba(0,0,0,0.55))",
        }}
      >
        <path
          d="M 1 0.5 L 1 18.5 L 4.8 15 L 7.4 22 L 10 20.8 L 7.4 13.8 L 13 13.8 Z"
          fill="white"
          stroke="#1c1c1c"
          strokeWidth="1.3"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </motion.svg>
      {clicking && (
        <>
          <motion.div
            key="ripple-a"
            className="absolute rounded-full border-2 border-white/75"
            style={{ width: 14, height: 14, top: -7, left: -6 }}
            initial={{ scale: 0.25, opacity: 1 }}
            animate={{ scale: 2.8, opacity: 0 }}
            transition={{ duration: 0.38, ease: "easeOut" }}
          />
          <motion.div
            key="ripple-b"
            className="absolute rounded-full border border-white/40"
            style={{ width: 22, height: 22, top: -11, left: -10 }}
            initial={{ scale: 0.2, opacity: 0.85 }}
            animate={{ scale: 3.4, opacity: 0 }}
            transition={{ duration: 0.62, ease: "easeOut" }}
          />
        </>
      )}
    </motion.div>
  );
}

// ─── Phase 0: Tracked Works (matches real TrackedWorkCard) ────────────────────
function PhaseDashboard() {
  const papers = [
    {
      title: "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
      year: 2022,
      authors: "Wei · Cobbe · Lu · +5 more",
      citedBy: "3,241",
      newCitations: 12,
    },
    {
      title: "Finetuned Language Models Are Zero-Shot Learners",
      year: 2022,
      authors: "Wei · Bosma · Zhao · +3 more",
      citedBy: "847",
      newCitations: 3,
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      {/* Section header — matches real dashboard */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-white">Tracked Works</h2>
          <div className="flex rounded-lg border border-white/10 bg-gray-800 p-0.5">
            {["Year", "Cited By"].map((s, i) => (
              <span
                key={s}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                  i === 0 ? "bg-white text-gray-950 shadow" : "text-gray-400"
                }`}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
        {/* Import Papers button — matches real button */}
        <button className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-gray-950 shadow">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          Import Papers
        </button>
      </div>

      <p className="text-xs text-gray-500">2 papers</p>

      {/* Paper cards — matches real TrackedWorkCard structure */}
      <div className="flex flex-col gap-3">
        {papers.map((p, i) => (
          <motion.div
            key={p.title}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.13 }}
            className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-4 transition-all duration-200 hover:border-white/20"
          >
            {/* Title + year badge */}
            <div className="flex items-start justify-between gap-3">
              <h3 className="flex-1 text-sm font-semibold leading-snug text-white line-clamp-2">
                {p.title}
              </h3>
              <span className="shrink-0 rounded bg-gray-800 px-2 py-0.5 text-xs font-medium text-gray-400">
                {p.year}
              </span>
            </div>

            {/* Authors */}
            <p className="text-xs text-gray-400">{p.authors}</p>

            {/* Citation stats — matches real badge styles */}
            <div className="flex items-center gap-2">
              <span className="rounded-full border border-white/10 bg-gray-800 px-2.5 py-0.5 text-xs font-medium text-gray-300">
                Cited by {p.citedBy}
              </span>
              <motion.span
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.4 + i * 0.1, type: "spring", stiffness: 300, damping: 20 }}
                className="rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 text-xs font-semibold text-white"
              >
                +{p.newCitations} new
              </motion.span>
            </div>

            {/* Footer row — matches real footer */}
            <div className="flex items-center justify-between gap-2 border-t border-white/5 pt-2">
              <span className="flex items-center gap-1.5 text-xs text-gray-500">
                <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
                Checked Apr 15, 2026
              </span>
              <button className="rounded px-2.5 py-1 text-xs font-medium text-red-400 hover:bg-red-500/10">
                Remove
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

// ─── Phase 1: Import modal (matches real ImportModal input phase) ─────────────
function PhaseAddPaper() {
  const [typed, setTyped] = useState("");
  const [detected, setDetected] = useState(false);
  const [btnClicked, setBtnClicked] = useState(false);

  useEffect(() => {
    let idx = 0;
    setTyped("");
    setDetected(false);
    setBtnClicked(false);

    // Input click:   wp2 fires at 2100ms from phase start; mount offset ~320ms → ~1780ms from mount
    // Typing starts: 2000ms after click = ~3780ms from mount (2 s delay)
    // Look up click: wp5 fires at 7300ms from phase start → ~6980ms from mount → clicking at ~7360ms
    const clickTimer = setTimeout(() => setBtnClicked(true), 7360);

    // Typing starts 2 s after the input click
    const start = setTimeout(() => {
      const iv = setInterval(() => {
        idx++;
        setTyped(DOI.slice(0, idx));
        if (idx >= DOI.length) {
          clearInterval(iv);
          setTimeout(() => setDetected(true), 300);
        }
      }, 48);
      return () => clearInterval(iv);
    }, 3780);

    return () => {
      clearTimeout(clickTimer);
      clearTimeout(start);
    };
  }, []);

  const chips = [
    { label: "DOI",            cls: "border-sky-500/25 bg-sky-500/10 text-sky-400" },
    { label: "arXiv URL",      cls: "border-teal-500/25 bg-teal-500/10 text-teal-400" },
    { label: "INSPIRE profile",cls: "border-purple-500/25 bg-purple-500/10 text-purple-400" },
    { label: "DBLP profile",   cls: "border-orange-500/25 bg-orange-500/10 text-orange-400" },
    { label: "author name",    cls: "border-white/10 bg-white/5 text-gray-400" },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* Modal header — matches real ImportModal */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Add Papers</h2>
        <button className="rounded-md p-1.5 text-gray-400 hover:bg-white/5 hover:text-white">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Input */}
      <div>
        <div className="flex items-center rounded-lg border border-white/10 bg-gray-800 px-4 py-2.5">
          <span className="flex-1 font-mono text-sm">
            {typed ? (
              <span className="text-white">
                {typed}
                {!detected && <span className="inline-block w-px animate-pulse bg-white">&nbsp;</span>}
              </span>
            ) : (
              <span className="text-gray-500">DOI, arXiv URL, author URL, or name…</span>
            )}
          </span>
        </div>

        {/* Detected hint — matches real teal hint */}
        {detected && (
          <motion.p
            initial={{ opacity: 0, y: -3 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-1.5 text-xs text-teal-400/80"
          >
            Detected: DOI
          </motion.p>
        )}

        {/* Format chips — shown before typing */}
        {!typed && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-gray-600">Accepts</span>
            {chips.map((c) => (
              <span
                key={c.label}
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${c.cls}`}
              >
                {c.label}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Action buttons — matches real modal buttons */}
      <div className="flex justify-end gap-3">
        <button className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/5">
          Cancel
        </button>
        <motion.button
          className="rounded-lg bg-white px-5 py-2 text-sm font-semibold text-gray-950 shadow-lg"
          animate={btnClicked ? { scale: [1, 0.84, 1.06, 1], opacity: [1, 0.65, 1, 1] } : {}}
          transition={{ duration: 0.38, ease: "easeInOut" }}
        >
          {btnClicked ? "Looking up…" : "Look up"}
        </motion.button>
      </div>
    </div>
  );
}

// ─── Phase 2: Scanning ────────────────────────────────────────────────────────
function PhaseScanning() {
  const [progress, setProgress] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    setProgress(0);
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / 2600, 1);
      setProgress(Math.round(t * 100));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current !== null) cancelAnimationFrame(rafRef.current); };
  }, []);

  return (
    <div className="flex flex-col items-center gap-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
        Daily citation scan
      </p>

      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white/10" />
        <span className="absolute inline-flex h-20 w-20 animate-ping rounded-full bg-white/[0.08] [animation-delay:0.3s]" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-white/20 bg-white/5 text-3xl">
          🔍
        </div>
      </div>

      <div className="w-full">
        <div className="mb-2 flex justify-between text-xs text-gray-500">
          <span>OpenAlex · Crossref · Semantic Scholar · PubMed · NASA ADS · INSPIRE · DBLP</span>
          <span className="font-medium text-white">{progress}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
          <motion.div
            className="h-full rounded-full bg-white"
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.1 }}
          />
        </div>
      </div>

      <p className="text-center text-sm text-gray-500">Checking 250M+ scholarly works</p>
    </div>
  );
}

// ─── Phase 3: Citations panel (matches real RecentCitationCard) ───────────────
function PhaseCited() {
  return (
    <div className="flex flex-col gap-3">
      {/* Section header — matches real Citations section */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold text-white">
            Citations
            <span className="ml-2 rounded-full bg-white px-2 py-0.5 text-xs font-bold text-gray-950">
              2
            </span>
          </h2>
          <p className="mt-0.5 text-xs text-gray-500">47 total · page 1 of 5</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="text-xs font-medium text-gray-500 hover:text-gray-300">
            Mark all as read
          </button>
        </div>
      </div>

      {/* RecentCitationCard — mirrors real component exactly */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="flex cursor-pointer flex-col gap-3 rounded-xl border border-white/15 bg-white/5 p-4 transition-all duration-200 hover:border-white/20"
      >
        {/* Header: unread dot + label + date */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 shrink-0 rounded-full bg-white" />
            <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
              New citation
            </span>
          </div>
          <span className="shrink-0 text-xs text-gray-600">Apr 18, 2026</span>
        </div>

        {/* Citing paper title — underlined link style */}
        <p className="text-sm font-bold leading-snug text-white underline decoration-dotted underline-offset-2">
          Attention Is All You Need
        </p>

        {/* Authors */}
        <p className="text-xs leading-relaxed text-gray-400 -mt-1">
          Vaswani · Shazeer · Parmar
        </p>

        {/* "cites your paper" divider */}
        <div className="flex items-center gap-2">
          <div className="h-px flex-1 bg-white/5" />
          <span className="text-[10px] italic text-gray-600">cites your paper</span>
          <div className="h-px flex-1 bg-white/5" />
        </div>

        {/* Your paper */}
        <div>
          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-400">
            Your paper
          </p>
          <p className="text-xs leading-snug text-white/70">
            Chain-of-Thought Prompting Elicits Reasoning in Large Language Models
          </p>
        </div>

        {/* Affiliation pills — matches real ring-1 ring-white/10 style */}
        <div className="flex flex-wrap gap-1.5">
          {["Google Brain", "Univ. of Toronto", "Google Research"].map((affil) => (
            <span
              key={affil}
              className="inline-flex items-center rounded-full bg-white/[0.08] px-2.5 py-0.5 text-xs font-medium text-gray-300 ring-1 ring-white/10"
            >
              {affil}
            </span>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

// ─── Cursor waypoints per phase ───────────────────────────────────────────────
// Coordinates are CSS left/top % relative to the full card (title bar + content + footer).
// Card approx layout: title bar ~8%, content ~84%, footer ~8%.
type Waypoint = { lp: string; tp: string; afterMs: number; click?: true };

const CURSOR_SEQUENCES: Waypoint[][] = [
  // Phase 0: Dashboard — notice "+new" badges, hover Import Papers, then click
  [
    { lp: "72%", tp: "38%", afterMs: 1000 },              // first card "+12 new"
    { lp: "66%", tp: "66%", afterMs: 1100 },              // second card "+3 new"
    { lp: "86%", tp: "17%", afterMs: 3000 },              // cursor settles on Import Papers (~3 s)
    { lp: "86%", tp: "17%", afterMs: 600, click: true },  // then clicks
  ],
  // Phase 1: Add Papers modal — hover over input, click, 2 s delay, type DOI, click Look up
  [
    { lp: "50%", tp: "32%", afterMs: 2100 },              // cursor moves to input, hovers ~2 s
    { lp: "50%", tp: "32%", afterMs: 700,  click: true }, // cursor clicks input
    { lp: "50%", tp: "32%", afterMs: 3600 },              // wait while typing (2 s delay + DOI)
    { lp: "85%", tp: "47%", afterMs: 900  },              // cursor travels to Look up button
    { lp: "85%", tp: "47%", afterMs: 300,  click: true }, // cursor clicks Look up
  ],
  // Phase 2: Scanning — watch search icon, then follow progress bar
  [
    { lp: "50%", tp: "34%", afterMs: 1000 },             // search icon
    { lp: "14%", tp: "62%", afterMs: 1100 },             // progress bar start
    { lp: "88%", tp: "62%", afterMs: 1500 },             // progress bar end
  ],
  // Phase 3: Citations panel — unread dot → title → divider → affiliation pills
  [
    { lp: "10%", tp: "25%", afterMs: 900 },              // unread dot
    { lp: "45%", tp: "35%", afterMs: 1000 },             // paper title
    { lp: "50%", tp: "54%", afterMs: 1000 },             // "cites your paper" divider
    { lp: "38%", tp: "72%", afterMs: 1200 },             // affiliation pills
  ],
];

// ─── Main component ───────────────────────────────────────────────────────────
export default function HeroDemo() {
  const [phase, setPhase] = useState<Phase>(0);
  const [cursorPos, setCursorPos] = useState<CursorPos>({ lp: "50%", tp: "50%" });
  const [clicking, setClicking] = useState(false);

  useEffect(() => {
    const t = setTimeout(
      () => setPhase((p) => (((p + 1) % 4) as Phase)),
      PHASE_MS[phase],
    );
    return () => clearTimeout(t);
  }, [phase]);

  useEffect(() => {
    const waypoints = CURSOR_SEQUENCES[phase];
    let active = true;
    const timeouts: ReturnType<typeof setTimeout>[] = [];
    let elapsed = 0;

    for (const wp of waypoints) {
      const delay = elapsed;
      const t = setTimeout(() => {
        if (!active) return;
        setCursorPos({ lp: wp.lp, tp: wp.tp });
        if (wp.click) {
          const ct = setTimeout(() => {
            if (!active) return;
            setClicking(true);
            const rt = setTimeout(() => setClicking(false), 340);
            timeouts.push(rt);
          }, 380);
          timeouts.push(ct);
        }
      }, delay);
      timeouts.push(t);
      elapsed += wp.afterMs;
    }

    return () => {
      active = false;
      timeouts.forEach(clearTimeout);
    };
  }, [phase]);

  return (
    <div className="relative z-10 mx-auto w-full max-w-xl lg:max-w-2xl">
      <div className="relative overflow-hidden rounded-2xl border border-white/15 bg-gray-950/80 shadow-2xl shadow-black/50 backdrop-blur-xl">
        <DemoCursor pos={cursorPos} clicking={clicking} />

        {/* Title bar */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          </div>
          <span
            className="text-xs font-semibold text-gray-400"
            style={{ fontFamily: "var(--font-syne)" }}
          >
            Citey
          </span>
          <div className="w-14" />
        </div>

        {/* Phase content */}
        <div className="relative min-h-[360px] px-6 py-5 [@media(max-height:820px)]:min-h-[240px] [@media(max-height:820px)]:px-4 [@media(max-height:820px)]:py-4">
          <AnimatePresence mode="wait">
            <motion.div
              key={phase}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            >
              {phase === 0 && <PhaseDashboard />}
              {phase === 1 && <PhaseAddPaper />}
              {phase === 2 && <PhaseScanning />}
              {phase === 3 && <PhaseCited />}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Step indicators */}
        <div className="border-t border-white/[0.08] px-5 py-3">
          <div className="flex items-center justify-center gap-3">
            {PHASE_LABELS.map((label, i) => (
              <button
                key={i}
                onClick={() => setPhase(i as Phase)}
                className="group flex items-center gap-1.5"
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
