"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useNotifications } from "@/contexts/NotificationsContext";
import { labsToText } from "@/lib/labs";

const navLinks = [
  { label: "Home",      href: "/" },
  { label: "Dashboard", href: "/dashboard" },
  { label: "Settings",  href: "/settings" },
  { label: "FAQ",       href: "/faq" },
];

function formatRelativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function BellIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
      />
    </svg>
  );
}

function NotificationDropdown({
  onClose,
}: {
  onClose: () => void;
}) {
  const { notifications, unreadCount, loading, markSeen } = useNotifications();
  const recent = notifications.slice(0, 6);

  const handleItemClick = async (id: string, seen: boolean) => {
    if (!seen) {
      await markSeen(id);
      window.dispatchEvent(new CustomEvent("citey:markRead", { detail: id }));
    }
  };

  return (
    <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-white/10 bg-gray-900 shadow-2xl overflow-hidden z-50">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <span className="text-sm font-semibold text-white">Notifications</span>
      </div>

      {/* Notification list */}
      <div className="max-h-80 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <svg className="h-5 w-5 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
            </svg>
          </div>
        ) : recent.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <BellIcon className="h-8 w-8 text-gray-600" />
            <p className="text-sm text-gray-500">No notifications yet</p>
          </div>
        ) : (
          recent.map((n) => {
            const byLine = labsToText(n.citing_affiliations);
            const yourPaper = n.cited_work_title || n.cited_work_id;
            return (
              <button
                key={n.id}
                onClick={() => handleItemClick(n.id, n.seen)}
                className={`w-full border-b border-white/5 px-4 py-3 text-left transition-colors last:border-0 hover:bg-white/5 ${
                  !n.seen ? "bg-white/5" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  {!n.seen && (
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-white" />
                  )}
                  <div className={`flex-1 min-w-0 ${n.seen ? "pl-3.5" : ""}`}>
                    <p className="truncate text-sm font-medium text-white">
                      Cited by {byLine}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-gray-500">
                      &ldquo;{yourPaper}&rdquo;
                    </p>
                    {n.created_at && (
                      <p className="mt-1 text-xs text-gray-600">{formatRelativeDate(n.created_at)}</p>
                    )}
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>

    </div>
  );
}

export default function Nav() {
  const { user, signOut } = useAuth();
  const { unreadCount } = useNotifications();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch {
      // ignore
    }
  };

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  // Close bell dropdown on outside click
  useEffect(() => {
    if (!bellOpen) return;
    function handleClick(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setBellOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [bellOpen]);

  return (
    <nav className="sticky top-0 z-50 border-b border-white/10 bg-gray-950/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-2"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white shadow-lg text-gray-950">
              <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
                {/* Citation lines */}
                <line x1="5.5" y1="5.5" x2="10" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
                <line x1="18.5" y1="5.5" x2="14" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
                <line x1="12" y1="19.5" x2="12" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
                {/* Source nodes */}
                <circle cx="4.5" cy="4.5" r="2" fill="currentColor" opacity="0.6"/>
                <circle cx="19.5" cy="4.5" r="2" fill="currentColor" opacity="0.6"/>
                <circle cx="12" cy="20.5" r="2" fill="currentColor" opacity="0.6"/>
                {/* Center node */}
                <circle cx="12" cy="12" r="3.5" fill="currentColor"/>
              </svg>
            </span>
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
            {/* Bell icon */}
            {user && (
              <div className="relative" ref={bellRef}>
                <button
                  onClick={() => setBellOpen((prev) => !prev)}
                  className="relative flex items-center justify-center rounded-md p-2 text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
                  aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
                  aria-expanded={bellOpen}
                >
                  <BellIcon className="h-5 w-5" />
                  {unreadCount > 0 && (
                    <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-white text-[10px] font-bold text-gray-950">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </button>
                {bellOpen && <NotificationDropdown onClose={() => setBellOpen(false)} />}
              </div>
            )}

            {/* Auth */}
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

          {/* Mobile right: bell + hamburger */}
          <div className="flex items-center gap-1 md:hidden">
            {user && (
              <div className="relative" ref={bellOpen ? bellRef : undefined}>
                <button
                  onClick={() => { setBellOpen((prev) => !prev); setMenuOpen(false); }}
                  className="relative flex items-center justify-center rounded-md p-2 text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
                  aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
                >
                  <BellIcon className="h-5 w-5" />
                  {unreadCount > 0 && (
                    <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-white text-[10px] font-bold text-gray-950">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </button>
                {bellOpen && (
                  <div ref={bellRef} className="absolute right-0 top-full mt-2 w-72">
                    <NotificationDropdown onClose={() => setBellOpen(false)} />
                  </div>
                )}
              </div>
            )}
            <button
              className="flex items-center justify-center rounded-md p-2 text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              onClick={() => { setMenuOpen((prev) => !prev); setBellOpen(false); }}
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
