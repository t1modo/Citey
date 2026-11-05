import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Citey identity: warm ink background, paper-white text, and one
        // signal color reserved for citations (the arcs in the hero).
        ink: {
          DEFAULT: "#0c0d10",
          900: "#0c0d10",
          800: "#121418",
          700: "#1a1d22",
          600: "#262a31",
        },
        paper: "#e8e2d6",
        signal: {
          DEFAULT: "#ff6a3d",
          soft: "#ff8a66",
        },
        brand: {
          50:  "#f0fdfa",
          100: "#ccfbf1",
          200: "#99f6e4",
          300: "#5eead4",
          400: "#2dd4bf",
          500: "#14b8a6",
          600: "#0d9488",
          700: "#0f766e",
          800: "#115e59",
          900: "#134e4a",
        },
      },
      fontFamily: {
        sans: ["var(--font-jakarta)", "ui-sans-serif", "system-ui", "sans-serif"],
        syne: ["var(--font-syne)", "ui-sans-serif", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      animation: {
        "aurora-1": "aurora1 12s ease-in-out infinite alternate",
        "aurora-2": "aurora2 16s ease-in-out infinite alternate",
        "aurora-3": "aurora3 20s ease-in-out infinite alternate",
        "aurora-4": "aurora4 14s ease-in-out infinite alternate",
      },
      keyframes: {
        aurora1: {
          "0%":   { transform: "translate(0%, 0%) scale(1)" },
          "100%": { transform: "translate(15%, -10%) scale(1.2)" },
        },
        aurora2: {
          "0%":   { transform: "translate(0%, 0%) scale(1.1)" },
          "100%": { transform: "translate(-12%, 12%) scale(0.9)" },
        },
        aurora3: {
          "0%":   { transform: "translate(0%, 0%) scale(0.9)" },
          "100%": { transform: "translate(10%, 15%) scale(1.15)" },
        },
        aurora4: {
          "0%":   { transform: "translate(0%, 0%) scale(1.05)" },
          "100%": { transform: "translate(-8%, -15%) scale(0.95)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
