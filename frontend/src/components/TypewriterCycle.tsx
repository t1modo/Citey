"use client";

import { useEffect, useState } from "react";

interface TypewriterCycleProps {
  /** List of strings to cycle through */
  phrases: string[];
  /** ms per character typed */
  typeSpeed?: number;
  /** ms per character deleted */
  deleteSpeed?: number;
  /** ms to pause after fully typed */
  pauseAfterType?: number;
  /** ms to pause after fully deleted */
  pauseAfterDelete?: number;
  className?: string;
}

export default function TypewriterCycle({
  phrases,
  typeSpeed = 45,
  deleteSpeed = 22,
  pauseAfterType = 1600,
  pauseAfterDelete = 400,
  className = "",
}: TypewriterCycleProps) {
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [displayed, setDisplayed] = useState("");
  const [phase, setPhase] = useState<"typing" | "pausing" | "deleting" | "waiting">("typing");

  useEffect(() => {
    const target = phrases[phraseIdx];

    if (phase === "typing") {
      if (displayed.length < target.length) {
        const t = setTimeout(
          () => setDisplayed(target.slice(0, displayed.length + 1)),
          typeSpeed
        );
        return () => clearTimeout(t);
      } else {
        const t = setTimeout(() => setPhase("deleting"), pauseAfterType);
        return () => clearTimeout(t);
      }
    }

    if (phase === "deleting") {
      if (displayed.length > 0) {
        const t = setTimeout(
          () => setDisplayed(displayed.slice(0, -1)),
          deleteSpeed
        );
        return () => clearTimeout(t);
      } else {
        const t = setTimeout(() => {
          setPhraseIdx((i) => (i + 1) % phrases.length);
          setPhase("typing");
        }, pauseAfterDelete);
        return () => clearTimeout(t);
      }
    }
  }, [displayed, phase, phraseIdx, phrases, typeSpeed, deleteSpeed, pauseAfterType, pauseAfterDelete]);

  return (
    <span className={className}>
      {displayed}
      <span className="ml-px inline-block w-[2px] animate-pulse rounded-sm bg-current align-middle opacity-75" style={{ height: "1em" }} />
    </span>
  );
}
