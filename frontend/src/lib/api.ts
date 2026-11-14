import { demoResult } from "./demo";
import { propertyTitle } from "./format";
import type { Profile, Property, SearchResult, SearchStats } from "./types";

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
  return {
    ...p,
    features: Array.isArray(p.features) ? p.features : [],
    missing_info: Array.isArray(p.missing_info) ? p.missing_info : [],
    agentic_score: Number(p.agentic_score) || 0,
    score_reason: p.score_reason || "",
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
  parts.push("Approve a viewing on any card and I will contact the landlord for you.");
  return parts.join(" ");
}

/**
 * Accepts the current backend shape (`PropertyDetails[]`) and a richer future shape
 * (`{ reply, properties, stats }`).
 */
function normalize(query: string, data: unknown): SearchResult {
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
    .sort((a, b) => b.agentic_score - a.agentic_score)
    .slice(0, 3);
  return {
    query,
    reply: typeof obj.reply === "string" && obj.reply ? obj.reply : synthesizeReply(properties),
    properties,
    stats: obj.stats,
    source: "live",
  };
}

/** Calls POST /api/search; falls back to demo data if the backend is unreachable or errors. */
export async function searchProperties(
  query: string,
  profile: Profile,
  signal?: AbortSignal,
): Promise<SearchResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SEARCH_TIMEOUT_MS);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);

  try {
    const res = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: buildRequest(query, profile) }),
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      return demoResult(query, `The agent backend returned an error (${detail}).`);
    }
    return normalize(query, await res.json());
  } catch (err) {
    if (signal?.aborted) throw err;
    const reason = controller.signal.aborted
      ? "The agent backend timed out."
      : "The agent backend is offline.";
    return demoResult(query, reason);
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", onAbort);
  }
}
