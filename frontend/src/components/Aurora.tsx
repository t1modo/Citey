"use client";

import { useRef, useEffect } from "react";

interface AuroraProps {
  className?: string;
}

export default function Aurora({ className = "" }: AuroraProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Subtle mouse-parallax on desktop
    const handleMouseMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      const cx = (e.clientX - rect.left) / rect.width  - 0.5;
      const cy = (e.clientY - rect.top)  / rect.height - 0.5;
      el.style.setProperty("--mx", `${cx * 30}px`);
      el.style.setProperty("--my", `${cy * 20}px`);
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  return (
    <>
      <style>{`
        @keyframes aurora1 {
          0%   { transform: translate(0, 0) scale(1); }
          50%  { transform: translate(12%, -8%) scale(1.18); }
          100% { transform: translate(20%, -14%) scale(1.1); }
        }
        @keyframes aurora2 {
          0%   { transform: translate(0, 0) scale(1.1); }
          50%  { transform: translate(-10%, 10%) scale(0.92); }
          100% { transform: translate(-16%, 18%) scale(1.05); }
        }
        @keyframes aurora3 {
          0%   { transform: translate(0, 0) scale(0.95); }
          50%  { transform: translate(8%, 12%) scale(1.12); }
          100% { transform: translate(14%, 20%) scale(1.0); }
        }
        @keyframes aurora4 {
          0%   { transform: translate(0, 0) scale(1.05); }
          50%  { transform: translate(-6%, -12%) scale(0.88); }
          100% { transform: translate(-10%, -20%) scale(1.08); }
        }
        .aurora-blob {
          position: absolute;
          border-radius: 9999px;
          filter: blur(80px);
          opacity: 0.55;
          will-change: transform;
          mix-blend-mode: screen;
        }
        .aurora-blob-1 {
          width: 60%;
          height: 55%;
          background: radial-gradient(ellipse at center, #14b8a6 0%, #0d9488 40%, transparent 75%);
          top: -10%;
          left: -5%;
          animation: aurora1 14s ease-in-out infinite alternate;
        }
        .aurora-blob-2 {
          width: 55%;
          height: 50%;
          background: radial-gradient(ellipse at center, #6366f1 0%, #4f46e5 40%, transparent 75%);
          top: 10%;
          right: -10%;
          animation: aurora2 18s ease-in-out infinite alternate;
        }
        .aurora-blob-3 {
          width: 45%;
          height: 45%;
          background: radial-gradient(ellipse at center, #8b5cf6 0%, #7c3aed 40%, transparent 75%);
          bottom: -5%;
          left: 20%;
          animation: aurora3 22s ease-in-out infinite alternate;
        }
        .aurora-blob-4 {
          width: 40%;
          height: 40%;
          background: radial-gradient(ellipse at center, #2dd4bf 0%, #0891b2 40%, transparent 75%);
          bottom: 10%;
          right: 5%;
          animation: aurora4 16s ease-in-out infinite alternate;
        }
      `}</style>
      <div
        ref={containerRef}
        className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
        aria-hidden="true"
        style={
          {
            "--mx": "0px",
            "--my": "0px",
          } as React.CSSProperties
        }
      >
        {/* Dark base */}
        <div className="absolute inset-0 bg-gray-950" />

        {/* Gradient overlay to darken edges */}
        <div className="absolute inset-0 bg-gradient-to-b from-gray-950/20 via-transparent to-gray-950/90" />

        {/* Blobs */}
        <div className="aurora-blob aurora-blob-1" />
        <div className="aurora-blob aurora-blob-2" />
        <div className="aurora-blob aurora-blob-3" />
        <div className="aurora-blob aurora-blob-4" />

        {/* Grain texture overlay */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E")`,
            backgroundRepeat: "repeat",
            backgroundSize: "128px 128px",
          }}
        />
      </div>
    </>
  );
}
