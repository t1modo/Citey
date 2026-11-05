"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";

/**
 * "From a DOI to your inbox": the landing page's product demo.
 *
 * Three steps of what Citey actually does, each shown with the app's own
 * styling. It advances on its own while visible, pauses offscreen, and
 * stops auto-advancing as soon as the visitor picks a step. With reduced
 * motion it shows each step's finished state and never auto-advances.
 */

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


// Seven indexes, in the order Citey reports them.
const SOURCES = ["OpenAlex", "Semantic Scholar", "Crossref", "PubMed", "NASA ADS", "INSPIRE-HEP", "DBLP"];

const STEPS = [
  { title: "Add a paper", body: "Paste a DOI or arXiv link. Citey fills in the rest." },
  { title: "Citey checks overnight", body: "Every tracked paper is looked up in seven citation indexes." },
  { title: "The email arrives", body: "New citing papers, with authors, affiliations and a link." },
] as const;

const STEP_MS = [6200, 5200, 6800];

// ─── Step 1: add a paper ──────────────────────────────────────────────────────
function AddScene({ entry, animate }: { entry: DemoEntry; animate: boolean }) {
  const paper = entry.trackedPapers[0];
  const [typed, setTyped] = useState(animate ? "" : entry.doi);
  const done = typed.length === entry.doi.length;

  useEffect(() => {
    if (!animate) return;
    let i = 0;
    const start = setTimeout(function tick() {
      i += 1;
      setTyped(entry.doi.slice(0, i));
      if (i < entry.doi.length) timer = setTimeout(tick, 55);
    }, 500);
    let timer = start;
    return () => clearTimeout(timer);
  }, [animate, entry.doi]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="mb-1.5 text-sm font-bold text-ink">DOI or arXiv link</p>
        <div className="flex gap-2">
          <div
            className="flex min-w-0 flex-1 items-center rounded-md border border-control bg-paper px-3 py-2 font-mono text-sm text-ink"
          >
            <span className="truncate">{typed}</span>
            {!done && <span className="ml-px inline-block h-4 w-px animate-pulse bg-ink" aria-hidden="true" />}
          </div>
          <span
            className={`shrink-0 rounded-md px-4 py-2 text-sm font-bold transition-colors ${
              done ? "bg-ink text-paper" : "bg-ink/10 text-muted"
            }`}
          >
            Add paper
          </span>
        </div>
      </div>

      <AnimatePresence>
        {done && (
          <motion.article
            initial={animate ? { opacity: 0, y: 8 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: animate ? 0.5 : 0, duration: 0.4 }}
            className="border-y border-rule py-4"
          >
            <h4 className="mb-1 font-serif text-[17px] font-semibold leading-snug text-ink">{paper.title}</h4>
            <p className="text-sm text-muted">
              {paper.authors}. <i>{paper.year}</i>.
            </p>
            <p className="mt-2 text-sm text-ink">Added. Citey will check it tonight.</p>
          </motion.article>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Step 2: the overnight check ──────────────────────────────────────────────
function CheckScene({ entry, animate, hitIndex }: { entry: DemoEntry; animate: boolean; hitIndex: number }) {
  const [shown, setShown] = useState(animate ? 0 : SOURCES.length);

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
        <span className="text-muted">Duplicates across indexes are merged, so you hear about it once.</span>
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
  const reduceMotion = useReducedMotion();
  const rootRef = useRef<HTMLDivElement>(null);
  const visible = useInView(rootRef, { margin: "-80px 0px" });
  const [entryIndex, setEntryIndex] = useState(0);
  const [step, setStep] = useState(0);
  const [autoplay, setAutoplay] = useState(true);
  const [runId, setRunId] = useState(0); // remounts scenes so animations replay

  // Pick a sample after mount (avoids a server/client mismatch).
  useEffect(() => setEntryIndex(Math.floor(Math.random() * DEMO_POOL.length)), []);

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
  const hitIndex = (entryIndex % 3) + 1; // which index finds the citation
  const animateScenes = !reduceMotion;

  const choose = (i: number) => {
    setAutoplay(false);
    setStep(i);
    setRunId((r) => r + 1);
  };

  return (
    <div ref={rootRef} className="grid gap-10 lg:grid-cols-[5fr_7fr] lg:items-start">
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
        className="relative min-h-[27rem] rounded-lg border border-rule bg-sheet p-6 shadow-[0_1px_0_rgba(20,33,61,0.04),0_12px_32px_-12px_rgba(20,33,61,0.18)] sm:p-8"
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
            {step === 0 && <AddScene entry={entry} animate={animateScenes} />}
            {step === 1 && <CheckScene entry={entry} animate={animateScenes} hitIndex={hitIndex} />}
            {step === 2 && <EmailScene entry={entry} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
