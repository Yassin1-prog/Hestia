"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { BackendUnavailable, streamSearch } from "./api";
import { demoResult } from "./demo";
import { demoSearchEvents } from "./demoAgent";
import { applyTraceEvent, failRunning, Pacer, type AgentEvent, type TraceStep } from "./trace";
import type { Profile, SearchResult } from "./types";

export interface SearchRun {
  id: number;
  query: string;
  steps: TraceStep[];
  result: SearchResult | null;
  error: string | null;
  /** running → done (steps collapse, cards appear) | stopped (by the user). */
  phase: "running" | "done" | "stopped";
  startedAt: number;
  finishedAt: number | null;
}

type FeedEvent = AgentEvent | { type: "final"; result: SearchResult } | { type: "reveal" };

/** Minimum time each event stays on screen before the next one appears. */
function gapFor(e: FeedEvent): number {
  switch (e.type) {
    case "step":
      return e.status === "running" ? 420 : 260;
    case "log":
      return 230;
    case "agent":
      return 180;
    case "final":
      return 650; // Let the last checkmark land before the steps collapse.
    default:
      return 0;
  }
}

const STOPPED = "Search stopped. Adjust your request and try again.";

export function useSearchAgent(profile: Profile) {
  const [search, setSearch] = useState<SearchRun | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pacerRef = useRef<Pacer<FeedEvent> | null>(null);
  const idRef = useRef(0);

  const halt = useCallback(() => {
    abortRef.current?.abort();
    pacerRef.current?.dispose();
    pacerRef.current = null;
  }, []);

  useEffect(() => halt, [halt]);

  const newPacer = useCallback((id: number) => {
    pacerRef.current?.dispose();
    const update = (fn: (s: SearchRun) => SearchRun) =>
      setSearch((s) => (s && s.id === id ? fn(s) : s));
    const pacer = new Pacer<FeedEvent>((e) => {
      if (e.type === "final") update((s) => ({ ...s, result: e.result }));
      else if (e.type === "reveal")
        update((s) => ({ ...s, phase: "done", finishedAt: Date.now() }));
      else update((s) => ({ ...s, steps: applyTraceEvent(s.steps, e) }));
    }, gapFor);
    pacerRef.current = pacer;
    return pacer;
  }, []);

  const run = useCallback(
    async (query: string) => {
      halt();
      const controller = new AbortController();
      abortRef.current = controller;
      const id = ++idRef.current;
      setSearch({
        id,
        query,
        steps: [],
        result: null,
        error: null,
        phase: "running",
        startedAt: Date.now(),
        finishedAt: null,
      });
      let pacer = newPacer(id);
      try {
        const result = await streamSearch(query, profile, controller.signal, (e) => pacer.push(e));
        pacer.push({ type: "final", result }, { type: "reveal" });
      } catch (err) {
        if (controller.signal.aborted || !(err instanceof BackendUnavailable)) return;
        // Live agent unavailable: replay the same pipeline on demo data, with a notice.
        pacer = newPacer(id);
        setSearch((s) => (s && s.id === id ? { ...s, steps: [] } : s));
        const result = demoResult(query, err.message);
        pacer.push(...demoSearchEvents(result), { type: "final", result }, { type: "reveal" });
      }
    },
    [profile, halt, newPacer],
  );

  const stop = useCallback(() => {
    halt();
    setSearch((s) =>
      s && s.phase === "running"
        ? { ...s, phase: "stopped", error: STOPPED, steps: failRunning(s.steps, "Stopped") }
        : s,
    );
  }, [halt]);

  const reset = useCallback(() => {
    halt();
    setSearch(null);
  }, [halt]);

  return { search, run, stop, reset };
}
