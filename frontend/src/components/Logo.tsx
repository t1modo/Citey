import { Dancing_Script } from "next/font/google";

const dancing = Dancing_Script({
  subsets: ["latin"],
  weight: ["700"],
});

interface LogoProps {
  className?: string;
}

export default function Logo({ className = "h-8 w-8" }: LogoProps) {
  return (
    <svg
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <radialGradient
          id="logo-fill"
          cx="25%"
          cy="50%"
          r="75%"
          gradientUnits="objectBoundingBox"
        >
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#b0b0b0" />
        </radialGradient>
        <filter id="logo-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="6" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Ambient glow layer */}
      <text
        x="100"
        y="158"
        textAnchor="middle"
        style={{
          fontFamily: dancing.style.fontFamily,
          fontSize: 168,
          fontWeight: "bold",
        }}
        fill="white"
        fillOpacity={0.18}
        filter="url(#logo-glow)"
      >
        C
      </text>
      {/* Main letter */}
      <text
        x="100"
        y="158"
        textAnchor="middle"
        style={{
          fontFamily: dancing.style.fontFamily,
          fontSize: 168,
          fontWeight: "bold",
        }}
        fill="url(#logo-fill)"
      >
        C
      </text>
    </svg>
  );
}
