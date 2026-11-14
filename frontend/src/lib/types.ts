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
  /** Oumi Iris verdict from backend/decision.py, when the scam gate has run. */
  scam_verdict?: "SAFE" | "POSSIBLY_SCAM";
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
}

export interface Viewing {
  property: Property;
  requestedAt: string;
  /** Missing on viewings saved before e-mail outreach existed. */
  email?: EmailOutcome;
}

export const EMPTY_PROFILE: Profile = {
  name: "",
  email: "",
};
