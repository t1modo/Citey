"use client";

import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { getNotifications, markSeen as apiMarkSeen, markAllSeen as apiMarkAllSeen } from "@/lib/api";
import type { Notification } from "@/lib/types";

interface NotificationsContextValue {
  /** Most recent page of notifications (used by dashboard). */
  notifications: Notification[];
  /** Total unseen count across ALL notifications (from server). */
  unreadCount: number;
  /** Total notification count (from server). */
  totalCount: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  markSeen: (id: string) => Promise<void>;
  markAllSeen: () => Promise<void>;
}

const NotificationsContext = createContext<NotificationsContextValue | null>(null);

export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      // Fetch the first page — enough for the Nav unread badge and the
      // dashboard overview.  The dashboard manages deeper pagination itself.
      const data = await getNotifications(1, 20);
      setNotifications(data.items);
      setUnreadCount(data.unseen);
      setTotalCount(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  const markSeen = useCallback(async (id: string) => {
    try {
      const updated = await apiMarkSeen(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, seen: updated.seen } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // ignore silently
    }
  }, []);

  // Ref-based in-flight guard — prevents duplicate requests on rapid clicks.
  const markingAllRef = useRef(false);

  const markAllSeen = useCallback(async () => {
    if (unreadCount === 0 || markingAllRef.current) return;
    markingAllRef.current = true;

    // Snapshot current state so we can roll back if the request fails.
    const prevNotifications = notifications;
    const prevUnreadCount = unreadCount;

    // Optimistic update — clear badge and dots immediately.
    setNotifications((prev) => prev.map((n) => ({ ...n, seen: true })));
    setUnreadCount(0);
    // Native event so the dashboard citation list reacts without React batching.
    window.dispatchEvent(new Event("citey:markAllRead"));

    try {
      await apiMarkAllSeen();
    } catch {
      // Request failed — restore previous state.
      setNotifications(prevNotifications);
      setUnreadCount(prevUnreadCount);
    } finally {
      markingAllRef.current = false;
    }
  }, [unreadCount, notifications]);

  useEffect(() => {
    if (user) {
      refresh();
    } else {
      setNotifications([]);
      setUnreadCount(0);
      setTotalCount(0);
    }
  }, [user, refresh]);

  return (
    <NotificationsContext.Provider
      value={{ notifications, unreadCount, totalCount, loading, error, refresh, markSeen, markAllSeen }}
    >
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications() {
  const ctx = useContext(NotificationsContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationsProvider");
  return ctx;
}
