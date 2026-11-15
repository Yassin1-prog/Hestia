import { propertyTitle } from "./format";
import { readNdjson, type AgentEvent } from "./trace";
import type {
  EmailOutcome,
  EmailState,
  OutreachChannel,
  Profile,
  Property,
  SearchResult,
  SearchStats,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

/** The live pipeline (Firecrawl + Gemini, 3 deep scrapes) can take a couple of minutes. */
const SEARCH_TIMEOUT_MS = 180_000;

/** Trims the user query before sending it to POST /api/search. */
export function buildRequest(query: string, _profile?: Profile): string {
  return query.trim();
}

function isProperty(value: unknown): value is Property {
  return typeof value === "object" && value !== null && "url" in value;
}

function normalizeProperty(p: Property): Property {
  const scam_verdict =
    p.scam_verdict === "SAFE" || p.scam_verdict === "POSSIBLY_SCAM" ? p.scam_verdict : undefined;
  const scam_risk_pct =
    p.scam_risk_pct != null && Number.isFinite(Number(p.scam_risk_pct))
      ? Math.max(0, Math.min(100, Math.round(Number(p.scam_risk_pct))))
      : undefined;
  const scam_reason = typeof p.scam_reason === "string" ? p.scam_reason.trim() || null : null;

  return {
    ...p,
    features: Array.isArray(p.features) ? p.features : [],
    missing_info: Array.isArray(p.missing_info) ? p.missing_info : [],
    pros: Array.isArray(p.pros) ? p.pros : [],
    images: Array.isArray(p.images)
      ? p.images.filter((u): u is string => typeof u === "string" && /^(https?:)?\/\//.test(u))
      : [],
    cons: Array.isArray(p.cons) ? p.cons : [],
    metrics: Array.isArray(p.metrics)
      ? p.metrics.filter((m) => m && typeof m.name === "string" && Number.isFinite(Number(m.score)))
      : [],
    agentic_score: Number(p.agentic_score) || 0,
    score_reason: p.score_reason || "",
    scam_verdict,
    scam_risk_pct,
    scam_reason,
  };
}

/** Used when the backend returns a bare list (current `/api/search`) without `reply`. */
export function synthesizeReply(properties: Property[]): string {
  if (!properties.length) {
    return (
      "I could not find listings that match this request right now. Try widening the area or " +
      "the budget, or remove one of the must-haves."
    );
  }
  const top = properties[0];
  const parts = [
    `I reviewed the latest listings for your request and shortlisted ${properties.length}.`,
    `My top pick is the ${propertyTitle(top).toLowerCase()} (${top.agentic_score}/10)` +
      (top.score_reason ? `: ${top.score_reason.replace(/\.$/, "")}.` : "."),
  ];
  const question = properties.flatMap((p) => p.missing_info)[0];
  if (question) {
    parts.push(`I will also ask the landlords what the listings leave open, such as "${question}"`);
  }
  parts.push("Approve a viewing on any card and I will e-mail the landlord for you.");
  return parts.join(" ");
}

/**
 * Accepts the current backend shape (`PropertyDetails[]`) and a richer future shape
 * (`{ reply, properties, stats }`).
 */
export function normalize(query: string, data: unknown): SearchResult {
  const obj = (Array.isArray(data) ? { properties: data } : (data ?? {})) as {
    reply?: unknown;
    properties?: unknown;
    results?: unknown;
    stats?: SearchStats;
  };
  const list = Array.isArray(obj.properties)
    ? obj.properties
    : Array.isArray(obj.results)
      ? obj.results
      : [];
  const properties = list
    .filter(isProperty)
    .map(normalizeProperty)
    .sort(
      (a, b) =>
        Number(a.scam_verdict === "POSSIBLY_SCAM") - Number(b.scam_verdict === "POSSIBLY_SCAM") ||
        b.agentic_score - a.agentic_score,
    )
    .slice(0, 5);
  return {
    query,
    reply: typeof obj.reply === "string" && obj.reply ? obj.reply : synthesizeReply(properties),
    properties,
    stats: obj.stats,
    source: "live",
  };
}

export class BackendUnavailable extends Error {}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    /* non-JSON error body */
  }
  return `HTTP ${res.status}`;
}

/**
 * Streams the search agent (POST /api/search/stream). Progress events go to `onEvent` as
 * they arrive; resolves with the final result. Throws `BackendUnavailable` (offline, HTTP
 * error, timeout, pipeline error) so the caller can fall back to demo data, or rethrows the
 * abort if `signal` was aborted by the user.
 */
