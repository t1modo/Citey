"use client";

import Link from "next/link";
import Logo from "@/components/Logo";
import Particles from "@/components/Particles";
import BlurText from "@/components/BlurText";
import SplitText from "@/components/SplitText";
import ScrollReveal from "@/components/ScrollReveal";
import HeroDemo from "@/components/HeroDemo";
import { useAuth } from "@/contexts/AuthContext";

const features = [
  {
    icon: "🔗",
    title: "Flexible paper import",
    description:
      "Add papers by DOI, arXiv URL, or INSPIRE / DBLP author profile URL. You can also search by author name. Citey resolves full metadata automatically from Crossref, OpenAlex, and more.",
  },
  {
    icon: "🔍",
    title: "Multi-source citation scans",
    description:
      "Our automated job runs every day, cross-referencing OpenAlex, Semantic Scholar, Crossref, PubMed, INSPIRE-HEP, DBLP, and NASA ADS to surface every new citation to your work.",
  },
  {
    icon: "📧",
    title: "Instant email alerts",
    description:
      "The moment a new citation is detected you receive a rich email with the citing paper's title, authors, affiliations, and a direct link to the paper.",
  },
  {
    icon: "👤",
    title: "Author profile linking",
    description:
      "Link your OpenAlex, INSPIRE-HEP, or DBLP author profile to auto-import your entire publication list. New papers you publish are added automatically and you are alerted right away.",
  },
  {
    icon: "🔒",
    title: "Secure and private",
    description:
      "Authenticated with Firebase. Your data is yours. We store only what is necessary to send you accurate, timely citation notifications.",
  },
];

const steps = [
  {
    step: 1,
    title: "Create your free account",
    description:
      "Sign up with your email address. No credit card required. Your account is secured with Firebase Authentication.",
  },
  {
    step: 2,
    title: "Add papers or link your author profile",
    description:
      "Paste a DOI, arXiv URL, or an INSPIRE / DBLP author profile URL — or just search by name. Linking your author profile auto-imports your full publication list and keeps it in sync as you publish new work.",
  },
  {
    step: 3,
    title: "We scan seven citation databases daily",
    description:
      "Every day, Citey queries OpenAlex, Semantic Scholar, Crossref, PubMed, INSPIRE-HEP, DBLP, and NASA ADS for papers that reference your tracked works. New citations are recorded and you are notified immediately.",
  },
  {
    step: 4,
    title: "Receive rich email alerts",
    description:
      "Each alert includes the citing paper's full title, authors, institutional affiliations, publication year, and a one-click link to the source, directly in your inbox.",
  },
];

