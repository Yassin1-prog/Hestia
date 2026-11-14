"use client";

import { ArrowUp, Check, CircleAlert, LoaderCircle, RotateCcw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { formatPrice, propertyLocation, propertyTitle, scoreLabel } from "@/lib/format";
import type { SearchResult } from "@/lib/types";

interface Step {
  title: string;
  running: string;
  done: (r: SearchResult | null, constraints: number) => string;
}

/** Mirrors the stages of `run_search_pipeline` in backend/agent.py. */
const STEPS: Step[] = [
  {
    title: "Reading your request",
    running: "Extracting area, budget and must-haves",
    done: (_, n) =>
      n > 0
        ? `Merged with ${n} saved preference${n === 1 ? "" : "s"}`
        : "Area, budget and must-haves extracted",
  },
  {
    title: "Building the search",
    running: "Writing a filtered Spitogatos search URL",
    done: () => "Spitogatos search ready",
  },
  {
    title: "Scanning listings",
    running: "Reading every listing on the results page",
    done: (r) =>
      r?.stats ? `Scanned ${r.stats.scanned} listings` : "Read every listing on the results page",
  },
  {
    title: "Filtering and ranking",
    running: "Scoring each listing against your constraints",
    done: (r) =>
      r?.stats
        ? `Rejected ${r.stats.rejected}` +
          (r.stats.rejectReason ? ` due to ${r.stats.rejectReason}` : "")
        : "Scored every listing against your constraints",
  },
  {
    title: "Inspecting the shortlist",
    running: "Visiting the best listings for contacts and missing details",
    done: (r) =>
      r?.properties.length
        ? `Found landlord contacts and open questions for ${r.properties.length} listings`
        : "Nothing left to inspect",
  },
  {
    title: "Selecting the top matches",
    running: "Final scoring",
    done: (r) =>
      r?.properties.length
        ? `Selected the top ${r.properties.length}, best match ${scoreLabel(r.properties[0].agentic_score)}/10`
        : "No listing passed the filters",
  },
];

/** Steps advance on a timer while waiting; the last one waits for the real response. */
const STEP_INTERVAL_MS = 1600;
/** Live results arrive after a long wait, so finish briskly. Demo data arrives instantly,
 * so keep a readable pace for the thought process. */
const FINISH_INTERVAL_MS = 320;
const DEMO_INTERVAL_MS = 1050;
const WAIT_AT = STEPS.length - 2;

function useElapsed(running: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [running]);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function useTypewriter(text: string, enabled: boolean) {
  const words = text.split(" ");
  const total = words.length;
  const [count, setCount] = useState(0);
  useEffect(() => {
    setCount(0);
    if (!enabled) return;
    let shown = 0;
    const id = setInterval(() => {
      shown += 2;
      setCount(shown);
      if (shown >= total) clearInterval(id);
    }, 30);
    return () => clearInterval(id);
  }, [text, enabled, total]);
  return { shown: words.slice(0, count).join(" "), finished: count >= words.length };
}

interface AgentFeedProps {
  query: string;
  result: SearchResult | null;
  error: string | null;
  constraintsCount: number;
  onFollowUp: (instructions: string) => void;
  onStop: () => void;
  onNewSearch: () => void;
  onFocusProperty: (rank: number) => void;
  /** Called once the thought process has played out and the conclusion is shown. */
  onComplete: () => void;
}

export function AgentFeed({
  query,
  result,
  error,
  constraintsCount,
  onFollowUp,
  onStop,
  onNewSearch,
  onFocusProperty,
  onComplete,
}: AgentFeedProps) {
  const [active, setActive] = useState(0);
  const [followUp, setFollowUp] = useState("");
  const finished = active >= STEPS.length;
  const working = !finished && !error;
  const elapsed = useElapsed(working);
  const reply = useTypewriter(result?.reply ?? "", finished && !!result);

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
    if (finished && result) onComplete();
  }, [finished, result, onComplete]);

  // Keep the newest step / conclusion text in view as the feed grows.
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [active, reply.shown, reply.finished, error]);

  function submitFollowUp() {
    const text = followUp.trim();
    if (!text) return;
    setFollowUp("");
    onFollowUp(text);
  }

  return (
    <section className="feed" aria-label="Agent feed">
      <header className="pane-head">
        <div>
          <p className="pane-kicker">Agent feed</p>
          <p className="pane-query" title={query}>
            {query}
          </p>
        </div>
        {working ? (
          <button type="button" className="ghost-btn" onClick={onStop}>
            <Square size={12} strokeWidth={2} /> Stop · {elapsed}
          </button>
        ) : (
          <button type="button" className="ghost-btn" onClick={onNewSearch}>
            <RotateCcw size={13} strokeWidth={1.75} /> New search
          </button>
        )}
      </header>

      <div className="pane-body" ref={bodyRef}>
        <ol className="steps">
          {STEPS.map((step, i) => {
            if (i > active) return null;
            const state = i < active ? "done" : error ? "failed" : "running";
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
                <div>
                  <p className="step-title">{step.title}</p>
                  <p className="step-detail">
                    {state === "done" ? step.done(result, constraintsCount) : step.running}
                  </p>
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

        {finished && result && (
          <div className="answer">
            {result.notice && (
              <div className="notice">
                <CircleAlert size={15} strokeWidth={1.75} />
                <span>
                  Showing demo data. {result.notice} Start the FastAPI server on port 8000 for live
                  results.
                </span>
              </div>
            )}
            <p className="answer-kicker">Agent conclusion</p>
            <p className="answer-text">
              {reply.shown}
              {!reply.finished && <span className="caret" />}
            </p>

            {reply.finished && result.properties.length > 0 && (
              <ul className="overview">
                {result.properties.map((p, i) => (
                  <li key={p.url}>
                    <button type="button" onClick={() => onFocusProperty(i + 1)}>
                      <span className="overview-rank">{String(i + 1).padStart(2, "0")}</span>
                      <span className="overview-main">
                        <span className="overview-title">{propertyTitle(p)}</span>
                        <span className="overview-sub">
                          {propertyLocation(p)} · {formatPrice(p.price)}
                        </span>
                      </span>
                      <span className="overview-score">{scoreLabel(p.agentic_score)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <form
        className="followup"
        onSubmit={(e) => {
          e.preventDefault();
          submitFollowUp();
        }}
      >
        <input
          className="followup-input"
          value={followUp}
          onChange={(e) => setFollowUp(e.target.value)}
          placeholder={
            working
              ? "The agent is working..."
              : "Add instructions, e.g. only places with an elevator"
          }
          disabled={working}
          aria-label="Additional instructions for the agent"
        />
        <button
          type="submit"
          className="followup-send"
          disabled={working || !followUp.trim()}
          aria-label="Send instructions"
        >
          <ArrowUp size={16} strokeWidth={2} />
        </button>
      </form>
    </section>
  );
}
