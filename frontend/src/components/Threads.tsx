"use client";

import { useEffect, useRef } from "react";

interface ThreadsProps {
  className?: string;
}

export default function Threads({ className = "" }: ThreadsProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf: number;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    interface Thread {
      baseY: number;
      amplitude: number;
      frequency: number;
      speed: number;
      phase: number;
      opacity: number;
      width: number;
    }

    const NUM_THREADS = 14;
    const SEGMENTS = 90;

    const makeThreads = (): Thread[] =>
      Array.from({ length: NUM_THREADS }, (_, i) => ({
        baseY:
          (canvas.height / NUM_THREADS) * i +
          (Math.random() - 0.5) * (canvas.height / NUM_THREADS) * 0.8,
        amplitude: 18 + Math.random() * 52,
        frequency: 1.2 + Math.random() * 2.4,
        speed: 0.0025 + Math.random() * 0.0035,
        phase: Math.random() * Math.PI * 2,
        opacity: 0.04 + Math.random() * 0.09,
        width: 0.3 + Math.random() * 0.85,
      }));

    let threads = makeThreads();

    // Rebuild threads on resize so they fill the new canvas dimensions.
    const roWithRebuild = new ResizeObserver(() => {
      resize();
      threads = makeThreads();
    });
    roWithRebuild.observe(canvas);
    ro.disconnect(); // replace the plain resize observer

    let t = 0;

    const draw = () => {
      t += 1;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const thread of threads) {
        // Sample points along the thread.
        const pts: [number, number][] = Array.from(
          { length: SEGMENTS + 1 },
          (_, i) => {
            const x = (canvas.width / SEGMENTS) * i;
            const y =
              thread.baseY +
              thread.amplitude *
                Math.sin(
                  (i / SEGMENTS) * thread.frequency * Math.PI * 2 +
                    t * thread.speed +
                    thread.phase
                );
            return [x, y];
          }
        );

        // Draw as a smooth quadratic-bezier chain.
        ctx.beginPath();
        ctx.lineWidth = thread.width;
        ctx.strokeStyle = `rgba(255, 255, 255, ${thread.opacity})`;
        ctx.moveTo(pts[0][0], pts[0][1]);

        for (let i = 1; i < pts.length - 1; i++) {
          const mx = (pts[i][0] + pts[i + 1][0]) / 2;
          const my = (pts[i][1] + pts[i + 1][1]) / 2;
          ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
        }
        ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
        ctx.stroke();
      }

      raf = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(raf);
      roWithRebuild.disconnect();
    };
  }, []);

  return (
    <>
      <canvas
        ref={canvasRef}
        className={`pointer-events-none absolute inset-0 h-full w-full ${className}`}
        aria-hidden="true"
      />
      {/* Fade into page content below */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-gray-950" />
    </>
  );
}