export default function HomePage() {
  const { user } = useAuth();

  return (
    <div className="flex flex-col">
      {/* ─── Full-page fixed particle background ──────────────────────── */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <Particles
          particleCount={180}
          particleSpread={10}
          speed={0.08}
          particleColors={["#ffffff", "#d1d5db", "#9ca3af"]}
          alphaParticles={true}
          particleBaseSize={90}
          sizeRandomness={1.2}
          cameraDistance={22}
          moveParticlesOnHover={false}
          disableRotation={false}
          pixelRatio={1}
        />
      </div>

      {/* ─── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center px-4 pt-20 pb-8 text-center [@media(max-height:820px)]:pt-10 [@media(max-height:820px)]:pb-4">

        {/* Subheading */}
        <p className="relative z-10 mb-8 max-w-xl text-lg leading-relaxed text-gray-400 sm:text-xl [@media(max-height:820px)]:mb-4 [@media(max-height:820px)]:text-base">
          Citey monitors your research and emails you the moment a new paper cites your work.
        </p>

        {/* CTA buttons */}
        <div className="relative z-10 mb-10 flex flex-col items-center gap-3 sm:flex-row [@media(max-height:820px)]:mb-5">
          <Link
            href={user ? "/dashboard" : "/signup"}
            className="rounded-xl bg-white px-8 py-3.5 text-base font-semibold text-gray-950 shadow-xl shadow-white/10 transition-all hover:scale-105 hover:bg-gray-100"
          >
            {user ? "Go to Dashboard" : "Get Started, It's Free!"}
          </Link>
          <a
            href="#features"
            className="rounded-xl border border-white/10 px-8 py-3.5 text-base font-semibold text-gray-300 transition-all hover:border-white/25 hover:bg-white/5 hover:text-white"
          >
            Learn more
          </a>
        </div>

        {/* Animated demo */}
        <HeroDemo />

        {/* Scroll indicator */}
        <div className="absolute bottom-6 left-1/2 z-10 -translate-x-1/2 animate-bounce text-gray-600">
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </section>

      {/* ─── Features ─────────────────────────────────────────────────── */}
      <section
        id="features"
        className="mx-auto w-full max-w-7xl px-4 py-24 sm:px-6 lg:px-8"
      >
        <ScrollReveal className="mb-14 text-center">
          <h2 className="mb-4 text-3xl font-bold text-white sm:text-4xl">
            Everything you need to track your impact
          </h2>
          <p className="mx-auto max-w-xl text-gray-400">
            Citey handles the tedious work of monitoring citation databases so
            you can focus on what matters. Do great research.
          </p>
        </ScrollReveal>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.slice(0, 3).map(({ icon, title, description }, i) => (
            <ScrollReveal key={title} delay={i * 0.08}>
              <div className="glass-card flex h-full flex-col gap-3 p-6 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/8 text-xl">
                    {icon}
                  </div>
                  <h3 className="text-lg font-semibold text-white">{title}</h3>
                </div>
                <p className="text-sm leading-relaxed text-gray-400">{description}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
        <div className="mx-auto mt-6 grid gap-6 sm:grid-cols-2 lg:w-2/3">
          {features.slice(3).map(({ icon, title, description }, i) => (
            <ScrollReveal key={title} delay={(i + 3) * 0.08}>
              <div className="glass-card flex h-full flex-col gap-3 p-6 transition-all duration-300 hover:border-white/20 hover:bg-white/5">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/8 text-xl">
                    {icon}
                  </div>
                  <h3 className="text-lg font-semibold text-white">{title}</h3>
                </div>
                <p className="text-sm leading-relaxed text-gray-400">{description}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ─── How it works ──────────────────────────────────────────────── */}
      <section className="bg-gray-900/50 py-24">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <ScrollReveal className="mb-14 text-center">
            <h2 className="mb-4 text-3xl font-bold text-white sm:text-4xl">
              <SplitText text="Up and running in minutes" />
            </h2>
            <p className="text-gray-400">
              Four simple steps from sign-up to your first citation alert.
            </p>
          </ScrollReveal>

          <div className="flex flex-col gap-10">
            {steps.map(({ step, title, description }, i) => (
              <ScrollReveal key={step} delay={i * 0.1}>
                <div className="flex gap-4">
                  <div className="shrink-0 flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-bold text-gray-950 shadow-lg">
                    {step}
                  </div>
                  <div className="pt-1">
                    <h3 className="mb-1 text-base font-semibold text-white">{title}</h3>
                    <p className="text-sm leading-relaxed text-gray-400">{description}</p>
                  </div>
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA banner ────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden py-24">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-gray-900/40 via-gray-800/20 to-gray-900/40" />
        <ScrollReveal className="relative mx-auto max-w-3xl px-4 text-center sm:px-6">
          <h2 className="mb-4 text-3xl font-bold text-white sm:text-4xl">
            <SplitText text="Ready to stay on top of your citations?" charDelay={0.022} />
          </h2>
          <p className="mb-8 text-lg text-gray-400">
            Join researchers who use Citey to automatically track when their
            work is cited, and never miss a mention again.
          </p>
          <Link
            href={user ? "/dashboard" : "/signup"}
            className="inline-block rounded-xl bg-white px-10 py-4 text-base font-bold text-gray-950 shadow-xl shadow-white/10 transition-all hover:scale-105 hover:bg-gray-100"
          >
            {user ? "Go to Dashboard" : "Start tracking for free"}
          </Link>
        </ScrollReveal>
      </section>

      {/* ─── Footer ────────────────────────────────────────────────────── */}
      <footer className="border-t border-white/5 bg-gray-950 py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
            <div className="flex items-center gap-2">
              <Logo className="h-7 w-7" />
              <span className="font-bold text-white" style={{ fontFamily: "var(--font-syne)" }}>Citey</span>
              <span className="text-sm text-gray-600">
                Citation Alerts for Researchers
              </span>
            </div>

            <nav className="flex flex-wrap justify-center gap-6 text-sm text-gray-500">
              <Link href="/"          className="transition-colors hover:text-gray-300">Home</Link>
              <Link href="/dashboard" className="transition-colors hover:text-gray-300">Dashboard</Link>
              <Link href="/settings"  className="transition-colors hover:text-gray-300">Settings</Link>
              <Link href="/faq"       className="transition-colors hover:text-gray-300">FAQ</Link>
            </nav>
          </div>

          <div className="mt-8 border-t border-white/5 pt-8 text-center text-xs text-gray-600">
            <p>
              &copy; {new Date().getFullYear()} Citey. Built for researchers, by researchers.
            </p>
            <p className="mt-1.5">
              Citation data sourced from{" "}
              <a href="https://openalex.org" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">OpenAlex</a>
              ,{" "}
              <a href="https://www.semanticscholar.org" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">Semantic Scholar</a>
              ,{" "}
              <a href="https://www.crossref.org" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">Crossref</a>
              ,{" "}
              <a href="https://pubmed.ncbi.nlm.nih.gov" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">PubMed</a>
              ,{" "}
              <a href="https://inspirehep.net" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">INSPIRE-HEP</a>
              ,{" "}
              <a href="https://dblp.org" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">DBLP</a>
              , and{" "}
              <a href="https://ui.adsabs.harvard.edu" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-300">NASA ADS</a>
              .
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
