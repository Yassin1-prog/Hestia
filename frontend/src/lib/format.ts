import type { Property } from "./types";

export function propertyTitle(p: Property): string {
  if (p.title) return p.title;
  return p.sqm ? `${p.sqm} m² apartment` : "Apartment";
}

export function propertyLocation(p: Property): string {
  if (p.location) return p.location;
  try {
    return new URL(p.url).hostname.replace(/^www\./, "");
  } catch {
    return "Listing";
  }
}

export function formatPrice(price: number | null): string {
  return price ? `€${price.toLocaleString("en-US")}/mo` : "Price on request";
}

export function propertyFacts(p: Property): string[] {
  const facts = [formatPrice(p.price)];
  if (p.sqm) facts.push(`${p.sqm} m²`);
  if (p.floor) facts.push(/floor/i.test(p.floor) ? p.floor : `${p.floor} floor`);
  return facts;
}

/** Oumi Iris badge text: "Safe · 7% risk" or "Possible scam · 96% risk". */
export function scamLabel(p: Property): string {
  const verdict = p.scam_verdict === "POSSIBLY_SCAM" ? "Possible scam" : "Safe";
  return p.scam_risk_pct != null ? `${verdict} · ${p.scam_risk_pct}% risk` : verdict;
}

/** Plain-English scam warning shown on flagged cards, the details modal, and the outreach brief. */
export function scamWarningText(p: Property): string {
  const reason = (p.scam_reason?.trim() || "This listing shows rental-scam patterns").replace(
    /\.+$/,
    "",
  );
  return `${reason}. The agent will draft the e-mail for review but will not send it.`;
}

/** True when an outreach outcome was blocked by the Oumi Iris scam lock rather than a server dry run. */
export function isScamLockedOutcome(outcome?: { detail?: string | null }): boolean {
  return Boolean(outcome?.detail && /oumi iris|possible scam/i.test(outcome.detail));
}

/** Backend scores are 1-10 (ints); demo data may use decimals. */
export function scoreLabel(score: number): string {
  const clamped = Math.max(0, Math.min(10, score));
  return Number.isInteger(clamped) ? `${clamped}` : clamped.toFixed(1);
}

export function matchPercent(score: number): number {
  return Math.round(Math.max(0, Math.min(10, score)) * 10);
}

/** 0:42 / 1:05 */
export function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function scoreTier(score: number): "gold" | "emerald" | "muted" {
  if (score >= 9) return "gold";
  if (score >= 7) return "emerald";
  return "muted";
}
