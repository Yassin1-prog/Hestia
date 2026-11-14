"use client";

import { Check, ChevronDown, CircleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";

import { AgentSteps } from "@/components/AgentSteps";
import { CountUp } from "@/components/CountUp";
import { formatDuration } from "@/lib/format";
import type { TraceStep } from "@/lib/trace";
import type { SearchResult } from "@/lib/types";

interface AgentFeedProps {
  steps: TraceStep[];
  /** running: live steps; done: collapsed into a one-line summary (expandable). */
  phase: "running" | "done" | "stopped";
  result: SearchResult | null;
  error: string | null;
  durationMs: number;
}

function Summary({
  steps,
  result,
  durationMs,
}: {
  steps: TraceStep[];
  result: SearchResult | null;
  durationMs: number;
}) {
  const parts: ReactNode[] = [
    <>Agent finished in {formatDuration(durationMs)}</>,
    <>
      <CountUp value={steps.length} duration={700} /> step{steps.length === 1 ? "" : "s"}
    </>,
  ];
  if (result?.stats?.scanned) {
    parts.push(
      <>
        <CountUp value={result.stats.scanned} duration={1000} /> listings scanned
      </>,
    );
  }
  if (result) {
    parts.push(
      <>
        <CountUp value={result.properties.length} duration={700} /> shortlisted
      </>,
    );
  }
  return (
    <>
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && " · "}
          {part}
        </span>
      ))}
    </>
  );
}

export function AgentFeed({ steps, phase, result, error, durationMs }: AgentFeedProps) {
  const [showWork, setShowWork] = useState(false);
  const collapsed = phase === "done" && !showWork;

  return (
    <section className={`agent-steps agent-steps-${phase}`} aria-label="Agent steps">
      {phase === "done" && (
        <button
          type="button"
          className="feed-summary"
          onClick={() => setShowWork((v) => !v)}
          aria-expanded={showWork}
        >
          <span className="feed-summary-icon">
            <Check size={12} strokeWidth={2.5} className="check-draw" />
          </span>
          <span className="feed-summary-text">
            <Summary steps={steps} result={result} durationMs={durationMs} />
          </span>
          <span className="step-expand-hint">
            {showWork ? "Hide work" : "Show work"}
            <ChevronDown
              size={14}
              strokeWidth={1.75}
              className={showWork ? "step-chevron is-open" : "step-chevron"}
            />
          </span>
        </button>
      )}

      <div className={`collapse${collapsed ? " is-collapsed" : ""}`} aria-hidden={collapsed}>
        <div className="collapse-inner">
          {!steps.length && phase === "running" ? (
            <p className="feed-booting">
              <span className="thinking-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              Starting the search agent
            </p>
          ) : (
            <AgentSteps steps={steps} follow={phase === "running"} />
          )}
        </div>
      </div>

      {error && (
        <div className="notice notice-error" role="alert">
          <CircleAlert size={15} strokeWidth={1.75} />
          <span>{error}</span>
        </div>
      )}
    </section>
  );
}
