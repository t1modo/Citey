"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useInView } from "framer-motion";
import Logo from "@/components/Logo";

// The card is authored at this width. On narrower viewports we apply a
// CSS scale transform so the layout never reflows and cursor hotspots
// (which are % of the card) stay perfectly aligned at every screen size.
const DESIGN_WIDTH = 576;

type Phase = 0 | 1 | 2 | 3;

const PHASE_LABELS = ["Dashboard", "Add papers", "Citey scans", "You're cited"];
const PHASE_MS = [6400, 8500, 4000, 6500];

// ─── Demo data pool ──────────────────────────────────────────────────────────

type DemoTrackedPaper = {
  title: string;
  year: number;
  authors: string;
  citedBy: string;
  newCitations: number;
};

type DemoCitation = {
  citingTitle: string;
  citingAuthors: string;
  citingDate: string;
  yourPaper: string;
  affiliations: string[];
};

type DemoEntry = {
  doi: string;
  trackedPapers: [DemoTrackedPaper, DemoTrackedPaper];
  citation: DemoCitation;
};

const DEMO_POOL: DemoEntry[] = [
  // ── 1. Transformers / NLP ────────────────────────────────────────────────
  {
    doi: "10.48550/arXiv.1706.03762",
    trackedPapers: [
      {
        title: "Attention Is All You Need",
        year: 2017,
        authors: "Vaswani, Shazeer, Parmar and 5 more",
        citedBy: "131,204",
        newCitations: 47,
      },
      {
        title: "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        year: 2019,
        authors: "Devlin, Chang, Lee and 1 more",
        citedBy: "96,518",
        newCitations: 29,
      },
    ],
    citation: {
      citingTitle: "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
      citingAuthors: "Gu, Dao",
      citingDate: "Apr 12, 2026",
      yourPaper: "Attention Is All You Need",
      affiliations: ["Carnegie Mellon", "Princeton", "Together AI"],
    },
  },
  // ── 2. Computer Vision ───────────────────────────────────────────────────
  {
    doi: "10.1109/CVPR.2016.90",
    trackedPapers: [
      {
        title: "Deep Residual Learning for Image Recognition",
        year: 2016,
        authors: "He, Zhang, Ren, Sun",
        citedBy: "208,347",
        newCitations: 63,
      },
      {
        title: "An Image is Worth 16×16 Words: Transformers for Image Recognition at Scale",
        year: 2021,
        authors: "Dosovitskiy, Beyer, Kolesnikov and 10 more",
        citedBy: "44,281",
        newCitations: 19,
      },
    ],
    citation: {
      citingTitle: "Segment Anything",
      citingAuthors: "Kirillov, Mintun, Ravi and 9 more",
      citingDate: "Apr 18, 2026",
      yourPaper: "Deep Residual Learning for Image Recognition",
      affiliations: ["Meta AI Research", "CMU"],
    },
  },
  // ── 3. Large Language Models ─────────────────────────────────────────────
  {
    doi: "10.48550/arXiv.2005.14165",
    trackedPapers: [
      {
        title: "Language Models are Few-Shot Learners",
        year: 2020,
        authors: "Brown, Mann, Ryder and 28 more",
        citedBy: "57,831",
        newCitations: 22,
      },
      {
        title: "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        year: 2022,
        authors: "Wei, Wang, Schuurmans and 4 more",
        citedBy: "11,842",
        newCitations: 8,
      },
    ],
    citation: {
      citingTitle: "Llama 2: Open Foundation and Fine-Tuned Chat Models",
      citingAuthors: "Touvron, Martin, Stone and 55 more",
      citingDate: "Apr 15, 2026",
      yourPaper: "Language Models are Few-Shot Learners",
      affiliations: ["Meta AI", "UT Austin", "CMU"],
    },
  },
  // ── 4. CRISPR / Genomics ─────────────────────────────────────────────────
  {
    doi: "10.1126/science.1225829",
    trackedPapers: [
      {
        title: "A Programmable Dual-RNA–Guided DNA Endonuclease in Adaptive Bacterial Immunity",
        year: 2012,
        authors: "Jinek, Chylinski, Fonfara and 3 more",
        citedBy: "24,108",
        newCitations: 11,
      },
      {
        title: "Multiplex Genome Engineering Using CRISPR/Cas Systems",
        year: 2013,
        authors: "Cong, Ran, Cox and 7 more",
        citedBy: "18,392",
        newCitations: 6,
      },
    ],
    citation: {
      citingTitle: "Programmable base editing of A·T to G·C in genomic DNA without DNA cleavage",
      citingAuthors: "Gaudelli, Komor, Rees and 4 more",
      citingDate: "Apr 9, 2026",
      yourPaper: "A Programmable Dual-RNA–Guided DNA Endonuclease in Adaptive Bacterial Immunity",
      affiliations: ["Broad Institute", "Harvard University", "MIT"],
    },
  },
  // ── 5. Gravitational Waves / Astrophysics ────────────────────────────────
  {
    doi: "10.1103/PhysRevLett.116.061102",
    trackedPapers: [
      {
        title: "Observation of Gravitational Waves from a Binary Black Hole Merger",
        year: 2016,
        authors: "Abbott, Abbott, Abbott and 1009 more",
        citedBy: "18,743",
        newCitations: 9,
      },
      {
        title: "First M87 Event Horizon Telescope Results. I. The Shadow of the Supermassive Black Hole",
        year: 2019,
        authors: "Akiyama, Alberdi, Alef and 198 more",
        citedBy: "4,821",
        newCitations: 4,
      },
    ],
    citation: {
      citingTitle: "GW190521: A Binary Black Hole Merger with a Total Mass of 150 M☉",
      citingAuthors: "Abbott, Abbott, Abbott and 1203 more",
      citingDate: "Apr 7, 2026",
      yourPaper: "Observation of Gravitational Waves from a Binary Black Hole Merger",
      affiliations: ["LIGO Scientific Collaboration", "Virgo Collaboration"],
    },
  },
  // ── 6. Behavioral Economics ──────────────────────────────────────────────
  {
    doi: "10.2307/1914185",
    trackedPapers: [
      {
        title: "Prospect Theory: An Analysis of Decision under Risk",
        year: 1979,
        authors: "Kahneman, Tversky",
        citedBy: "57,832",
        newCitations: 18,
      },
      {
        title: "The Strength of Weak Ties",
        year: 1973,
        authors: "Granovetter",
        citedBy: "64,201",
        newCitations: 21,
      },
    ],
    citation: {
      citingTitle: "A Model of Reference-Dependent Preferences",
      citingAuthors: "Kőszegi, Rabin",
      citingDate: "Apr 14, 2026",
      yourPaper: "Prospect Theory: An Analysis of Decision under Risk",
      affiliations: ["UC Berkeley", "Harvard University"],
    },
  },
];

