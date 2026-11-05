"use client";

import { useEffect, useRef } from "react";

interface GalaxyProps {
  className?: string;
  speedMultiplier?: number;
}

interface Star {
  angle: number;
  distance: number;
  size: number;
  opacity: number;
  speed: number;
  twinkleOffset: number;
  twinkleSpeed: number;
}

const NUM_STARS = 320;
const BACKGROUND = "#0c0d10";
const GLOW_SPRITE_SIZE = 64;

/** Soft white glow drawn once, then stamped with drawImage each frame. */
function makeGlowSprite(): HTMLCanvasElement {
  const sprite = document.createElement("canvas");
  sprite.width = sprite.height = GLOW_SPRITE_SIZE;
  const g = sprite.getContext("2d")!;
  const r = GLOW_SPRITE_SIZE / 2;
  const grad = g.createRadialGradient(r, r, 0, r, r, r);
  grad.addColorStop(0, "rgba(255,255,255,0.18)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, GLOW_SPRITE_SIZE, GLOW_SPRITE_SIZE);
  return sprite;
}

/**
 * Slowly rotating star field used as a page background.
 *
 * Performance notes: rendering pauses while the tab is hidden, honours
 * prefers-reduced-motion (one static frame), scales for high-DPI screens
 * (capped at 2x), and reuses a pre-rendered glow sprite rather than
 * building a radial gradient per star per frame.
 */
export default function Galaxy({ className = "", speedMultiplier = 1 }: GalaxyProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const glow = makeGlowSprite();
    let raf = 0;
    let t = 0;
    let width = 0;
    let height = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.offsetWidth;
      height = canvas.offsetHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();

    const radius = Math.max(width, height) * 0.65;
    const stars: Star[] = Array.from({ length: NUM_STARS }, () => {
      const distance = Math.pow(Math.random(), 0.6) * radius + 8;
      return {
        angle: Math.random() * Math.PI * 2,
        distance,
        size: Math.random() * 1.8 + 0.3,
        opacity: Math.random() * 0.5 + 0.4,
        speed: ((0.00012 + Math.random() * 0.00008) * speedMultiplier) / Math.sqrt(distance / 80),
        twinkleOffset: Math.random() * Math.PI * 2,
        twinkleSpeed: Math.random() * 0.018 + 0.004,
      };
    });

    const render = (advance: boolean) => {
      if (advance) t++;
      const cx = width / 2;
      const cy = height / 2;

      ctx.fillStyle = BACKGROUND;
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#ffffff";

      for (const s of stars) {
        if (advance) s.angle += s.speed;
        const x = cx + Math.cos(s.angle) * s.distance;
        const y = cy + Math.sin(s.angle) * s.distance * 0.38;
        if (x < -10 || x > width + 10 || y < -10 || y > height + 10) continue;

        const alpha = s.opacity * (Math.sin(t * s.twinkleSpeed + s.twinkleOffset) * 0.18 + 0.82);
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.arc(x, y, s.size, 0, Math.PI * 2);
        ctx.fill();

        if (s.size > 1.1) {
          const r = s.size * 3.5;
          ctx.drawImage(glow, x - r, y - r, r * 2, r * 2);
        }
      }
      ctx.globalAlpha = 1;
    };

    const loop = () => {
      render(true);
      raf = requestAnimationFrame(loop);
    };

    const start = () => {
      cancelAnimationFrame(raf);
      if (motionQuery.matches) {
        render(false); // static frame only
      } else if (document.visibilityState === "visible") {
        raf = requestAnimationFrame(loop);
      }
    };
    const stop = () => cancelAnimationFrame(raf);

    const onVisibility = () => (document.visibilityState === "visible" ? start() : stop());
    const ro = new ResizeObserver(() => {
      resize();
      if (motionQuery.matches) render(false);
    });

    ro.observe(canvas);
    document.addEventListener("visibilitychange", onVisibility);
    motionQuery.addEventListener("change", start);
    start();

    return () => {
      stop();
      ro.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      motionQuery.removeEventListener("change", start);
    };
  }, [speedMultiplier]);

  return (
    <canvas
      ref={canvasRef}
      className={`pointer-events-none fixed inset-0 -z-10 h-screen w-screen ${className}`}
      aria-hidden="true"
    />
  );
}
