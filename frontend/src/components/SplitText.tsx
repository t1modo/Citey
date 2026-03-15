"use client";

import { useRef } from "react";
import { motion, useInView } from "framer-motion";

interface SplitTextProps {
  text: string;
  className?: string;
  /** Delay between each character in seconds */
  charDelay?: number;
  /** Animation duration per character in seconds */
  duration?: number;
}

export default function SplitText({
  text,
  className = "",
  charDelay = 0.028,
  duration = 0.5,
}: SplitTextProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px 0px" });

  const words = text.split(" ");

  // Pre-compute the global char start index for each word so stagger is
  // consistent regardless of word boundaries.
  const wordStarts = words.reduce<number[]>((acc, _, i) => {
    if (i === 0) return [0];
    return [...acc, acc[i - 1] + words[i - 1].length];
  }, []);

  return (
    <span ref={ref} className={`inline-block ${className}`} aria-label={text}>
      {words.map((word, wi) => (
        <span
          key={wi}
          className="inline-block"
          style={{ marginRight: wi < words.length - 1 ? "0.28em" : undefined }}
        >
          {word.split("").map((char, ci) => {
            const globalIdx = wordStarts[wi] + ci;
            return (
              /* overflow-hidden creates the "rising from below" mask effect */
              <span key={ci} className="inline-block overflow-hidden leading-[1.15]">
                <motion.span
                  className="inline-block"
                  initial={{ y: "110%", opacity: 0 }}
                  animate={
                    inView
                      ? { y: "0%", opacity: 1 }
                      : { y: "110%", opacity: 0 }
                  }
                  transition={{
                    duration,
                    delay: globalIdx * charDelay,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                >
                  {char}
                </motion.span>
              </span>
            );
          })}
        </span>
      ))}
    </span>
  );
}
