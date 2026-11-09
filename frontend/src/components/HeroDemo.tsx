"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  AnimatePresence,
  animate,
  motion,
  useInView,
  useMotionValue,
  useReducedMotion,
  type MotionValue,
} from "framer-motion";

/**
 * "From a DOI to your inbox": the landing page's product demo.
 *
 * Three steps of what Citey actually does, each shown with the app's own
 * styling. Step 1 plays out like a screen recording, with a mouse pointer
 * clicking through the add form. It advances on its own while visible,
 * pauses offscreen, and stops auto-advancing as soon as the visitor picks a
 * step. With reduced motion it shows each step's finished state, without
 * the pointer, and never auto-advances.
 */

// ─── Demo data pool ──────────────────────────────────────────────────────────

type DemoTrackedPaper = {
  title: string;
  year: number;
  /** Only the first tracked paper's venue is shown (on the step 1 card). */
  venue?: string;
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
        venue: "Advances in Neural Information Processing Systems",
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
        venue: "CVPR",
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
        venue: "Advances in Neural Information Processing Systems",
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
        venue: "Science",
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
        venue: "Physical Review Letters",
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
        venue: "Econometrica",
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


// The indexes the nightly check reads.
const SOURCES = ["OpenAlex", "Semantic Scholar", "OpenCitations", "Europe PMC"];

const STEPS = [
  { title: "Add a paper", body: "Paste a DOI or arXiv link. Citey fills in the rest." },
  { title: "Citey checks overnight", body: "Every tracked paper is looked up in four citation indexes." },
  { title: "The email arrives", body: "New citing papers, with authors, affiliations and a link." },
] as const;

// Step 1 is a scripted add of about 6 s, plus time to read the card.
const STEP_MS = [8400, 5200, 6800];

// ─── Step 1: add a paper ──────────────────────────────────────────────────────

// Typing delays that are uneven but the same on every run: a little slower
// after "." and "/", where a person glances back at the DOI they're copying.
function keyDelay(ch: string, i: number): number {
  const jitter = (ch.charCodeAt(0) * 37 + i * 13) % 55;
  return 34 + jitter + (ch === "." || ch === "/" ? 110 : 0);
}

const DOI_PATTERN = /^10\.\d{4,}\//;

/** An ordinary mouse pointer: an arrow, or a pointing hand over a button. */
function DemoCursor({
  x,
  y,
  opacity,
  hand,
  down,
  clicks,
}: {
  x: MotionValue<number>;
  y: MotionValue<number>;
  opacity: MotionValue<number>;
  hand: boolean;
  down: boolean;
  clicks: number;
}) {
  // (x, y) is the hotspot: the arrow's tip or the hand's fingertip.
  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none absolute left-0 top-0 z-10 select-none"
      style={{ x, y, opacity }}
    >
      {/* A faint ring where each click lands, gone in under half a second. */}
      {clicks > 0 && (
        <motion.span
          key={clicks}
          className="absolute -left-3 -top-3 h-6 w-6 rounded-full border border-ink"
          initial={{ scale: 0.4, opacity: 0.4 }}
          animate={{ scale: 1, opacity: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
        />
      )}
      <motion.div
        style={{ transformOrigin: "0 0" }}
        animate={{ scale: down ? 0.95 : 1 }}
        transition={{ duration: 0.08 }}
      >
        {hand ? (
          <svg width="20" height="23" viewBox="0 0 20 23" className="absolute -left-[9px] -top-px drop-shadow-sm">
            <path
              d="M7.5 2.75a1.75 1.75 0 0 1 3.5 0V9.4a1.55 1.55 0 0 1 3.1.3v.5a1.5 1.5 0 0 1 2.9.6V16c0 3.3-2.2 6-5.2 6h-1.6c-1.9 0-3.1-1-4.1-2.5L2.7 14.8a1.5 1.5 0 0 1 2.4-1.8l2.4 2.2Z"
              fill="#000"
              stroke="#fff"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
            <path d="M11 9.4v4.1M14.1 10.2v3.3" stroke="#fff" strokeWidth="1" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="17" height="23" viewBox="0 0 17 23" className="absolute -left-px -top-px drop-shadow-sm">
            <path
              d="M1 1v17.2l4.4-4.2 2.9 6.8 2.8-1.2-2.8-6.6h6.2Z"
              fill="#000"
              stroke="#fff"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </motion.div>
    </motion.div>
  );
}

type CursorTarget = "start" | "input" | "aside" | "button" | "away";

function AddScene({ entry, animated, play }: { entry: DemoEntry; animated: boolean; play: boolean }) {
  const paper = entry.trackedPapers[0];
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  const [typed, setTyped] = useState("");
  const [focused, setFocused] = useState(false);
  const [hover, setHover] = useState(false);
  const [down, setDown] = useState(false);
  const [clicks, setClicks] = useState(0);
  const [loading, setLoading] = useState(false);
  const [added, setAdded] = useState(false);

  const cx = useMotionValue(0);
  const cy = useMotionValue(0);
  const cursorOpacity = useMotionValue(0);
  const targetRef = useRef<CursorTarget>("start");

  // Where the pointer goes, measured from the fake controls themselves so it
  // lands on them at any width.
  const pointFor = useCallback((target: CursorTarget) => {
    const root = rootRef.current?.getBoundingClientRect();
    const input = inputRef.current?.getBoundingClientRect();
    const button = buttonRef.current?.getBoundingClientRect();
    if (!root || !input || !button) return { x: 0, y: 0 };
    const inputX = input.left - root.left + Math.min(input.width * 0.35, 120);
    const inputY = input.top - root.top + input.height * 0.55;
    const buttonX = button.left - root.left + button.width * 0.55;
    const buttonY = button.top - root.top + button.height * 0.6;
    switch (target) {
      case "start":
        return { x: root.width * 0.78, y: input.bottom - root.top + 150 };
      case "input":
        return { x: inputX, y: inputY };
      case "aside": // nudged off the text (and the hint below) while typing
        return { x: inputX + 16, y: input.bottom - root.top + 36 };
      case "button":
        return { x: buttonX, y: buttonY };
      case "away":
        return { x: Math.min(buttonX + 30, root.width - 12), y: buttonY + 110 };
    }
  }, []);

  // A real input keeps the caret in view, so show the end of a long DOI.
  useLayoutEffect(() => {
    const el = textRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [typed]);

  // Keep the pointer on its element when the panel changes width. Height is
  // ignored: it changes when the card appears, mid-glide.
  useEffect(() => {
    const root = rootRef.current;
    if (!animated || !root) return;
    let width = root.offsetWidth;
    const ro = new ResizeObserver(() => {
      if (root.offsetWidth === width) return;
      width = root.offsetWidth;
      const p = pointFor(targetRef.current);
      cx.jump(p.x);
      cy.jump(p.y);
    });
    ro.observe(root);
    return () => ro.disconnect();
  }, [animated, pointFor, cx, cy]);

  // The script. It runs on timers only, so cancelling is clearing them: a
  // wait whose timer is cleared never resolves and the script stops there.
  useEffect(() => {
    if (!animated || !play) return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const wait = (ms: number) => new Promise<void>((resolve) => void timers.push(setTimeout(resolve, ms)));

    const glide = (target: CursorTarget, seconds: number) => {
      targetRef.current = target;
      const p = pointFor(target);
      // x and y ease differently, which bends the path into a slight arc.
      animate(cx, p.x, { duration: seconds, ease: [0.45, 0, 0.25, 1] });
      animate(cy, p.y, { duration: seconds, ease: [0.3, 0.1, 0.4, 1] });
      return wait(seconds * 1000);
    };
    const click = async () => {
      setDown(true);
      setClicks((c) => c + 1);
      await wait(110);
      setDown(false);
    };

    const run = async () => {
      // Start from scratch, also when scrolled back into view part way.
      setTyped("");
      setFocused(false);
      setHover(false);
      setLoading(false);
      setAdded(false);
      const start = pointFor("start");
      targetRef.current = "start";
      cx.jump(start.x);
      cy.jump(start.y);
      animate(cursorOpacity, 1, { duration: 0.3 });

      await wait(300);
      await glide("input", 0.9);
      await wait(200);
      await click();
      setFocused(true);
      await wait(280);
      void glide("aside", 0.4);
      for (let i = 1; i <= entry.doi.length; i++) {
        await wait(keyDelay(entry.doi[i - 1], i));
        setTyped(entry.doi.slice(0, i));
      }
      await wait(400);
      await glide("button", 0.75);
      setHover(true);
      await wait(300);
      await click();
      setHover(false);
      setLoading(true);
      await wait(1100);
      setLoading(false);
      setAdded(true);
      setTyped("");
      setFocused(false);
      await wait(500);
      void glide("away", 0.9);
      animate(cursorOpacity, 0, { duration: 0.5, delay: 0.4 });
    };
    void run();

    return () => {
      timers.forEach(clearTimeout);
      cx.stop();
      cy.stop();
      cursorOpacity.jump(0);
    };
  }, [animated, play, entry.doi, pointFor, cx, cy, cursorOpacity]);

  // Without motion the scene is simply its finished state.
  const text = animated ? typed : entry.doi;
  const shownAdded = animated ? added : true;
  const enabled = text.length > 0 && !loading;
  const source = [paper.venue, paper.year].filter(Boolean).join(", ");

  return (
    <div ref={rootRef} className="relative flex flex-col gap-5">
      {/* The fake form: a picture of the real one, so hidden from assistive
          tech and never focusable. */}
      <div aria-hidden="true" className="select-none">
        <p className="mb-1.5 text-sm font-bold text-ink">DOI or arXiv link</p>
        <div className="flex gap-2">
          <div
            ref={inputRef}
            className={`flex h-[2.625rem] min-w-0 flex-1 items-center rounded-lg border bg-sheet px-4 text-sm text-ink transition-[border-color,box-shadow] duration-150 ${
              focused ? "border-ink ring-1 ring-ink/20" : "border-control"
            } ${loading ? "opacity-60" : ""}`}
          >
            <div ref={textRef} className="flex min-w-0 flex-1 items-center overflow-hidden whitespace-nowrap">
              {text ? (
                <span>{text}</span>
              ) : (
                !focused && <span className="truncate text-muted">10.xxxx/… or arxiv.org/abs/…</span>
              )}
              {focused && !loading && <span className="ml-px inline-block h-4 w-px shrink-0 animate-pulse bg-ink" />}
            </div>
          </div>
          <span
            ref={buttonRef}
            className={`flex min-w-[7.5rem] shrink-0 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-paper shadow transition-[background-color,opacity,transform] duration-150 ${
              hover ? "bg-ink-soft" : "bg-ink"
            } ${enabled || loading ? "opacity-100" : "opacity-50"} ${hover && down ? "scale-[0.97]" : "scale-100"}`}
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
                Adding…
              </>
            ) : (
              "Add paper"
            )}
          </span>
        </div>
        {/* The real form's hint line, then what Citey is doing. */}
        <p className={`mt-1.5 h-4 text-xs ${loading ? "text-muted" : "text-ok"}`}>
          {loading
            ? "Looking up the title, authors and venue…"
            : DOI_PATTERN.test(text) && !shownAdded
              ? "Detected: DOI"
              : ""}
        </p>
      </div>

      <AnimatePresence>
        {shownAdded && (
          <motion.div
            initial={animated ? { opacity: 0, y: 6 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
          >
            {/* Set like the dashboard's tracked-paper card. */}
            <article className="border-y border-rule py-4">
              <h3 className="mb-1.5 font-serif text-lg font-semibold leading-snug text-ink">{paper.title}</h3>
              <p className="text-sm leading-relaxed text-muted">
                {paper.authors}. <i>{source}</i>.
              </p>
              <p className="mt-1 truncate font-mono text-xs text-muted underline decoration-rule underline-offset-2">
                doi:{entry.doi}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className="text-ink">Cited by {paper.citedBy}</span>
                <span className="text-muted">Not checked yet</span>
              </div>
            </article>
            <p className="mt-3 text-sm text-ink">Added. Citey will check it tonight.</p>
          </motion.div>
        )}
      </AnimatePresence>

      {animated && <DemoCursor x={cx} y={cy} opacity={cursorOpacity} hand={hover} down={down} clicks={clicks} />}
    </div>
  );
}

// ─── Step 2: the overnight check ──────────────────────────────────────────────
function CheckScene({ entry, animate, hitIndex }: { entry: DemoEntry; animate: boolean; hitIndex: number }) {
  const [count, setShown] = useState(0);
  const shown = animate ? count : SOURCES.length;

  useEffect(() => {
    if (!animate) return;
    const t = setInterval(() => setShown((n) => (n >= SOURCES.length ? n : n + 1)), 480);
    return () => clearInterval(t);
  }, [animate]);

  const finished = shown >= SOURCES.length;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">
        Checking <i className="font-serif text-ink">{entry.trackedPapers[0].title}</i> at midnight
      </p>
      <ul className="divide-y divide-rule border-y border-rule">
        {SOURCES.map((s, i) => {
          const visible = i < shown;
          const hit = i === hitIndex;
          return (
            <li key={s} className="flex items-center justify-between py-2 text-sm">
              <span className={visible ? "text-ink" : "text-muted"}>{s}</span>
              {visible ? (
                hit ? (
                  <span className="highlight font-bold text-ink">1 new citation</span>
                ) : (
                  <span className="text-muted">Nothing new</span>
                )
              ) : (
                <span className="text-muted/60" aria-hidden="true">…</span>
              )}
            </li>
          );
        })}
      </ul>
      <p className={`text-sm transition-opacity duration-500 ${finished ? "opacity-100" : "opacity-0"}`}>
        <span className="text-ink">Found 1 new citation.</span>{" "}
        <span className="text-muted">A paper found in both is reported once.</span>
      </p>
    </div>
  );
}

// ─── Step 3: the email ────────────────────────────────────────────────────────
function EmailScene({ entry }: { entry: DemoEntry }) {
  const c = entry.citation;
  return (
    <div className="flex flex-col gap-4">
      <div className="border-b border-rule pb-3 text-sm">
        <div className="flex items-baseline justify-between gap-3">
          <p className="font-bold text-ink">Citey</p>
          <p className="shrink-0 text-muted">7:02 am</p>
        </div>
        <p className="text-ink">New citation of <i className="font-serif">{c.yourPaper}</i></p>
        <p className="text-muted">to you@university.edu</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <p className="text-sm">
          <span className="highlight font-bold text-ink">New citation</span>
          <span className="ml-2 text-muted">{c.citingDate}</span>
        </p>
        <h4 className="font-serif text-[17px] font-semibold leading-snug text-ink">{c.citingTitle}</h4>
        <p className="text-sm text-muted">{c.citingAuthors}</p>
        <p className="text-sm text-muted">{c.affiliations.join("; ")}</p>
        <p className="mt-1 text-sm text-ink">
          Cites <i className="font-serif">{c.yourPaper}</i>
        </p>
        <p className="mt-2 text-sm text-ink underline decoration-rule underline-offset-4">Read the citing paper</p>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function HeroDemo() {
  const prefersReducedMotion = useReducedMotion();
  // Read the preference only after mount, so the server render and the first
  // client render agree (the server can't know it).
  const [mounted, setMounted] = useState(false);
  const reduceMotion = mounted && prefersReducedMotion;
  const rootRef = useRef<HTMLDivElement>(null);
  const visible = useInView(rootRef, { margin: "-80px 0px" });
  const [entryIndex, setEntryIndex] = useState(0);
  const [step, setStep] = useState(0);
  const [autoplay, setAutoplay] = useState(true);
  const [runId, setRunId] = useState(0); // remounts scenes so animations replay

  // Pick a sample after mount (avoids a server/client mismatch).
  useEffect(() => {
    setEntryIndex(Math.floor(Math.random() * DEMO_POOL.length));
    setMounted(true);
  }, []);

  const playing = autoplay && !reduceMotion && visible;

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      setStep((s) => {
        const next = (s + 1) % STEPS.length;
        if (next === 0) setEntryIndex((e) => (e + 1) % DEMO_POOL.length);
        return next;
      });
      setRunId((r) => r + 1);
    }, STEP_MS[step]);
    return () => clearTimeout(t);
  }, [playing, step]);

  const entry = DEMO_POOL[entryIndex];
  const hitIndex = entryIndex % SOURCES.length; // which index finds the citation
  const animateScenes = !reduceMotion;

  const choose = (i: number) => {
    setAutoplay(false);
    setStep(i);
    setRunId((r) => r + 1);
  };

  return (
    <div ref={rootRef} className="grid grid-cols-1 gap-10 lg:grid-cols-[5fr_7fr] lg:items-start">
      <ol className="flex flex-col" aria-label="How Citey works">
        {STEPS.map((s, i) => {
          const active = i === step;
          return (
            <li key={s.title} className="border-t border-rule last:border-b">
              <button
                type="button"
                onClick={() => choose(i)}
                aria-current={active ? "step" : undefined}
                className="group relative flex w-full gap-4 py-5 text-left"
              >
                <span
                  className={`font-serif text-3xl font-light leading-none tabular-nums ${active ? "text-ink" : "text-rule group-hover:text-muted"}`}
                  aria-hidden="true"
                >
                  {i + 1}
                </span>
                <span>
                  <span className={`block text-lg ${active ? "font-bold text-ink" : "text-muted group-hover:text-ink"}`}>
                    {s.title}
                  </span>
                  <span className={`mt-1 block text-sm leading-relaxed text-muted`}>
                    {s.body}
                  </span>
                </span>
                {/* progress of the current step while autoplaying */}
                {active && playing && (
                  <motion.span
                    key={`${runId}-bar`}
                    className="absolute -top-px left-0 h-0.5 bg-ink"
                    initial={{ width: "0%" }}
                    animate={{ width: "100%" }}
                    transition={{ duration: STEP_MS[i] / 1000, ease: "linear" }}
                    aria-hidden="true"
                  />
                )}
              </button>
            </li>
          );
        })}
        {!autoplay && !reduceMotion && (
          <li className="pt-3">
            <button
              type="button"
              onClick={() => { setAutoplay(true); setRunId((r) => r + 1); }}
              className="text-sm text-muted underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink"
            >
              Play the steps automatically
            </button>
          </li>
        )}
      </ol>

      <div
        className="relative min-h-[27rem] min-w-0 rounded-lg border border-rule bg-sheet p-6 shadow-[0_1px_0_rgba(20,33,61,0.04),0_12px_32px_-12px_rgba(20,33,61,0.18)] sm:p-8"
        role="region"
        aria-label={`Step ${step + 1}: ${STEPS[step].title}`}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={`${step}-${runId}-${entryIndex}`}
            initial={animateScenes ? { opacity: 0, y: 6 } : false}
            animate={{ opacity: 1, y: 0 }}
            exit={animateScenes ? { opacity: 0, y: -6 } : { opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            {step === 0 && <AddScene entry={entry} animated={animateScenes} play={visible} />}
            {step === 1 && <CheckScene entry={entry} animate={animateScenes} hitIndex={hitIndex} />}
            {step === 2 && <EmailScene entry={entry} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
