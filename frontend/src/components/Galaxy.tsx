"use client";

import { useEffect, useRef } from "react";

interface GalaxyProps {
  className?: string;
  speedMultiplier?: number;
}

export default function Galaxy({ className = "", speedMultiplier = 1 }: GalaxyProps) {
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
    const stars: Star[] = Array.from({ length: NUM_STARS }, () => {
      const distance =
        Math.pow(Math.random(), 0.6) *
          Math.max(canvas.width, canvas.height) * 0.65 +
        8;
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

    let t = 0;

    const draw = () => {
      t++;
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#030712";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (const s of stars) {
        s.angle += s.speed;
        const x = cx + Math.cos(s.angle) * s.distance;
        const y = cy + Math.sin(s.angle) * s.distance * 0.38;

        const twinkle =
          Math.sin(t * s.twinkleSpeed + s.twinkleOffset) * 0.18 + 0.82;
        const alpha = s.opacity * twinkle;

        ctx.beginPath();
        ctx.arc(x, y, s.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        ctx.fill();

        if (s.size > 1.1) {
          const g = ctx.createRadialGradient(x, y, 0, x, y, s.size * 3.5);
          g.addColorStop(0, `rgba(255, 255, 255, ${alpha * 0.18})`);
          g.addColorStop(1, "rgba(0, 0, 0, 0)");
          ctx.beginPath();
          ctx.arc(x, y, s.size * 3.5, 0, Math.PI * 2);
          ctx.fillStyle = g;
          ctx.fill();
        }
      }

      raf = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`pointer-events-none absolute inset-0 h-full w-full ${className}`}
      aria-hidden="true"
    />
  );
}
