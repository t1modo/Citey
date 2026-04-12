"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import Logo from "@/components/Logo";

const navLinks = [
  { label: "Home",      href: "/" },
  { label: "Dashboard", href: "/dashboard" },
  { label: "Settings",  href: "/settings" },
  { label: "FAQ",       href: "/faq" },
  { label: "Help",      href: "/help" },
];

export default function Nav() {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch {
      // ignore
    }
  };

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <nav className="sticky top-0 z-50 border-b border-white/10 bg-gray-950/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-2"
          >
            <Logo className="h-8 w-8" />
            <span
              className="text-xl font-bold tracking-tight text-white"
              style={{ fontFamily: "var(--font-syne)" }}
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
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(link.href)
                    ? "bg-white/10 text-white"
                    : "text-gray-300 hover:bg-white/5 hover:text-white"
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
                <span className="max-w-[180px] truncate text-sm text-gray-400">
                  {user.email}
                </span>
                <button
                  onClick={handleSignOut}
                  className="rounded-md border border-white/10 px-3 py-1.5 text-sm font-medium text-gray-300 transition-colors hover:border-red-500/50 hover:bg-red-500/10 hover:text-red-400"
                >
                  Sign Out
                </button>
              </>
            ) : (
              <Link
                href="/signup"
                className="rounded-md bg-white px-4 py-1.5 text-sm font-semibold text-gray-950 shadow-lg transition-opacity hover:opacity-90"
              >
                Sign In
              </Link>
            )}
          </div>

          {/* Mobile right: hamburger */}
          <div className="flex items-center gap-1 md:hidden">
            <button
              className="flex items-center justify-center rounded-md p-2 text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
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
        <div className="border-t border-white/10 bg-gray-950/95 px-4 pb-4 pt-2 md:hidden">
          <div className="flex flex-col gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(link.href)
                    ? "bg-white/10 text-white"
                    : "text-gray-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-2 border-t border-white/10 pt-2">
              {user ? (
                <>
                  <p className="px-3 py-1 text-xs text-gray-500 truncate">{user.email}</p>
                  <button
                    onClick={() => { handleSignOut(); setMenuOpen(false); }}
                    className="mt-1 w-full rounded-md border border-white/10 px-3 py-2 text-left text-sm font-medium text-gray-300 transition-colors hover:border-red-500/50 hover:bg-red-500/10 hover:text-red-400"
                  >
                    Sign Out
                  </button>
                </>
              ) : (
                <Link
                  href="/signup"
                  onClick={() => setMenuOpen(false)}
                  className="block rounded-md bg-white px-4 py-2 text-center text-sm font-semibold text-gray-950"
                >
                  Sign In
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
