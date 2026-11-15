"use client";

import { Bot, CalendarCheck, Check, ChevronDown, Mail } from "lucide-react";
import { useEffect, useState } from "react";

import { AgentSteps } from "@/components/AgentSteps";
import { formatDuration, isScamLockedOutcome } from "@/lib/format";
import type { EmailDraft, EmailOutcome, OutreachRun } from "@/lib/types";

/** The body types itself out in about this long, whatever its length. */
const TYPE_DURATION_MS = 1900;
const TYPE_TICK_MS = 30;

function useTypewriter(text: string, animate: boolean): string {
  const [shown, setShown] = useState(animate ? 0 : text.length);
  useEffect(() => {
    if (!animate) {
      setShown(text.length);
      return;
    }
    setShown(0);
    const step = Math.max(1, Math.ceil(text.length / (TYPE_DURATION_MS / TYPE_TICK_MS)));
    const id = setInterval(() => {
      setShown((n) => {
        if (n + step >= text.length) clearInterval(id);
        return Math.min(text.length, n + step);
      });
    }, TYPE_TICK_MS);
    return () => clearInterval(id);
  }, [text, animate]);
  return text.slice(0, shown);
}

export function EmailDraftView({ draft, animate }: { draft: EmailDraft; animate: boolean }) {
  const body = useTypewriter(draft.body, animate);
  const typing = body.length < draft.body.length;
  return (
    <div className="email-draft">
      <div className="email-draft-head">
        <p>
          <span>To</span>
          {draft.to}
        </p>
        <p>
          <span>Subject</span>
          {draft.subject}
        </p>
      </div>
      <pre className="email-draft-body">
        {body}
        {typing && <span className="caret" />}
      </pre>
    </div>
  );
}

export function outcomeText(outcome: EmailOutcome | undefined): { text: string; tone: string } {
  const scamLocked = isScamLockedOutcome(outcome);
  if (outcome?.channel === "call") {
    switch (outcome.state) {
      case "sending":
        return { text: "The agent is calling the landlord", tone: "pending" };
      case "sent":
      case "demo":
        return { text: "Voice call placed with the landlord", tone: "ok" };
      case "dry_run":
        return scamLocked
          ? { text: "Call not placed (Oumi Iris scam lock)", tone: "warn" }
          : { text: "Call not placed (server dry run)", tone: "muted" };
      case "no_contact":
        return { text: `Call not placed${outcome.detail ? `: ${outcome.detail}` : ""}`, tone: "warn" };
      case "failed":
        return { text: `Call failed${outcome.detail ? `: ${outcome.detail}` : ""}`, tone: "error" };
    }
  }
  switch (outcome?.state) {
    case "sending":
      return { text: "The agent is contacting the landlord", tone: "pending" };
    case "sent":
      return { text: `E-mail sent${outcome.to ? ` to ${outcome.to}` : ""}`, tone: "ok" };
    case "dry_run":
      return scamLocked
        ? { text: "E-mail drafted, not sent (Oumi Iris scam lock)", tone: "warn" }
        : { text: "E-mail composed, not sent (server dry run)", tone: "muted" };
    case "demo":
      return scamLocked
        ? { text: "Demo listing: e-mail drafted, not sent (Oumi Iris scam lock)", tone: "warn" }
        : { text: "Demo listing: e-mail composed, not sent", tone: "muted" };
    case "no_contact":
      return { text: "No e-mail address on the listing: use the listing page", tone: "warn" };
    case "failed":
      return {
        text: `Outreach failed${outcome.detail ? `: ${outcome.detail}` : ""}`,
        tone: "error",
      };
    default:
      return { text: "Not contacted yet", tone: "muted" };
  }
}

function useTicker(running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  return now;
}

/** The outreach agent at work inside a property card; collapses to a summary when done. */
export function OutreachWorkspace({ run }: { run: OutreachRun }) {
  const running = run.phase === "running";
  const [showWork, setShowWork] = useState(false);
  const now = useTicker(running);
  const elapsed = (run.finishedAt ?? now) - run.startedAt;
  const current = [...run.steps].reverse().find((s) => s.status === "running");
  const status = outcomeText(run.outcome);
  const windows = run.outcome?.windows ?? [];
  const open = running || showWork;

  return (
    <section
      className={`outreach outreach-${run.phase}`}
      aria-label="Outreach agent"
      aria-live="polite"
    >
      <header className="outreach-head">
        <span
          className={`outreach-avatar${running ? " is-working" : ` is-${status.tone}`}`}
          key={running ? "working" : "done"}
        >
          {running || status.tone === "error" || status.tone === "warn" ? (
            <Bot size={15} strokeWidth={1.75} />
          ) : (
            <Check size={15} strokeWidth={2.25} className="check-draw" />
          )}
        </span>
        <div className="outreach-heading">
          <p className="outreach-kicker">Outreach agent</p>
          <p className="outreach-title" key={running ? (current?.title ?? "start") : status.text}>
            {running ? (current?.title ? `${current.title}…` : "Getting started…") : status.text}
          </p>
        </div>
        {running ? (
          <span className="outreach-timer">{formatDuration(elapsed)}</span>
        ) : (
          <button
            type="button"
            className="step-expand-hint outreach-toggle"
            onClick={() => setShowWork((v) => !v)}
            aria-expanded={showWork}
          >
            {showWork ? "Hide work" : "Show work"}
            <ChevronDown
              size={14}
              strokeWidth={1.75}
              className={showWork ? "step-chevron is-open" : "step-chevron"}
            />
          </button>
        )}
      </header>

      {!running && windows.length > 0 && (
        <p className="outreach-slots">
          <CalendarCheck size={13} strokeWidth={1.75} />
          Proposed {windows.join(" · ")}
        </p>
      )}

      <div className={`collapse${open ? "" : " is-collapsed"}`} aria-hidden={!open}>
        <div className="collapse-inner">
          <div className="outreach-body">
            <AgentSteps
              steps={run.steps}
              follow={running}
              compact
              renderExtra={(step) =>
                step.id === "draft" && run.draft ? (
                  <div className="outreach-draft">
                    <p className="outreach-draft-label">
                      <Mail size={13} strokeWidth={1.75} />
                      {running ? "Drafting the e-mail" : "The e-mail the agent wrote"}
                    </p>
                    <EmailDraftView draft={run.draft} animate={running} />
                  </div>
                ) : null
              }
            />
          </div>
        </div>
      </div>
    </section>
  );
}