export async function streamSearch(
  query: string,
  profile: Profile,
  signal: AbortSignal,
  onEvent: (event: AgentEvent) => void,
): Promise<SearchResult> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, SEARCH_TIMEOUT_MS);
  const onAbort = () => controller.abort();
  signal.addEventListener("abort", onAbort);

  try {
    const res = await fetch(`${API_BASE}/api/search/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: buildRequest(query, profile) }),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new BackendUnavailable(
        `The agent backend returned an error (${await errorDetail(res)}).`,
      );
    }
    let result: SearchResult | null = null;
    let failure: string | null = null;
    await readNdjson(res, (event) => {
      if (event.type === "result") result = normalize(query, event);
      else if (event.type === "error") failure = event.detail || "unknown error";
      else onEvent(event);
    });
    if (failure) throw new BackendUnavailable(`The search agent stopped (${failure}).`);
    if (!result) throw new BackendUnavailable("The search agent stopped before finishing.");
    return result;
  } catch (err) {
    if (signal.aborted) throw err;
    if (err instanceof BackendUnavailable) throw err;
    throw new BackendUnavailable(
      timedOut ? "The agent backend timed out." : "The agent backend is offline.",
    );
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener("abort", onAbort);
  }
}

export const DEMO_URL = /[?&]demo=/;

export function isDemoListing(property: Property): boolean {
  return DEMO_URL.test(property.url);
}

interface OutreachAttempt {
  channel: string;
  status: "sent" | "dry_run" | "skipped" | "failed";
  to?: string | null;
  detail?: string | null;
  subject?: string | null;
  body?: string | null;
}

/** Maps the outreach agent's final `result` event to the outcome stored on the viewing. */
function toOutcome(result: Record<string, unknown>, demo: boolean): EmailOutcome {
  const attempts = (Array.isArray(result.attempts) ? result.attempts : []) as OutreachAttempt[];
  const windows = Array.isArray(result.viewing_windows)
    ? (result.viewing_windows as string[])
    : undefined;
  const call = attempts.find((a) => a.channel === "call");
  if (call) {
    return {
      channel: "call",
      state: call.status === "skipped" ? "no_contact" : call.status,
      to: call.to,
      detail: call.detail,
      windows,
      body: call.body,
    };
  }
  const email = attempts.find((a) => a.channel === "email");
  if (!email) {
    return {
      state: result.status === "failed" ? "failed" : "no_contact",
      detail: "No e-mail address on the listing.",
      windows,
    };
  }
  const state: EmailState =
    email.status === "skipped"
      ? "no_contact"
      : email.status === "dry_run" && demo
        ? "demo"
        : email.status;
  return {
    state,
    to: email.to,
    detail: email.detail,
    windows,
    subject: email.subject,
    body: email.body,
  };
}

export type OutreachEvent = AgentEvent | { type: "outcome"; outcome: EmailOutcome };

/**
 * Streams the outreach agent for one listing (POST /api/outreach/stream): it checks the
 * user's calendar, verifies the landlord's e-mail, drafts and sends the viewing request.
 * Whether it is really sent, and to whom, is decided by the server (OUTREACH_DRY_RUN,
 * OUTREACH_OVERRIDE_EMAIL); demo listings are always a dry run. Throws `BackendUnavailable`.
 *
 * With `channel: "call"` the agent phones the landlord instead: after the calendar it streams
 * a `call` event (the voice agent's brief) and the browser places the call (useVoiceCall).
 */
export async function streamOutreach(
  property: Property,
  profile: Profile,
  questions: string[] | undefined,
  signal: AbortSignal,
  onEvent: (event: OutreachEvent) => void,
  channel: OutreachChannel = "email",
): Promise<void> {
  const demo = isDemoListing(property);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/outreach/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user: { name: profile.name.trim(), email: profile.email.trim() || null },
        properties: [property],
        channels: [channel],
        calendar_url: profile.calendarUrl?.trim() || null,
        questions: questions ?? null,
        demo,
      }),
      signal,
    });
  } catch (err) {
    if (signal.aborted) throw err;
    throw new BackendUnavailable("The agent backend is offline.");
  }
  if (!res.ok) {
    throw new BackendUnavailable(
      `The agent backend returned an error (${await errorDetail(res)}).`,
    );
  }
  let finished = false;
  let failure: string | null = null;
  try {
    await readNdjson(res, (event) => {
      if (event.type === "result") {
        finished = true;
        onEvent({ type: "outcome", outcome: toOutcome(event, demo) });
      } else if (event.type === "error") {
        failure = event.detail || "unknown error";
      } else {
        onEvent(event);
      }
    });
  } catch (err) {
    if (signal.aborted) throw err;
    throw new BackendUnavailable("The connection to the outreach agent dropped.");
  }
  if (failure) throw new BackendUnavailable(`The outreach agent stopped (${failure}).`);
  if (!finished) throw new BackendUnavailable("The outreach agent stopped before finishing.");
}
