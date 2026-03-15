"use client";

import { useEffect, useRef } from "react";

interface OrbProps {
  className?: string;
}

export default function Orb({ className = "" }: OrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf: number;
    let t = 0;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    /** Draw a softly wobbling blob outline */
    const drawBlob = (
      cx: number,
      cy: number,
      r: number,
      pts: number,
      wobble: number,
      phase: number,
      yScale = 0.78
    ) => {
      ctx.beginPath();
      for (let i = 0; i <= pts; i++) {
        const angle = (i / pts) * Math.PI * 2;
        const rr =
          r +
          Math.sin(i * 3.7 + phase) * wobble +
          Math.cos(i * 2.3 + phase * 0.6) * wobble * 0.55 +
          Math.sin(i * 1.4 + phase * 1.3) * wobble * 0.3;
        const x = cx + Math.cos(angle) * rr;
        const y = cy + Math.sin(angle) * rr * yScale;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
    };

    const draw = () => {
      t += 0.007;
      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      // Primary orb — drifts slowly around the upper centre
      const cx1 = w * 0.5 + Math.sin(t * 0.38) * w * 0.045;
      const cy1 = h * 0.42 + Math.cos(t * 0.27) * h * 0.05;
      const r1 = Math.min(w, h) * 0.38;

      drawBlob(cx1, cy1, r1, 72, r1 * 0.09, t);
      const g1 = ctx.createRadialGradient(
        cx1 - r1 * 0.22, cy1 - r1 * 0.22, 0,
        cx1, cy1, r1 * 1.15
      );
      g1.addColorStop(0,    "rgba(255,255,255,0.42)");
      g1.addColorStop(0.28, "rgba(230,230,230,0.22)");
      g1.addColorStop(0.55, "rgba(160,160,160,0.10)");
      g1.addColorStop(1,    "rgba(0,0,0,0)");
      ctx.fillStyle = g1;
      ctx.fill();

      // Secondary blob — counter-phase drift for depth
      const cx2 = w * 0.5 + Math.cos(t * 0.52 + 1.8) * w * 0.055;
      const cy2 = h * 0.44 + Math.sin(t * 0.41 + 1.8) * h * 0.045;
      const r2 = r1 * 0.62;

      drawBlob(cx2, cy2, r2, 64, r2 * 0.08, t * 1.25 + 2.1);
      const g2 = ctx.createRadialGradient(cx2, cy2, 0, cx2, cy2, r2 * 1.1);
      g2.addColorStop(0,    "rgba(255,255,255,0.28)");
      g2.addColorStop(0.45, "rgba(190,190,190,0.12)");
      g2.addColorStop(1,    "rgba(0,0,0,0)");
      ctx.fillStyle = g2;
      ctx.fill();

      // Bright highlight core — tiny inner glow that shifts
      const hlX = cx1 - r1 * 0.18 + Math.sin(t * 0.9) * r1 * 0.06;
      const hlY = cy1 - r1 * 0.22 + Math.cos(t * 0.7) * r1 * 0.06;
      const hlR = r1 * 0.26;
      const ghl = ctx.createRadialGradient(hlX, hlY, 0, hlX, hlY, hlR);
      ghl.addColorStop(0, "rgba(255,255,255,0.55)");
      ghl.addColorStop(1, "rgba(255,255,255,0)");
      ctx.beginPath();
      ctx.arc(hlX, hlY, hlR, 0, Math.PI * 2);
      ctx.fillStyle = ghl;
      ctx.fill();

      raf = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <>
      {/* Blurred canvas — creates the soft glowing orb */}
      <div
        className={`pointer-events-none absolute inset-0 ${className}`}
        aria-hidden="true"
        style={{ filter: "blur(30px)" }}
      >
        <canvas ref={canvasRef} className="h-full w-full" />
      </div>
      {/* Bottom gradient — fades the orb into page content; not blurred */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-gray-950" />
    </>
  );
}
