"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { BackendUnavailable, isDemoListing, streamOutreach, type OutreachEvent } from "./api";
import { demoCallEvents, demoOutreachEvents, offlineOutreachEvents } from "./demoAgent";
import { applyTraceEvent, Pacer } from "./trace";
import type {
  CallBrief,
  EmailOutcome,
  OutreachChannel,
  OutreachRun,
  Profile,
  Property,
} from "./types";

/** The outreach agent is fast on the server; pace it so each action can be read. */
function gapFor(e: OutreachEvent): number {
  switch (e.type) {
    case "step":
      return e.status === "running" ? 520 : 300;
    case "log":
      return 320;
    case "draft":
      return 2300; // The e-mail types itself out (EmailDraftView) before it is sent.
    default:
      return 0;
  }
}

/**
 * One outreach agent per listing, running in parallel. `onFinished` receives the final
 * outcome (to persist it on the viewing and notify the user). On a voice call, `onCall`
 * receives the voice agent's brief so the page can place the call (useVoiceCall).
 */
export function useOutreachAgents(
  profile: Profile,
  onFinished: (property: Property, outcome: EmailOutcome) => void,
  onCall?: (property: Property, brief: CallBrief) => void,
) {
  const [runs, setRuns] = useState<Record<string, OutreachRun>>({});
  const pacers = useRef(new Map<string, Pacer<OutreachEvent>>());
  const aborts = useRef(new Map<string, AbortController>());
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;
  const onCallRef = useRef(onCall);
  onCallRef.current = onCall;

  useEffect(() => {
    const p = pacers.current;
    const a = aborts.current;
    return () => {
      p.forEach((x) => x.dispose());
      a.forEach((x) => x.abort());
    };
  }, []);

  const start = useCallback(
    async (property: Property, questions?: string[], channel: OutreachChannel = "email") => {
      const url = property.url;
      aborts.current.get(url)?.abort();
      pacers.current.get(url)?.dispose();
      const controller = new AbortController();
      aborts.current.set(url, controller);

      const update = (fn: (r: OutreachRun) => OutreachRun) =>
        setRuns((all) => (all[url] ? { ...all, [url]: fn(all[url]) } : all));
      const newPacer = () => {
        pacers.current.get(url)?.dispose();
        const pacer = new Pacer<OutreachEvent>((e) => {
          if (e.type === "call") {
            const { type: _type, ...brief } = e;
            onCallRef.current?.(property, brief);
          } else if (e.type === "draft") {
            update((r) => ({ ...r, draft: { to: e.to, subject: e.subject, body: e.body } }));
          } else if (e.type === "outcome") {
            update((r) => ({ ...r, phase: "done", finishedAt: Date.now(), outcome: e.outcome }));
            onFinishedRef.current(property, e.outcome);
          } else {
            update((r) => ({ ...r, steps: applyTraceEvent(r.steps, e) }));
          }
        }, gapFor);
        pacers.current.set(url, pacer);
        return pacer;
      };

      setRuns((all) => ({
        ...all,
        [url]: { channel, steps: [], draft: null, phase: "running", startedAt: Date.now() },
      }));
      const pacer = newPacer();
      try {
        await streamOutreach(
          property,
          profile,
          questions,
          controller.signal,
          (e) => pacer.push(e),
          channel,
        );
      } catch (err) {
        if (controller.signal.aborted || !(err instanceof BackendUnavailable)) return;
        const fallback = newPacer();
        setRuns((all) => (all[url] ? { ...all, [url]: { ...all[url], steps: [] } } : all));
        fallback.push(
          ...(!isDemoListing(property)
            ? offlineOutreachEvents(err.message)
            : channel === "call"
              ? demoCallEvents(property, profile, questions)
              : demoOutreachEvents(property, profile, questions)),
        );
      }
    },
    [profile],
  );

  const cancel = useCallback((url: string) => {
    aborts.current.get(url)?.abort();
    pacers.current.get(url)?.dispose();
    aborts.current.delete(url);
    pacers.current.delete(url);
    setRuns((all) => {
      if (!all[url]) return all;
      const next = { ...all };
      delete next[url];
      return next;
    });
  }, []);

  return { runs, start, cancel };
}
