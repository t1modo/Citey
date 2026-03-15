"use client";

import { useState } from "react";
import type { Notification } from "@/lib/types";

interface NotificationCardProps {
  notification: Notification;
  onMarkSeen: (id: string) => void;
}

function formatDate(iso: string): string {
  // Parse date-only strings as local time to avoid UTC-offset off-by-one
  const parts = iso.split("T")[0].split("-").map(Number);
  const d = new Date(parts[0], parts[1] - 1, parts[2]);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function NotificationCard({
  notification,
  onMarkSeen,
}: NotificationCardProps) {
  const [marking, setMarking] = useState(false);

  const handleMarkSeen = async () => {
    if (notification.seen || marking) return;
    setMarking(true);
    try {
      onMarkSeen(notification.id);
    } finally {
      setMarking(false);
    }
  };

  const citingUrl =
    notification.citing_work_url ??
    (notification.citing_work_doi
      ? `https://doi.org/${notification.citing_work_doi}`
      : null);

  const affiliations =
    notification.citing_affiliations.length > 0
      ? notification.citing_affiliations
      : ["Independent"];

  return (
    <div
      className={`glass-card flex flex-col gap-3 p-4 transition-all duration-200 cursor-pointer hover:border-white/20 ${
        !notification.seen ? "border-white/15 bg-white/5" : ""
      }`}
      onClick={handleMarkSeen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && handleMarkSeen()}
      aria-label={`Notification: ${notification.citing_work_title} cites your work`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {!notification.seen && (
            <span
              className="h-2 w-2 shrink-0 rounded-full bg-white"
              aria-label="Unread"
            />
          )}
          <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
            New citation
          </span>
        </div>
        {(notification.citing_publication_date || notification.citing_year) && (
          <span className="shrink-0 text-xs text-gray-600">
            {notification.citing_publication_date
              ? formatDate(notification.citing_publication_date)
              : notification.citing_year}
          </span>
        )}
      </div>

      {/* Citing paper title — prominent headline */}
      <div>
        {citingUrl ? (
          <a
            href={citingUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-base font-bold text-white underline decoration-dotted underline-offset-2 hover:text-gray-300 hover:decoration-solid leading-snug transition-colors"
          >
            {notification.citing_work_title || "Untitled"}
          </a>
        ) : (
          <p className="text-base font-bold text-white leading-snug">
            {notification.citing_work_title || "Untitled"}
          </p>
        )}
      </div>

      {/* "cites your paper" divider */}
      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-white/5" />
        <span className="text-xs text-gray-600 italic">cites your paper</span>
        <div className="h-px flex-1 bg-white/5" />
      </div>

      {/* Your paper */}
      <div>
        <p className="mb-0.5 text-xs font-medium uppercase tracking-wide text-gray-400">
          Your paper
        </p>
        <p className="text-sm font-semibold text-white/80 leading-snug">
          {notification.cited_work_title || notification.cited_work_id}
        </p>
      </div>

      {/* Authors */}
      {notification.citing_authors.length > 0 && (
        <p className="text-xs text-gray-400 leading-relaxed">
          {notification.citing_authors.slice(0, 4).join(" · ")}
          {notification.citing_authors.length > 4 && (
            <span className="text-gray-600">
              {" "}+{notification.citing_authors.length - 4} more
            </span>
          )}
        </p>
      )}

      {/* Affiliation tags */}
      <div className="flex flex-wrap gap-1.5">
        {affiliations.slice(0, 4).map((affil) => {
          const isIndependent = affil === "Independent";
          return (
            <span
              key={affil}
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${
                isIndependent
                  ? "bg-white/5 text-gray-500 ring-white/10"
                  : "bg-white/8 text-gray-300 ring-white/10"
              }`}
            >
              {affil}
            </span>
          );
        })}
        {affiliations.length > 4 && (
          <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-white/5 text-gray-500 ring-1 ring-white/10">
            +{affiliations.length - 4} more
          </span>
        )}
      </div>

      {/* DOI row */}
      <div className="flex flex-wrap items-center gap-3 pt-1 border-t border-white/5">
        {notification.citing_work_doi && (
          <a
            href={`https://doi.org/${notification.citing_work_doi}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="font-mono text-xs text-gray-400 underline decoration-dotted underline-offset-2 hover:text-gray-300 transition-colors"
          >
            {notification.citing_work_doi}
          </a>
        )}
        {!notification.seen && (
          <span className="ml-auto text-xs text-gray-600">
            {marking ? "Marking…" : "Click to mark seen"}
          </span>
        )}
      </div>
    </div>
  );
}
