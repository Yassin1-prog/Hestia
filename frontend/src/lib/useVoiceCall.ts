"use client";

import Vapi from "@vapi-ai/web";
import { useCallback, useEffect, useRef, useState } from "react";

import type { CallBrief } from "./types";

/**
 * Live voice call with the landlord, placed from the browser with the brief the outreach agent
 * wrote (backend/outreach/live.py). It is a web call: the user plays the landlord through
 * their microphone.
 *
 * With NEXT_PUBLIC_VAPI_PUBLIC_KEY set, the call runs on Vapi (an OpenAI model + voice). Without
 * a key, or if Vapi cannot start, a scripted call runs on the browser's own speech synthesis and
 * recognition, built from the same brief.
 */

const VAPI_KEY = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY?.trim() || "";

export interface CallTurn {
  speaker: "agent" | "landlord";
  text: string;
}

export interface VoiceCall {
  /** The listing being discussed. */
  title: string;
  phase: "connecting" | "live" | "ended";
  /** Who is talking right now (drives the mic / speaker indicator). */
  talking: "agent" | "landlord" | null;
  status: string;
  transcript: CallTurn[];
  engine: "vapi" | "browser";
  /** The browser blocked the agent's audio: the panel asks for a click to turn it on. */
  needsSound: boolean;
}

/** A 0-sample WAV: playing it during a click "unlocks" the element for later playback. */
const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

/** One speech segment: Vapi sends several "final" segments per turn, they form one message. */
function appendTurn(transcript: CallTurn[], speaker: CallTurn["speaker"], text: string) {
  const last = transcript[transcript.length - 1];
  if (last?.speaker === speaker) {
    return [...transcript.slice(0, -1), { speaker, text: `${last.text} ${text}`.trim() }];
  }
  return [...transcript, { speaker, text: text.trim() }];
}

interface DailyParticipantLike {
  local?: boolean;
  user_name?: string;
  tracks?: { audio?: { persistentTrack?: MediaStreamTrack; track?: MediaStreamTrack } };
}

// Minimal Web Speech API typings (not in TypeScript's DOM lib).
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

const FEMALE_VOICES = [
  "Aria",
  "Jenny",
  "Sonia",
  "Libby",
  "Natasha",
  "Clara",
  "Molly",
  "Google UK English Female",
  "Google US English",
  "Zira",
  "Hazel",
  "Susan",
  "Samantha",
  "Victoria",
  "Karen",
  "Moira",
  "Tessa",
  "Ava",
  "Allison",
  "Female",
];
const MALE_VOICES = ["David", "Mark", "George", "James", "Richard", "Daniel", "Alex", "Male"];

/** One consistent English voice for the whole call (a female one when the browser has it). */
function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const en = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = en.length ? en : voices;
  const male = (v: SpeechSynthesisVoice) =>
    MALE_VOICES.some((m) => v.name.toLowerCase().includes(m.toLowerCase()));
  for (const name of FEMALE_VOICES) {
    const match = pool.find((v) => v.name.toLowerCase().includes(name.toLowerCase()) && !male(v));
    if (match) return match;
  }
  return pool.find((v) => !male(v)) ?? pool[0] ?? null;
}

/** The browser fallback's script: what the agent says, turn by turn, from the brief. */
function scriptFor(brief: CallBrief, clientName: string): string[] {
  const slots = brief.viewing_windows.slice(0, 2);
  return [
    brief.first_message,
    ...brief.questions.map((q, i) => (i === 0 ? `Great, thank you! ${q}` : `Got it. ${q}`)),
    slots.length
      ? `Perfect. Could ${clientName} come for a viewing on ${slots.join(", or ")}?`
      : `Perfect. When would suit you for ${clientName} to come for a viewing?`,
    `Wonderful, thank you so much. ${clientName} will follow up to confirm. Goodbye!`,
  ];
}

