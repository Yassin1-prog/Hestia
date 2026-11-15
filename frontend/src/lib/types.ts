import type { TraceStep } from "./trace";

/**
 * Mirrors `PropertyDetails` in backend/agent.py (what POST /api/search returns).
 * Fields marked optional are frontend/demo extras the backend may add later.
 */
export interface Property {
  url: string;
  price: number | null;
  sqm: number | null;
  floor: string | null;
  features: string[];
  agent_name: string | null;
  agent_phone: string | null;
  agent_email: string | null;
  missing_info: string[];
  agentic_score: number;
  score_reason: string;
  title?: string;
  location?: string;
  /** The site the listing was found on (backend/sources.py key, e.g. "xe"). */
  source?: string;
  source_name?: string;
  /** Furnished short stay (Booking.com): the price is the cost of 30 nights. */
  short_stay?: boolean;
  /** Oumi Iris verdict from backend/decision.py, when the scam gate has run. */
  scam_verdict?: "SAFE" | "POSSIBLY_SCAM";
  scam_risk_pct?: number;
  /** The listing agent's judgement for this user (deep scrape). */
  pros?: string[];
  /** Listing photos, main photo first (deep scrape: og:image + page images). */
  images?: string[];
  cons?: string[];
  metrics?: MetricScore[];
}

export interface MetricScore {
  name: string;
  /** 1-10 */
  score: number;
  note: string;
}

export interface SearchStats {
  scanned: number;
  rejected: number;
  rejectReason?: string;
}

export interface SearchResult {
  /** The query as typed by the user (without the attached profile constraints). */
  query: string;
  reply: string;
  properties: Property[];
  stats?: SearchStats;
  source: "live" | "demo";
  /** Why demo data is shown instead of live results, if it is. */
  notice?: string;
}

export interface Profile {
  name: string;
  email: string;
  /** Google Calendar "secret address in iCal format"; the outreach agent reads free slots from it. */
  calendarUrl?: string;
}

/** State of the viewing-request e-mail to the landlord (POST /api/outreach/send). */
export type EmailState =
  | "sending"
  | "sent"
  | "dry_run"
  | "no_contact"
  | "failed"
  /** Demo listing: nothing is sent. */
  | "demo";

export interface EmailOutcome {
  state: EmailState;
  /** Actual recipient after any server-side override (OUTREACH_OVERRIDE_EMAIL). */
  to?: string | null;
  detail?: string | null;
  /** Viewing slots the agent proposed (from the user's calendar). */
  windows?: string[];
  subject?: string | null;
  body?: string | null;
}

/** The exact e-mail the outreach agent wrote (streamed before it is sent). */
export interface EmailDraft {
  to: string;
  subject: string;
  body: string;
}

/** One live outreach agent working on one listing (in memory, not persisted). */
export interface OutreachRun {
  steps: TraceStep[];
  draft: EmailDraft | null;
  phase: "running" | "done";
  startedAt: number;
  finishedAt?: number;
  outcome?: EmailOutcome;
}

export interface Viewing {
  property: Property;
  requestedAt: string;
  /** Missing on viewings saved before e-mail outreach existed. */
  email?: EmailOutcome;
  /** The questions the user approved for the landlord (reused on retry). */
  questions?: string[];
}

export const EMPTY_PROFILE: Profile = {
  name: "",
  email: "",
  calendarUrl: "",
};
