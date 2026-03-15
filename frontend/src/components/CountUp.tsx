"use client";

import { useEffect, useRef, useState } from "react";

interface CountUpProps {
  end: number;
  duration?: number;
  className?: string;
}

export default function CountUp({
  end,
  duration = 1.4,
  className = "",
}: CountUpProps) {
  const [count, setCount] = useState(0);
  const elRef = useRef<HTMLSpanElement>(null);
  const started = useRef(false);
  const rafRef = useRef<number | null>(null);

  // Reset if the target value changes (e.g. after data loads)
  useEffect(() => {
    started.current = false;
    setCount(0);
  }, [end]);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          const startTime = performance.now();

          const tick = (now: number) => {
            const t = Math.min((now - startTime) / (duration * 1000), 1);
            // Ease-out cubic
            const eased = 1 - Math.pow(1 - t, 3);
            setCount(Math.round(eased * end));
            if (t < 1) {
              rafRef.current = requestAnimationFrame(tick);
            }
          };

          rafRef.current = requestAnimationFrame(tick);
        }
      },
      { threshold: 0.4 }
    );

    observer.observe(el);

    return () => {
      observer.disconnect();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [end, duration]);

  return (
    <span ref={elRef} className={className}>
      {count.toLocaleString()}
    </span>
  );
}