export function useVoiceCall(onEnded?: (call: VoiceCall) => void) {
  const [call, setCallState] = useState<VoiceCall | null>(null);
  /** The latest call, readable synchronously from event handlers. */
  const callRef = useRef<VoiceCall | null>(null);
  const setCall = useCallback((next: VoiceCall | null) => {
    callRef.current = next;
    setCallState(next);
  }, []);
  const vapiRef = useRef<Vapi | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  /** Bumped on every start / stop: callbacks from an older call are ignored. */
  const callIdRef = useRef(0);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  /** Unlocked during the user's click (`prime`), it plays the agent when the browser blocks Vapi's own. */
  const speakerRef = useRef<HTMLAudioElement | null>(null);
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;

  /**
   * Call this synchronously inside the click that asks for the call. The call itself starts a
   * few seconds later (once the outreach agent has written the brief), when the browser no
   * longer counts it as a user action and may block its audio: playing something now keeps
   * audio allowed (an unlocked <audio> element, a resumed AudioContext, the speech engine).
   */
  const prime = useCallback(() => {
    if (typeof window === "undefined") return;
    try {
      const el = speakerRef.current ?? new Audio();
      el.autoplay = true;
      el.src = SILENT_WAV;
      void el.play().catch(() => {});
      speakerRef.current = el;
    } catch {
      // no media support
    }
    try {
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctx) void new Ctx().resume().catch(() => {});
    } catch {
      // no Web Audio
    }
    if ("speechSynthesis" in window) {
      const u = new SpeechSynthesisUtterance("");
      u.volume = 0;
      window.speechSynthesis.speak(u);
    }
  }, []);

  /** Plays the agent's audio track from the Vapi (Daily) call on our own unlocked element. */
  const playAgentAudio = useCallback(async (): Promise<boolean> => {
    const daily = vapiRef.current?.getDailyCallObject() as {
      participants(): Record<string, DailyParticipantLike>;
    } | null;
    const agent = Object.values(daily?.participants() ?? {}).find(
      (p) => !p.local && p.user_name === "Vapi Speaker",
    );
    const track = agent?.tracks?.audio?.persistentTrack ?? agent?.tracks?.audio?.track;
    if (!track) return false;
    const el = speakerRef.current ?? new Audio();
    speakerRef.current = el;
    el.autoplay = true;
    el.muted = false;
    el.srcObject = new MediaStream([track]);
    try {
      await el.play();
      return true;
    } catch (err) {
      console.warn("The browser blocked the voice agent's audio:", err);
      return false;
    }
  }, []);

  const update = useCallback(
    (id: number, fn: (c: VoiceCall) => VoiceCall) => {
      if (id !== callIdRef.current || !callRef.current) return;
      setCall(fn(callRef.current));
    },
    [setCall],
  );

  // Load the browser voices early so the first sentence already uses the chosen voice.
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const load = () => {
      if (!voiceRef.current) voiceRef.current = pickVoice(window.speechSynthesis.getVoices());
    };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);

  const teardown = useCallback(() => {
    const vapi = vapiRef.current;
    vapiRef.current = null;
    try {
      vapi?.removeAllListeners();
      void vapi?.stop().catch(() => {});
    } catch {
      // already stopped
    }
    const rec = recognitionRef.current;
    recognitionRef.current = null;
    if (rec) {
      rec.onend = rec.onerror = null;
      rec.onresult = null;
      try {
        rec.stop();
      } catch {
        // not listening
      }
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    const speaker = speakerRef.current;
    if (speaker?.srcObject) {
      speaker.pause();
      speaker.srcObject = null;
    }
  }, []);

  useEffect(() => teardown, [teardown]);

  const end = useCallback(
    (id: number, status = "Call ended") => {
      if (id !== callIdRef.current) return;
      teardown();
      const c = callRef.current;
      if (!c || c.phase === "ended") return;
      const ended: VoiceCall = { ...c, phase: "ended", talking: null, needsSound: false, status };
      callRef.current = ended;
      setCall(ended);
      onEndedRef.current?.(ended);
    },
    [teardown, setCall],
  );

  /** The panel's "Turn on sound" button (a click, so the browser allows playback). */
  const enableSound = useCallback(async () => {
    const id = callIdRef.current;
    const ok = await playAgentAudio();
    update(id, (c) => ({ ...c, needsSound: !ok }));
  }, [playAgentAudio, update]);

  /** Hangs up (the panel stays open with the transcript until `dismiss`). */
  const stop = useCallback(() => end(callIdRef.current), [end]);

  const dismiss = useCallback(() => {
    end(callIdRef.current);
    callIdRef.current += 1;
    setCall(null);
  }, [end, setCall]);

  const runBrowserCall = useCallback(
    async (id: number, brief: CallBrief, clientName: string) => {
      update(id, (c) => ({ ...c, engine: "browser", status: "Calling in your browser" }));
      const speech = typeof window !== "undefined" && "speechSynthesis" in window;
      if (speech && !voiceRef.current) {
        await new Promise((r) => setTimeout(r, 400));
        voiceRef.current = pickVoice(window.speechSynthesis.getVoices());
      }
      try {
        await navigator.mediaDevices?.getUserMedia?.({ audio: true });
      } catch {
        // No microphone: the landlord's turns are simulated below.
      }
      const w = window as unknown as {
        SpeechRecognition?: SpeechRecognitionCtor;
        webkitSpeechRecognition?: SpeechRecognitionCtor;
      };
      const Recognition = w.SpeechRecognition ?? w.webkitSpeechRecognition;
      const live = () => id === callIdRef.current;

      const say = (text: string) =>
        new Promise<void>((resolve) => {
          if (!live()) return resolve();
          update(id, (c) => ({
            ...c,
            phase: "live",
            talking: "agent",
            status: "Agent is speaking",
            transcript: [...c.transcript, { speaker: "agent", text }],
          }));
          if (!speech) return void setTimeout(resolve, 2500);
          window.speechSynthesis.cancel();
          const u = new SpeechSynthesisUtterance(text);
          u.rate = 0.98;
          u.pitch = 1.05;
          if (voiceRef.current) {
            u.voice = voiceRef.current;
            u.lang = voiceRef.current.lang;
          } else {
            u.lang = "en-US";
          }
          u.onend = u.onerror = () => resolve();
          window.speechSynthesis.speak(u);
        });

      const listen = () =>
        new Promise<string>((resolve) => {
          if (!live()) return resolve("");
          update(id, (c) => ({
            ...c,
            talking: "landlord",
            status: "Your turn: answer as the landlord",
          }));
          if (!Recognition) return void setTimeout(() => resolve("Yes, that works."), 4000);
          let done = false;
          const finish = (text: string) => {
            if (done) return;
            done = true;
            recognitionRef.current = null;
            resolve(text);
          };
          try {
            const rec = new Recognition();
            recognitionRef.current = rec;
            rec.lang = "en-US";
            rec.interimResults = false;
            rec.maxAlternatives = 1;
            rec.onresult = (e) => finish(e.results?.[0]?.[0]?.transcript || "");
            rec.onerror = () => finish("");
            rec.onend = () => finish("");
            rec.start();
          } catch {
            setTimeout(() => finish("Yes, that works."), 4000);
          }
        });

      const lines = scriptFor(brief, clientName);
      for (let i = 0; i < lines.length; i++) {
        await say(lines[i]);
        if (!live()) return;
        if (i === lines.length - 1) break;
        const reply = await listen();
        if (!live()) return;
        update(id, (c) => ({
          ...c,
          transcript: [
            ...c.transcript,
            { speaker: "landlord", text: reply || "(no answer heard)" },
          ],
        }));
        await new Promise((r) => setTimeout(r, 400));
      }
      setTimeout(() => end(id), 1200);
    },
    [update, end],
  );

  /** Places the call. Any call already in progress is hung up first. */
  const start = useCallback(
    async (title: string, brief: CallBrief, clientName: string) => {
      teardown();
      const id = ++callIdRef.current;
      setCall({
        title,
        phase: "connecting",
        talking: null,
        status: "Connecting the voice agent",
        transcript: [],
        engine: VAPI_KEY ? "vapi" : "browser",
        needsSound: false,
      });

      if (!VAPI_KEY) return runBrowserCall(id, brief, clientName);

      let started = false;
      const onError = (err: unknown) => {
        if (id !== callIdRef.current) return;
        // The browser blocked playback (autoplay policy): the call itself is fine. Play the
        // agent's track on the element unlocked during the click, or ask for a click.
        if ((err as { type?: string } | null)?.type === "audio-start-failed") {
          void playAgentAudio().then((ok) => update(id, (c) => ({ ...c, needsSound: !ok })));
          return;
        }
        // Once connected, Vapi reports a real hang-up with `call-end`; other errors are not fatal.
        if (started) return console.warn("Vapi error during the call:", err);
        console.warn("Vapi could not start the call, using the browser voice instead:", err);
        teardown();
        void runBrowserCall(id, brief, clientName);
      };
      try {
        const vapi = new Vapi(VAPI_KEY);
        vapiRef.current = vapi;
        vapi.on("call-start", () => {
          started = true;
          update(id, (c) => ({ ...c, phase: "live", status: "Connected: answer as the landlord" }));
        });
        vapi.on("speech-start", () =>
          update(id, (c) => ({ ...c, talking: "agent", status: "Agent is speaking" })),
        );
        vapi.on("speech-end", () =>
          update(id, (c) => ({
            ...c,
            talking: "landlord",
            status: "Your turn: answer as the landlord",
          })),
        );
        vapi.on(
          "message",
          (msg: { type?: string; transcriptType?: string; role?: string; transcript?: string }) => {
            if (msg?.type !== "transcript" || msg.transcriptType !== "final" || !msg.transcript)
              return;
            const speaker = msg.role === "assistant" ? "agent" : "landlord";
            const text = msg.transcript;
            update(id, (c) => ({ ...c, transcript: appendTurn(c.transcript, speaker, text) }));
          },
        );
        vapi.on("call-end", () => end(id));
        vapi.on("error", onError);
        await vapi.start({
          name: "Domus AI landlord call",
          model: {
            provider: "openai",
            model: "gpt-4o-mini",
            messages: [{ role: "system", content: brief.system_prompt }],
          },
          voice: { provider: "openai", voiceId: "nova" },
          firstMessage: brief.first_message,
          // Laptop speakers + mic: a stray word or the agent's own echo must not cut it off
          // mid-sentence (which splits its answer into fragments).
          stopSpeakingPlan: { numWords: 2, voiceSeconds: 0.3 },
          // Let the landlord finish a sentence before the agent answers.
          startSpeakingPlan: { waitSeconds: 0.6 },
        });
      } catch (err) {
        onError(err);
      }
    },
    [teardown, runBrowserCall, update, end, setCall, playAgentAudio],
  );

  return { call, prime, start, stop, dismiss, enableSound };
}
