import { Dancing_Script } from "next/font/google";

const dancing = Dancing_Script({
  subsets: ["latin"],
  weight: ["700"],
});

interface LogoProps {
  className?: string;
}

/**
 * Citey's script "C". The original mark is white with a soft radial
 * gradient for dark backgrounds; on the paper theme the same letterform is
 * drawn in ink, with the gradient kept (deepest at the spine, lifting
 * toward the tips).
 */
export default function Logo({ className = "h-8 w-8" }: LogoProps) {
  return (
    <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" className={className} aria-hidden="true">
      <defs>
        <radialGradient id="citey-logo-ink" cx="25%" cy="50%" r="75%" gradientUnits="objectBoundingBox">
          <stop offset="0%" stopColor="#14213D" />
          <stop offset="100%" stopColor="#3B4A6B" />
        </radialGradient>
      </defs>
      <text
        x="100"
        y="158"
        textAnchor="middle"
        style={{ fontFamily: dancing.style.fontFamily, fontSize: 168, fontWeight: "bold" }}
        fill="url(#citey-logo-ink)"
      >
        C
      </text>
    </svg>
  );
}
