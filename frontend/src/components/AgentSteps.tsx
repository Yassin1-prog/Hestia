"use client";

import { Check, ChevronDown, CircleAlert, LoaderCircle, Minus } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { AgentSwarm } from "@/components/AgentSwarm";
import { SiteLogo, SiteLogos } from "@/components/SiteLogo";
import type { TraceItem, TraceStep } from "@/lib/trace";

/** Delay between items when a finished step is reopened, so they replay one by one. */
const REPLAY_STAGGER_MS = 85;

function StepIcon({ status }: { status: TraceStep["status"] }) {
  return (
    <span className="step-icon">
      {status === "done" ? (
        <Check size={12} strokeWidth={2.5} className="check-draw" />
      ) : status === "running" ? (
        <LoaderCircle size={14} strokeWidth={2} className="spin" />
      ) : status === "skipped" ? (
        <Minus size={12} strokeWidth={2.5} />
      ) : (
        <CircleAlert size={13} strokeWidth={2} />
      )}
    </span>
  );
}

function ItemList({
  items,
  running,
  replay,
}: {
  items: TraceItem[];
  running: boolean;
  /** Stagger the entrance of every item (reopened step) instead of only new ones (live). */
  replay: boolean;
}) {
  return (
    <ul className={`step-items${running ? " is-live" : ""}`}>
      {items.map((item, i) => (
        <li
          key={item.id}
          className={`step-item step-item-${item.kind}`}
          style={replay ? { animationDelay: `${i * REPLAY_STAGGER_MS}ms` } : undefined}
        >
          <span className="step-item-mark" aria-hidden="true" />
          <span className="step-item-text">
            {item.source && <SiteLogo source={item.source} size={14} className="step-item-logo" />}
            {item.text}
          </span>
        </li>
      ))}
      {running && (
        <li className="step-item step-item-thinking" aria-label="Working">
          <span className="thinking-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </li>
      )}
    </ul>
  );
}

function Step({ step, extra }: { step: TraceStep; extra?: ReactNode }) {
  const running = step.status === "running";
  // `null` = follow the agent (open while running, closed once done); a click pins it.
  const [pinned, setPinned] = useState<boolean | null>(null);
  const [replayKey, setReplayKey] = useState(0);
  const open = running || (pinned ?? false);
  const count = step.items.length;

  return (
    <li className={`step step-${step.status}`}>
      <StepIcon status={step.status} />
      <div className="step-body">
        <button
          type="button"
          className="step-toggle"
          onClick={() => {
            if (running || !count) return;
            if (!open) setReplayKey((k) => k + 1);
            setPinned(!open);
          }}
          aria-expanded={open}
          disabled={running || !count}
        >
          <div>
            <p className="step-title-row">
              <span className="step-title">{step.title}</span>
              {step.sources && step.sources.length > 0 && <SiteLogos sources={step.sources} />}
            </p>
            {step.detail && (
              // Keyed so a new detail fades in instead of snapping.
              <p className="step-detail" key={step.detail}>
                {step.detail}
              </p>
            )}
          </div>
          {!running && count > 0 && (
            <span className="step-expand-hint">
              {count} action{count === 1 ? "" : "s"}
              <ChevronDown
                size={14}
                strokeWidth={1.75}
                className={open ? "step-chevron is-open" : "step-chevron"}
              />
            </span>
          )}
        </button>
        {step.agents && step.agents.length > 0 && (
          <AgentSwarm hub={step.hub} agents={step.agents} />
        )}
        {open && (count > 0 || running) && (
          <ItemList key={replayKey} items={step.items} running={running} replay={!running} />
        )}
        {extra}
      </div>
    </li>
  );
}

interface AgentStepsProps {
  steps: TraceStep[];
  /** Keep the newest action in view while the agent works. */
  follow?: boolean;
  compact?: boolean;
  /** Extra content shown under a step whether or not it is expanded (e.g. the e-mail draft). */
  renderExtra?: (step: TraceStep) => ReactNode;
}

export function AgentSteps({
  steps,
  follow = false,
  compact = false,
  renderExtra,
}: AgentStepsProps) {
  const tailRef = useRef<HTMLDivElement>(null);
  const itemCount = steps.reduce((n, s) => n + s.items.length, 0);
  const extraKey = steps.filter((s) => renderExtra?.(s)).length;

  useEffect(() => {
    if (!follow || (!steps.length && !itemCount)) return;
    tailRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [follow, steps.length, itemCount, extraKey]);

  return (
    <>
      <ol className={`steps${compact ? " steps-compact" : ""}`}>
        {steps.map((step) => (
          <Step key={step.id} step={step} extra={renderExtra?.(step)} />
        ))}
      </ol>
      <div ref={tailRef} />
    </>
  );
}
