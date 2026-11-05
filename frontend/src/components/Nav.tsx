"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import Logo from "@/components/Logo";

const allNavLinks = [
  { label: "Home",      href: "/",          authOnly: false },
  { label: "Dashboard", href: "/dashboard", authOnly: true },
  { label: "Settings",  href: "/settings",  authOnly: true },
  { label: "FAQ",       href: "/faq",       authOnly: false },
  { label: "Help",      href: "/help",      authOnly: false },
];

export default function Nav() {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  // Signed out visitors would just be bounced to sign in from these pages.
  const navLinks = allNavLinks.filter((l) => user || !l.authOnly);

  const handleSignOut = async () => {
    try {
      await signOut();
      router.push("/");
    } catch {
      // ignore
    }
  };

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <nav className="sticky top-0 z-50 border-b border-rule bg-paper/90 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-2"
          >
            <Logo className="h-8 w-8" />
            <span
              className="text-xl font-bold tracking-tight text-ink"
              style={{ fontFamily: "var(--font-serif)", fontWeight: 400 }}
            >
              Citey
            </span>
          </Link>

          {/* Desktop links */}
          <div className="hidden items-center gap-1 md:flex">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive(link.href) ? "page" : undefined}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(link.href)
                    ? "font-bold text-ink underline decoration-2 underline-offset-8"
                    : "text-ink hover:underline hover:decoration-rule hover:decoration-2 hover:underline-offset-8"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>

          {/* Desktop right section */}
          <div className="hidden items-center gap-2 md:flex">
            {user ? (
              <>
                <span className="max-w-[180px] truncate text-sm text-muted">
                  {user.email}
                </span>
                <button
                  onClick={handleSignOut}
                  className="rounded-md border border-rule px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:border-danger/40 hover:bg-danger/10 hover:text-danger"
                >
                  Sign out
                </button>
              </>
            ) : (
              <Link
                href="/signup"
                className="rounded-md border border-rule px-4 py-1.5 text-sm font-medium text-ink transition-colors hover:border-ink"
              >
                Sign in
              </Link>
            )}
          </div>

          {/* Mobile right: hamburger */}
          <div className="flex items-center gap-1 md:hidden">
            <button
              className="flex items-center justify-center rounded-md p-2 text-muted transition-colors hover:bg-ink/5 hover:text-ink"
              onClick={() => setMenuOpen((prev) => !prev)}
              aria-label="Toggle menu"
              aria-expanded={menuOpen}
            >
              {menuOpen ? (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="border-t border-rule bg-paper/90 px-4 pb-4 pt-2 md:hidden">
          <div className="flex flex-col gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive(link.href) ? "page" : undefined}
                onClick={() => setMenuOpen(false)}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(link.href)
                    ? "font-bold text-ink underline decoration-2 underline-offset-8"
                    : "text-ink hover:underline hover:decoration-rule hover:decoration-2 hover:underline-offset-8"
                }`}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-2 border-t border-rule pt-2">
              {user ? (
                <>
                  <p className="px-3 py-1 text-xs text-muted truncate">{user.email}</p>
                  <button
                    onClick={() => { handleSignOut(); setMenuOpen(false); }}
                    className="mt-1 w-full rounded-md border border-rule px-3 py-2 text-left text-sm font-medium text-ink transition-colors hover:border-danger/40 hover:bg-danger/10 hover:text-danger"
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <Link
                  href="/signup"
                  onClick={() => setMenuOpen(false)}
                  className="block rounded-md bg-ink px-4 py-2 text-center text-sm font-semibold text-paper"
                >
                  Sign in
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
