"use client";

import { RefObject, useEffect, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";

/**
 * Decide whether an element should play a reveal-on-scroll animation.
 *
 * Content renders visible on the server and on first paint, so it never
 * depends on JavaScript to appear (good for first paint, crawlers and
 * slow devices). After mount, only elements that start below the fold are
 * tucked away and then revealed when scrolled into view. Elements already
 * on screen, and visitors who prefer reduced motion, are left alone.
 *
 * Returns `hidden`: true while the element should be in its pre-reveal state.
 */
export function useScrollReveal(
  ref: RefObject<Element | null>,
  margin: `${number}px ${number}px` = "-70px 0px",
): boolean {
  const reduceMotion = useReducedMotion();
  const inView = useInView(ref, { once: true, margin });
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (reduceMotion || !ref.current) return;
    if (ref.current.getBoundingClientRect().top > window.innerHeight) {
      setArmed(true);
    }
  }, [reduceMotion, ref]);

  return armed && !inView;
}
