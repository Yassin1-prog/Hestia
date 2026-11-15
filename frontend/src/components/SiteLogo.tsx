"use client";

import { useState } from "react";

/**
 * Logos of the sites and services the agents work with. Keys match the `source` / `sources`
 * fields of the streamed events (backend/sources.py, backend/outreach/live.py) and the
 * `source` field of a listing. Files live in public/logos/.
 */
export const SITES: Record<string, { name: string; logo: string; domain: string }> = {
  spitogatos: { name: "Spitogatos", logo: "/logos/spitogatos.png", domain: "spitogatos.gr" },
  xe: { name: "xe.gr", logo: "/logos/xe.png", domain: "xe.gr" },
  booking: { name: "Booking.com", logo: "/logos/booking.png", domain: "booking.com" },
  google_calendar: {
    name: "Google Calendar",
    logo: "/logos/google-calendar.png",
    domain: "calendar.google.com",
  },
};

/** The site a listing URL belongs to, if it is one we search. */
export function siteForUrl(url: string): string | undefined {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    return Object.keys(SITES).find(
      (key) => host === SITES[key].domain || host.endsWith(`.${SITES[key].domain}`),
    );
  } catch {
    return undefined;
  }
}

export function SiteLogo({
  source,
  size = 16,
  className,
}: {
  source: string;
  size?: number;
  className?: string;
}) {
  const site = SITES[source];
  const [failed, setFailed] = useState(false);
  const name = site?.name ?? source;
  const style = { width: size, height: size };
  const classes = `site-logo${className ? ` ${className}` : ""}`;
  if (!site || failed) {
    return (
      <span
        className={`${classes} site-logo-fallback`}
        style={style}
        title={name}
        aria-label={name}
      >
        {name.charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- tiny static icon, no optimisation needed
    <img
      src={site.logo}
      alt={name}
      title={name}
      width={size}
      height={size}
      className={classes}
      style={style}
      onError={() => setFailed(true)}
    />
  );
}

/** "[logo] Spitogatos": where a listing was found. */
export function SiteBadge({ source }: { source: string }) {
  return (
    <span className="site-badge">
      <SiteLogo source={source} size={14} />
      {SITES[source]?.name ?? source}
    </span>
  );
}

/** A row of logos (e.g. every site a step searches). */
export function SiteLogos({ sources, size = 16 }: { sources: string[]; size?: number }) {
  if (!sources.length) return null;
  return (
    <span className="site-logos">
      {sources.map((s) => (
        <SiteLogo key={s} source={s} size={size} />
      ))}
    </span>
  );
}
