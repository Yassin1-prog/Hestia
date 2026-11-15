/**
 * Live agent progress: the NDJSON events streamed by the backend (backend/streaming.py),
 * the step list they reduce into, and a pacer that releases them one at a time so a burst
 * of events still reads as an agent working step by step.
 */

import type { CallBrief } from "./types";

export type StepStatus = "running" | "done" | "skipped" | "failed";
export type LogKind = "info" | "ok" | "warn";

export type AgentEvent =
  | {
      type: "step";
      step: string;
      status: StepStatus;
      title?: string | null;
      detail?: string | null;
      /** Sites / services this step works with (logos in the step header, see SiteLogo). */
      sources?: string[];
    }
  | { type: "log"; step: string; text: string; kind?: LogKind; source?: string }
  | {
      type: "agent";
      step: string;
      agent: string;
      label: string;
      status: StepStatus;
      detail?: string | null;
      /** The node the sub-agents report to (e.g. "Orchestrator", "Oumi Iris"). */
      hub?: string;
      /** The site this sub-agent works on (its logo is shown on the node). */
      source?: string;
    }
  | { type: "draft"; channel: string; to: string; subject: string; body: string }
  /** The voice agent's brief (backend/outreach/live.py): the browser places the call with it. */
  | ({ type: "call" } & CallBrief)
  | { type: "result"; [key: string]: unknown }
  | { type: "error"; detail?: string };

export interface TraceItem {
  id: number;
  text: string;
  kind: LogKind;
  source?: string;
}

/** A collaborating sub-agent inside a step, drawn as a node linked to the step's hub. */
export interface TraceAgent {
  id: string;
  label: string;
  status: StepStatus;
  detail: string | null;
  source?: string;
}

export interface TraceStep {
  id: string;
  title: string;
  status: StepStatus;
  detail: string | null;
  items: TraceItem[];
  hub?: string;
  agents?: TraceAgent[];
  sources?: string[];
}

let itemSeq = 0;

/** Applies one `step` / `log` / `agent` event to the step list (others leave it unchanged). */
export function applyTraceEvent(steps: TraceStep[], e: AgentEvent): TraceStep[] {
  if (e.type !== "step" && e.type !== "log" && e.type !== "agent") return steps;
  const index = steps.findIndex((s) => s.id === e.step);
  const current: TraceStep =
    index >= 0
      ? steps[index]
      : { id: e.step, title: e.step, status: "running", detail: null, items: [] };
  let next: TraceStep;
  if (e.type === "step") {
    next = {
      ...current,
      status: e.status,
      title: e.title || current.title,
      detail: e.detail ?? current.detail,
      sources: e.sources ?? current.sources,
    };
  } else if (e.type === "agent") {
    const agents = current.agents ?? [];
    const previous = agents.find((a) => a.id === e.agent);
    const agent: TraceAgent = {
      id: e.agent,
      label: e.label,
      status: e.status,
      detail: e.detail ?? previous?.detail ?? null,
      source: e.source ?? previous?.source,
    };
    const at = agents.findIndex((a) => a.id === e.agent);
    next = {
      ...current,
      hub: e.hub ?? current.hub,
      agents: at < 0 ? [...agents, agent] : agents.map((a, i) => (i === at ? agent : a)),
    };
  } else {
    next = {
      ...current,
      items: [
        ...current.items,
        { id: ++itemSeq, text: e.text, kind: e.kind ?? "info", source: e.source },
      ],
    };
  }
  if (index < 0) return [...steps, next];
  const copy = steps.slice();
  copy[index] = next;
  return copy;
}

/** Marks whatever is still running as failed (used when the user stops an agent). */
export function failRunning(steps: TraceStep[], detail: string): TraceStep[] {
  return steps.map((s) =>
    s.status === "running"
      ? {
          ...s,
          status: "failed",
          detail,
          agents: s.agents?.map((a) => (a.status === "running" ? { ...a, status: "failed" } : a)),
        }
      : s,
  );
}

/**
 * Releases queued events one at a time. After an event is applied, the next one waits at
 * least `gapFor(event)` ms. Slow live streams play in real time; bursts (and demo
 * scripts, which are pushed all at once) get a readable rhythm.
 */
export class Pacer<E> {
  private queue: E[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readyAt = 0;
  private disposed = false;

  constructor(
    private readonly apply: (event: E) => void,
    private readonly gapFor: (event: E) => number,
  ) {}

  push(...events: E[]) {
    if (this.disposed) return;
    this.queue.push(...events);
    this.pump();
  }

  dispose() {
    this.disposed = true;
    this.queue = [];
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private pump = () => {
    if (this.disposed || this.timer || !this.queue.length) return;
    const wait = this.readyAt - Date.now();
    if (wait > 0) {
      this.timer = setTimeout(() => {
        this.timer = null;
        this.pump();
      }, wait);
      return;
    }
    const event = this.queue.shift() as E;
    this.readyAt = Date.now() + this.gapFor(event);
    this.apply(event);
    this.pump();
  };
}

/** Reads an NDJSON response body, calling `onEvent` for every line. */
export async function readNdjson(res: Response, onEvent: (event: AgentEvent) => void) {
  if (!res.body) throw new Error("The agent backend sent an empty stream.");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const flush = (line: string) => {
    const text = line.trim();
    if (!text) return;
    try {
      onEvent(JSON.parse(text) as AgentEvent);
    } catch {
      /* ignore a malformed line */
    }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      flush(buffer.slice(0, nl));
      buffer = buffer.slice(nl + 1);
    }
  }
  flush(buffer + decoder.decode());
}
