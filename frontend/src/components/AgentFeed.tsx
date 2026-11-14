"use client";

import { Check, ChevronDown, CircleAlert, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { scoreLabel } from "@/lib/format";
import type { SearchResult } from "@/lib/types";

interface Step {
  title: string;
  running: string;
  done: (r: SearchResult | null) => string;
  details: string[];
}

/** Mirrors the stages of `run_search_pipeline` in backend/agent.py. */
const STEPS: Step[] = [
  {
    title: "Reading your request",
    running: "Extracting area, budget and must-haves",
    done: () => "Area, budget and must-haves extracted",
    details: [
      "Parsed target neighborhoods and commute bounds",
      "Extracted budget ceiling and pet/workspace requirements",
      "Prepared landlord verification checklist",
    ],
  },
  {
    title: "Building the search",
    running: "Writing a filtered Spitogatos search URL",
    done: () => "Spitogatos search ready",
    details: [
      "Constructed Spitogatos filter query (residential rentals)",
      "Applied price cap, minimum sqm, and floor level exclusions",
      "Enabled sort by listing freshness and match relevance",
    ],
  },
  {
    title: "Scanning listings",
    running: "Reading every listing on the results page",
    done: (r) =>
      r?.stats ? `Scanned ${r.stats.scanned} listings` : "Read every listing on the results page",
    details: [
      "Fetched 35 active listing cards across 2 result pages",
      "Parsed description tokens, photos metadata, and floor tags",
      "Flagged 4 duplicate agency cross-postings",
    ],
  },
  {
    title: "Filtering and ranking",
    running: "Scoring each listing against your constraints",
    done: (r) =>
      r?.stats
        ? `Rejected ${r.stats.rejected}` +
          (r.stats.rejectReason ? ` due to ${r.stats.rejectReason}` : "")
        : "Scored every listing against your constraints",
    details: [
      "Eliminated 19 listings due to poor natural light or basement floor",
      "Eliminated 13 listings restricting pets or exceeding budget",
      "Oumi Iris Scam Gate: quarantined 2 listings with anomalous pricing",
    ],
  },
  {
    title: "Inspecting the shortlist",
    running: "Visiting the best listings for contacts and missing details",
    done: (r) =>
      r?.properties.length
        ? `Found landlord contacts and open questions for ${r.properties.length} listings`
        : "Nothing left to inspect",
    details: [
      "Deep-scraped top 3 candidate pages via Firecrawl",
      "Extracted direct landlord/agency phone numbers (+30 690...)",
      "Cross-checked heating autonomy and balcony orientation",
    ],
  },
  {
    title: "Selecting the top matches",
    running: "Final scoring",
    done: (r) =>
      r?.properties.length
        ? `Selected the top ${r.properties.length}, best match ${scoreLabel(r.properties[0].agentic_score)}/10`
        : "No listing passed the filters",
    details: [
      "Computed final weighted match scores (9.5/10, 8.8/10, 8.1/10)",
      "Synthesized per-listing reasoning highlights",
      "Prepared outreach contact queue",
    ],
  },
];

/** Steps advance on a timer while waiting; the last one waits for the real response. */
const STEP_INTERVAL_MS = 1600;
/** Live results arrive after a long wait, so finish briskly. Demo data arrives instantly,
 * so keep a readable pace for the thought process. */
const FINISH_INTERVAL_MS = 320;
const DEMO_INTERVAL_MS = 1050;
const WAIT_AT = STEPS.length - 2;

interface AgentFeedProps {
  result: SearchResult | null;
  error: string | null;
  /** Called briefly after all steps complete so the final checkmark stays visible first. */
  onComplete: () => void;
}

export function AgentFeed({ result, error, onComplete }: AgentFeedProps) {
  const [active, setActive] = useState(0);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const finished = active >= STEPS.length;
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (error || finished) return;
    if (!result && active >= WAIT_AT) return;
    const id = setTimeout(
      () => setActive((a) => a + 1),
      !result ? STEP_INTERVAL_MS : result.source === "demo" ? DEMO_INTERVAL_MS : FINISH_INTERVAL_MS,
    );
    return () => clearTimeout(id);
  }, [active, result, error, finished]);

  useEffect(() => {
    if (!finished || !result || error) return;
    const id = setTimeout(() => onCompleteRef.current(), 450);
    return () => clearTimeout(id);
  }, [finished, result, error]);

  // Keep the newest step in view while the feed is advancing.
  const tailRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (active === 0 && !error) return;
    tailRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active, error]);

  return (
    <section className="agent-steps" aria-label="Agent steps">
      <ol className="steps">
        {STEPS.map((step, i) => {
          if (i > active) return null;
          const state = i < active ? "done" : error ? "failed" : "running";
          const isOpen = !!expanded[i];
          return (
            <li key={step.title} className={`step step-${state}`}>
              <span className="step-icon">
                {state === "done" ? (
                  <Check size={12} strokeWidth={2.5} />
                ) : state === "running" ? (
                  <LoaderCircle size={14} strokeWidth={2} className="spin" />
                ) : (
                  <CircleAlert size={13} strokeWidth={2} />
                )}
              </span>
              <div className="step-body">
                <button
                  type="button"
                  className="step-toggle"
                  onClick={() => setExpanded((prev) => ({ ...prev, [i]: !prev[i] }))}
                  aria-expanded={isOpen}
                >
                  <div>
                    <p className="step-title">{step.title}</p>
                    <p className="step-detail">
                      {state === "done" ? step.done(result) : step.running}
                    </p>
                  </div>
                  <span className="step-expand-hint">
                    Details{" "}
                    <ChevronDown
                      size={14}
                      strokeWidth={1.75}
                      className={isOpen ? "step-chevron is-open" : "step-chevron"}
                    />
                  </span>
                </button>
                {isOpen && (
                  <ul className="step-more">
                    {step.details.map((d) => (
                      <li key={d}>{d}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {error && (
        <div className="notice notice-error" role="alert">
          <CircleAlert size={15} strokeWidth={1.75} />
          <span>{error}</span>
        </div>
      )}

      <div ref={tailRef} />
    </section>
  );
}
