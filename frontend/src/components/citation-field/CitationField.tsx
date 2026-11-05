"use client";

import { useEffect, useRef, useState } from "react";
import shader from "./citationField.wgsl";

/**
 * Hero background: a live citation timeline rendered with vgpu (WebGPU).
 *
 * Columns are publication years. Every few seconds a newer paper cites
 * "your paper" (the ringed node): an arc draws across, a pulse rides it and
 * the node flares. Everything is computed in citationField.wgsl from time.
 *
 * Falls back to a poster frame of the same shader when WebGPU is missing,
 * the visitor prefers reduced motion, or the GPU fails. Rendering pauses
 * while the hero is offscreen or the tab is hidden.
 */

const COLS = 8;
const FOCAL = 1;
const FOCUS_Y = 0.54; // uv y of the focal node (0.5 + 0.04 in the shader)
// Start mid-sequence so a citation is already in flight on first paint.
const TIME_OFFSET = 11.2;

type Layout = { x0: number; step: number; intensity: number };

function layoutFor(width: number, height: number): Layout {
  return width / height >= 1.2
    ? { x0: 0.44, step: 0.075, intensity: 1 } // beside the headline
    : { x0: 0.1, step: 0.115, intensity: 0.45 }; // behind the text on phones
}

export default function CitationField({ className = "" }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [mode, setMode] = useState<"pending" | "gpu" | "poster">("pending");
  const [layout, setLayout] = useState<Layout>({ x0: 0.44, step: 0.075, intensity: 1 });

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion || !("gpu" in navigator)) {
      setMode("poster");
      return;
    }

    let cancelled = false;
    let cleanup = () => {};

    (async () => {
      try {
        const { init, surface, effect, clock, frameLoop } = await import("vgpu");
        const gpu = await init();
        if (cancelled) {
          gpu.dispose();
          return;
        }

        const target = surface(gpu, canvas, { dpr: [1, 1.5], clearColor: [0.933, 0.945, 0.957, 1] });
        const fx = effect(gpu, shader);

        const applySize = () => {
          const [w, h] = target.size;
          const l = layoutFor(w, h);
          fx.set({
            params: {
              time: TIME_OFFSET,
              aspect: w / h,
              px: 1 / h,
              intensity: l.intensity,
              columns: [l.x0, l.step],
            },
          });
          setLayout(l);
        };
        applySize();
        const offResize = target.onResize(applySize);

        const time = clock(gpu);
        let loop: { stop(): void } | null = null;
        const start = () => {
          if (loop) return;
          loop = frameLoop(gpu, (frame) => {
            fx.set({ params: { time: TIME_OFFSET + time.time } });
            frame.pass(target, fx);
          });
        };
        const stop = () => {
          loop?.stop();
          loop = null;
        };

        let onScreen = true;
        const sync = () =>
          onScreen && document.visibilityState === "visible" ? start() : stop();
        const io = new IntersectionObserver(([entry]) => {
          onScreen = entry.isIntersecting;
          sync();
        });
        io.observe(container);
        document.addEventListener("visibilitychange", sync);

        // Any GPU failure (pipeline compile, device loss) falls back to the
        // poster instead of leaving an empty canvas.
        const fail = (reason: unknown) => {
          if (cancelled) return;
          console.warn("CitationField: falling back to poster", reason, (reason as { cause?: unknown })?.cause);
          stop();
          setMode("poster");
        };
        gpu.onError(fail);
        gpu.lost.then(fail);

        sync();
        setMode("gpu");

        cleanup = () => {
          stop();
          io.disconnect();
          document.removeEventListener("visibilitychange", sync);
          offResize();
          gpu.dispose();
        };
      } catch (err) {
        if (!cancelled) {
          console.warn("CitationField: WebGPU unavailable, showing poster", err);
          setMode("poster");
        }
      }
    })();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, []);

  const year = new Date().getFullYear();

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
    >
      {mode === "poster" && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src="/citation-field.webp"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-right"
        />
      )}
      <canvas
        ref={canvasRef}
        className={`absolute inset-0 h-full w-full transition-opacity duration-700 ${
          mode === "gpu" ? "opacity-100" : "opacity-0"
        }`}
      />

      {mode === "gpu" && (
        <>
          {/* year axis, aligned with the shader's columns */}
          {Array.from({ length: COLS }, (_, c) => (
            <span
              key={c}
              className="absolute bottom-6 -translate-x-1/2 text-xs tabular-nums text-muted"
              style={{ left: `${(layout.x0 + c * layout.step) * 100}%`, opacity: layout.intensity }}
            >
              {year - (COLS - 1 - c)}
            </span>
          ))}
          <span
            className="absolute -translate-x-1/2 translate-y-6 whitespace-nowrap font-serif text-sm italic text-ink"
            style={{
              left: `${(layout.x0 + FOCAL * layout.step) * 100}%`,
              top: `${FOCUS_Y * 100}%`,
              opacity: layout.intensity,
            }}
          >
            Your paper
          </span>
        </>
      )}
    </div>
  );
}
