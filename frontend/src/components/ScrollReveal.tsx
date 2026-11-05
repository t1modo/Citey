"use client";

import { useRef } from "react";
import { motion } from "framer-motion";
import { useScrollReveal } from "@/hooks/useScrollReveal";

interface ScrollRevealProps {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  duration?: number;
  /** Distance in px the element travels before settling */
  distance?: number;
}

export default function ScrollReveal({
  children,
  className = "",
  delay = 0,
  duration = 0.65,
  distance = 36,
}: ScrollRevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const hidden = useScrollReveal(ref);

  return (
    <motion.div
      ref={ref}
      className={className}
      // initial={false}: render in the visible state on the server and on
      // first paint; useScrollReveal only hides content that starts offscreen.
      initial={false}
      animate={hidden ? { opacity: 0, y: distance } : { opacity: 1, y: 0 }}
      transition={hidden ? { duration: 0 } : { duration, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
