import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
    theme: {
    extend: {
      colors: {
        // "Annotated manuscript": cool paper, Prussian-blue ink, and a
        // highlighter mark reserved for what's new (new citations).
        paper: "#EEF1F4", // page
        sheet: "#F8F9FB", // raised surfaces: cards, inputs, modals
        ink: {
          DEFAULT: "#14213D", // text, lines, primary buttons
          soft: "#2A3A5E",
        },
        muted: "#5B6577", // secondary text (5.3:1 on paper)
        rule: "#C9D0DA", // decorative borders and dividers
        control: "#7E8899", // form field and switch outlines: 3:1 against paper and sheet (WCAG 1.4.11)
        mark: {
          DEFAULT: "#FFE45C", // highlighter
          soft: "#FFF3A8",
        },
        danger: "#A3261C",
        ok: "#2F6B3B",
      },
      fontFamily: {
        sans: ["var(--font-ui)", "ui-sans-serif", "system-ui", "sans-serif"],
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