// ─── Windows arrow cursor ─────────────────────────────────────────────────────
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
        animate={clicking ? { scale: [1, 0.48, 1.42, 1] } : {}}
        transition={{ duration: 0.44 }}
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
            className="absolute rounded-full border-2 border-rule"
            style={{ width: 14, height: 14, top: -7, left: -6 }}
            initial={{ scale: 0.25, opacity: 1 }}
            animate={{ scale: 2.8, opacity: 0 }}
            transition={{ duration: 0.38, ease: "easeOut" }}
          />
          <motion.div
            key="ripple-b"
            className="absolute rounded-full border border-rule"
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

// ─── Phase 0: Tracked papers ───────────────────────────────────────────────────
function PhaseDashboard({ papers }: { papers: DemoEntry["trackedPapers"] }) {
  const [btnPressed, setBtnPressed] = useState(false);

  useEffect(() => {
    setBtnPressed(false);
    const t = setTimeout(() => setBtnPressed(true), 4100);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="font-serif text-lg font-semibold text-ink">Your papers</h2>
          <div className="flex rounded-md border border-rule bg-sheet p-0.5">
            {["Newest", "Most cited"].map((s, i) => (
              <span
                key={s}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                  i === 0 ? "bg-ink text-paper" : "text-muted"
                }`}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
        <motion.button
          className="flex shrink-0 items-center gap-1.5 rounded-md bg-ink px-3 py-2 text-xs font-bold text-paper"
          animate={btnPressed ? { scale: [1, 0.84, 1.08, 1] } : {}}
          transition={{ duration: 0.42, ease: "easeInOut" }}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          Add papers
        </motion.button>
      </div>

      <p className="text-xs text-muted">2 papers</p>

      <div className="divide-y divide-rule border-y border-rule">
        {papers.map((p, i) => (
          <motion.article
            key={p.title}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.13 }}
            className="py-4"
          >
            <h3 className="mb-1 line-clamp-2 font-serif text-[15px] font-semibold leading-snug text-ink">{p.title}</h3>
            <p className="text-xs text-muted">
              {p.authors}. <i>{p.year}</i>.
            </p>
            <div className="mt-2 flex items-center gap-3 text-xs">
              <span className="text-ink">Cited by {p.citedBy}</span>
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 + i * 0.1 }}
                className="highlight font-bold text-ink"
              >
                {p.newCitations} new this month
              </motion.span>
              <span className="ml-auto text-muted">Checked Apr 15</span>
            </div>
          </motion.article>
        ))}
      </div>
    </div>
  );
}

// ─── Phase 1: Import modal ────────────────────────────────────────────────────
function PhaseAddPaper({ doi }: { doi: string }) {
  const [focused, setFocused] = useState(false);
  const [typed, setTyped] = useState("");
  const [detected, setDetected] = useState(false);
  const [btnClicked, setBtnClicked] = useState(false);

  useEffect(() => {
    let idx = 0;
    setFocused(false);
    setTyped("");
    setDetected(false);
    setBtnClicked(false);

    const focusTimer = setTimeout(() => setFocused(true), 2200);
    const clickTimer = setTimeout(() => setBtnClicked(true), 7360);

    const start = setTimeout(() => {
      const iv = setInterval(() => {
        idx++;
        setTyped(doi.slice(0, idx));
        if (idx >= doi.length) {
          clearInterval(iv);
          setTimeout(() => setDetected(true), 300);
        }
      }, 48);
      return () => clearInterval(iv);
    }, 3780);

    return () => {
      clearTimeout(focusTimer);
      clearTimeout(clickTimer);
      clearTimeout(start);
    };
  }, [doi]);

  const chips = [
    { label: "DOI",             cls: "border-sky-300 bg-sky-100 text-sky-800" },
    { label: "arXiv URL",       cls: "border-ok/40 bg-ok/10 text-ok" },
    { label: "INSPIRE profile", cls: "border-purple-300 bg-purple-100 text-purple-800" },
    { label: "DBLP profile",    cls: "border-orange-300 bg-orange-100 text-orange-800" },
    { label: "author name",     cls: "border-rule bg-ink/5 text-muted" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">Add papers</h2>
        <button className="rounded-md p-1.5 text-muted hover:bg-ink/5 hover:text-ink">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div>
        <div className="flex items-center rounded-lg border border-rule bg-sheet px-4 py-2.5">
          <span className="flex-1 text-left font-mono text-sm">
            {focused ? (
              <>
                {typed && <span className="text-ink">{typed}</span>}
                {!detected && (
                  <motion.span
                    className="inline-block w-px bg-ink"
                    style={{ height: "1em", verticalAlign: "text-bottom", marginLeft: "1px" }}
                    animate={{ opacity: [1, 1, 0, 0] }}
                    transition={{ duration: 1, times: [0, 0.47, 0.5, 0.97], repeat: Infinity, ease: "linear" }}
                  />
                )}
              </>
            ) : (
              <span className="text-muted">DOI, arXiv URL, author URL, or name…</span>
            )}
          </span>
        </div>

        {detected && (
          <motion.p
            initial={{ opacity: 0, y: -3 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-1.5 text-xs text-ok"
          >
            Detected: DOI
          </motion.p>
        )}

        {!typed && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-medium text-muted">Accepts</span>
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

      <div className="flex justify-end gap-3">
        <button className="rounded-lg border border-rule px-4 py-2 text-sm font-medium text-ink hover:bg-ink/5">
          Cancel
        </button>
        <motion.button
          className="rounded-lg bg-ink px-5 py-2 text-sm font-semibold text-paper shadow-lg"
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
      <p className="text-center text-xs font-semibold text-muted">
        Daily citation scan
      </p>

      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ink/10" />
        <span className="absolute inline-flex h-20 w-20 animate-ping rounded-full bg-ink/5 [animation-delay:0.3s]" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-rule bg-sheet text-ink">
          <Logo className="h-8 w-8" />
        </div>
      </div>

      <div className="w-full">
        <div className="mb-2 flex justify-between gap-2 text-xs text-muted">
          <span className="truncate">Checking all seven indexes</span>
          <span className="shrink-0 font-medium text-ink">{progress}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-ink/10">
          <motion.div
            className="h-full rounded-full bg-ink"
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.1 }}
          />
        </div>
      </div>

      <p className="text-center text-sm text-muted">OpenAlex, Crossref, Semantic Scholar, PubMed, NASA ADS, INSPIRE and DBLP</p>
    </div>
  );
}

// ─── Phase 3: Citations panel ─────────────────────────────────────────────────
function PhaseCited({ citation }: { citation: DemoEntry["citation"] }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-serif text-lg font-semibold text-ink">Recent citations</h2>
          <p className="mt-0.5 text-xs text-muted">Papers that cited you in the last 30 days</p>
        </div>
        <button className="text-xs font-medium text-muted hover:text-ink">Mark all as read</button>
      </div>

      <motion.article
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="border-y border-rule py-4"
      >
        <div className="mb-1 flex items-baseline justify-between gap-3">
          <h3 className="font-serif text-[15px] font-semibold leading-snug text-ink">
            <span className="highlight mr-1.5 font-sans text-[11px] font-bold">New</span>
            <span className="underline decoration-rule underline-offset-4">{citation.citingTitle}</span>
          </h3>
          <span className="shrink-0 text-xs text-muted">{citation.citingDate}</span>
        </div>
        <p className="text-xs leading-relaxed text-muted">{citation.citingAuthors}</p>
        <p className="text-xs leading-relaxed text-muted">{citation.affiliations.join("; ")}</p>
        <p className="mt-2 text-xs text-ink">
          Cites <i className="font-serif">{citation.yourPaper}</i>
        </p>
      </motion.article>
    </div>
  );
}

// ─── Cursor waypoints per phase ───────────────────────────────────────────────
type Waypoint = { lp: string; tp: string; afterMs: number; click?: true };

const CURSOR_SEQUENCES: Waypoint[][] = [
  // Phase 0: Dashboard — notice "+new" badges, hover Add papers, then click
  [
    { lp: "72%", tp: "38%", afterMs: 1000 },
    { lp: "66%", tp: "66%", afterMs: 1100 },
    { lp: "86%", tp: "17%", afterMs: 1620 },
    { lp: "86%", tp: "17%", afterMs: 600, click: true },
  ],
  // Phase 1: Add papers modal — hover over input, click, 2 s delay, type DOI, click Look up
  [
    { lp: "50%", tp: "29%", afterMs: 2100 },
    { lp: "50%", tp: "29%", afterMs: 700,  click: true },
    { lp: "50%", tp: "29%", afterMs: 3600 },
    { lp: "85%", tp: "47%", afterMs: 900  },
    { lp: "85%", tp: "47%", afterMs: 300,  click: true },
  ],
  // Phase 2: Scanning — watch search icon, then follow progress bar
  [
    { lp: "50%", tp: "34%", afterMs: 1000 },
    { lp: "14%", tp: "62%", afterMs: 1100 },
    { lp: "88%", tp: "62%", afterMs: 1500 },
  ],
  // Phase 3: Citations panel — unread dot → title → divider → affiliation pills
  [
    { lp: "10%", tp: "25%", afterMs: 900 },
    { lp: "45%", tp: "35%", afterMs: 1000 },
    { lp: "50%", tp: "54%", afterMs: 1000 },
    { lp: "38%", tp: "72%", afterMs: 1200 },
  ],
];

// ─── Main component ───────────────────────────────────────────────────────────
export default function HeroDemo() {
  const [entry] = useState<DemoEntry>(
    () => DEMO_POOL[Math.floor(Math.random() * DEMO_POOL.length)]
  );
  const [phase, setPhase] = useState<Phase>(0);
  const [cursorPos, setCursorPos] = useState<CursorPos>({ lp: "50%", tp: "50%" });
  const [clicking, setClicking] = useState(false);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [cardH, setCardH] = useState(490);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const update = () => setScale(Math.min(1, wrapper.offsetWidth / DESIGN_WIDTH));
    const ro = new ResizeObserver(update);
    ro.observe(wrapper);
    update();
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const card = cardRef.current;
    if (card && card.offsetHeight > 0) setCardH(card.offsetHeight);
  }, [phase, scale]);

  // Stop cycling scenes while the demo is scrolled out of view, so its
  // animations (and the frame loop driving them) go idle.
  const visible = useInView(wrapperRef, { margin: "100px 0px" });

  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(
      () => setPhase((p) => (((p + 1) % 4) as Phase)),
      PHASE_MS[phase],
    );
    return () => clearTimeout(t);
  }, [phase, visible]);

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

  const isScaled = scale < 1;

  return (
    <div
      ref={wrapperRef}
      className="relative z-10 mx-auto w-full max-w-xl text-left lg:max-w-2xl"
      style={isScaled ? { height: cardH * scale } : undefined}
    >
      <div
        ref={cardRef}
        className="relative overflow-hidden rounded-2xl border border-rule bg-paper/90 shadow-2xl shadow-ink/10 backdrop-blur-xl"
        style={isScaled ? {
          width: DESIGN_WIDTH,
          position: "absolute",
          left: "50%",
          transform: `translateX(-50%) scale(${scale})`,
          transformOrigin: "top center",
        } : undefined}
      >
        <DemoCursor pos={cursorPos} clicking={clicking} />

        {/* Title bar */}
        <div className="flex items-center justify-between border-b border-rule px-4 py-3">
          <div className="flex items-center gap-1.5">
          </div>
          <span
            className="text-xs font-semibold text-muted"
            style={{ fontFamily: "var(--font-serif)", fontWeight: 400 }}
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
              {phase === 0 && <PhaseDashboard papers={entry.trackedPapers} />}
              {phase === 1 && <PhaseAddPaper doi={entry.doi} />}
              {phase === 2 && <PhaseScanning />}
              {phase === 3 && <PhaseCited citation={entry.citation} />}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Step indicators */}
        <div className="border-t border-rule px-5 py-3">
          <div className="flex items-center justify-center gap-3">
            {PHASE_LABELS.map((label, i) => (
              <button
                key={i}
                onClick={() => setPhase(i as Phase)}
                className="group flex items-center gap-1.5"
              >
                <span
                  className={`h-1.5 w-6 rounded-full transition-all duration-300 ${
                    phase === i ? "bg-ink" : "bg-ink/10"
                  }`}
                />
                <span
                  className={`text-[10px] font-medium transition-colors ${
                    phase === i ? "text-ink" : "text-muted"
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
