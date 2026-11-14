"use client";

import { CalendarDays, Heart, UserRound } from "lucide-react";

export type PanelKey = "viewings" | "favorites" | "settings";

export function Logo({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="brand" onClick={onClick} aria-label="Hestia, back to home">
      <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
        <defs>
          <linearGradient id="brand-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--emerald)" />
            <stop offset="100%" stopColor="var(--gold)" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="30" height="30" rx="9" fill="none" stroke="var(--border-strong)" />
        <path
          d="M8 22V14.5L16 8l8 6.5V22"
          fill="none"
          stroke="url(#brand-gradient)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="16" cy="18" r="2.2" fill="var(--gold)" />
      </svg>
      <span className="brand-text">
        <span className="brand-name">Hestia</span>
        <span className="brand-tag">Autonomous housing agent</span>
      </span>
    </button>
  );
}

interface TopNavProps {
  viewingsCount: number;
  favoritesCount: number;
  onHome: () => void;
  onOpen: (panel: PanelKey) => void;
}

export function TopNav({ viewingsCount, favoritesCount, onHome, onOpen }: TopNavProps) {
  return (
    <header className="topnav">
      <Logo onClick={onHome} />
      <nav className="topnav-actions" aria-label="Panels">
        <button type="button" className="nav-btn" onClick={() => onOpen("viewings")}>
          <CalendarDays size={16} strokeWidth={1.75} />
          <span>My Viewings</span>
          {viewingsCount > 0 && <span className="nav-count">{viewingsCount}</span>}
        </button>
        <button type="button" className="nav-btn" onClick={() => onOpen("favorites")}>
          <Heart size={16} strokeWidth={1.75} />
          <span>My Favorites</span>
          {favoritesCount > 0 && <span className="nav-count">{favoritesCount}</span>}
        </button>
        <button
          type="button"
          className="nav-btn nav-btn-icon"
          onClick={() => onOpen("settings")}
          aria-label="Settings and profile"
          title="Settings and profile"
        >
          <UserRound size={16} strokeWidth={1.75} />
        </button>
      </nav>
    </header>
  );
}
