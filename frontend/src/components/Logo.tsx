interface LogoProps {
  className?: string;
}

/**
 * Citey mark: a paper (ringed node) with a citation arc landing on it, the
 * same motif as the hero timeline. Drawn in currentColor.
 */
export default function Logo({ className = "h-8 w-8" }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" fill="none">
      <path d="M28 5C22 5 15.5 9 13.6 16.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="28" cy="5" r="2" fill="currentColor" />
      <circle cx="12" cy="20" r="6.5" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="20" r="2.6" fill="currentColor" />
    </svg>
  );
}
