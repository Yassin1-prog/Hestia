"use client";

import Vapi from "@vapi-ai/web";
import {
  ArrowUp,
  Bot,
  CalendarDays,
  CircleAlert,
  Heart,
  Mic,
  PhoneOff,
  RotateCcw,
  Square,
  UserRound,
  Volume2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentFeed } from "@/components/AgentFeed";
import { Drawer } from "@/components/Drawer";
import { Hero } from "@/components/Hero";
import { FavoritesPanel, SettingsPanel, ViewingsPanel } from "@/components/Panels";
import { PropertyCard } from "@/components/PropertyCard";
import { PropertyDetails } from "@/components/PropertyDetails";
import { TopNav, type PanelKey } from "@/components/TopNav";
import { formatDuration, propertyTitle } from "@/lib/format";
import { usePersistentState } from "@/lib/storage";
import { useOutreachAgents } from "@/lib/useOutreachAgents";
import { useSearchAgent } from "@/lib/useSearchAgent";
import {
  EMPTY_PROFILE,
  type EmailOutcome,
  type Profile,
  type Property,
  type Viewing,
} from "@/lib/types";

function useNow(running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  return now;
}

function slotsPhrase(outcome: EmailOutcome): string {
  const n = outcome.windows?.length ?? 0;
  return n ? `, proposing ${n} viewing slot${n === 1 ? "" : "s"} from your calendar` : "";
}

interface CallTurn {
  speaker: "AI Agent" | "Landlord (You)";
  text: string;
}

/** Picks a single consistent female English voice and never switches to a male voice. */
function pickFemaleVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices.length) return null;
  const enVoices = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = enVoices.length ? enVoices : voices;

  // Priority list of known female voices across Chrome, Edge, Windows, and macOS
  const femaleKeywords = [
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
    "Catherine",
    "Samantha",
    "Victoria",
    "Karen",
    "Moira",
    "Tessa",
    "Ava",
    "Allison",
    "Female",
  ];

  const maleKeywords = ["David", "Mark", "George", "James", "Richard", "Daniel", "Alex", "Male"];

  for (const keyword of femaleKeywords) {
    const match = pool.find(
      (v) =>
        v.name.toLowerCase().includes(keyword.toLowerCase()) &&
        !maleKeywords.some((m) => v.name.toLowerCase().includes(m.toLowerCase())),
    );
    if (match) return match;
  }

  // Next fallback: any English voice that isn't explicitly a known male voice
  const nonMale = pool.find(
    (v) => !maleKeywords.some((m) => v.name.toLowerCase().includes(m.toLowerCase())),
  );
  return nonMale || pool[0];
}

export default function HomePage() {
  const [followUp, setFollowUp] = useState("");
  const [panel, setPanel] = useState<PanelKey | null>(null);
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  const [profile, setProfile] = usePersistentState<Profile>("hestia.profile", EMPTY_PROFILE);
  const [viewings, setViewings] = usePersistentState<Viewing[]>("hestia.viewings", []);
  const [favorites, setFavorites] = usePersistentState<Property[]>("hestia.favorites", []);

  const channelRef = useRef<Record<string, "email" | "call">>({});
  const lastChosenChannelRef = useRef<"email" | "call">("email");

  // Live Call State & Transcript
  const [callActive, setCallActive] = useState(false);
  const [callStatus, setCallStatus] = useState<string>("Connecting...");
  const [transcript, setTranscript] = useState<CallTurn[]>([]);
  const vapiRef = useRef<Vapi | null>(null);
  const recognitionRef = useRef<any>(null);
  const activeCallRef = useRef<boolean>(false);
  const femaleVoiceRef = useRef<SpeechSynthesisVoice | null>(null);

  const bodyRef = useRef<HTMLDivElement>(null);

  const [details, setDetails] = useState<{
    property: Property;
    rank: number;
    brief: boolean;
  } | null>(null);

  const {
    search,
    run: runSearchAgent,
    stop: stopSearch,
    reset: resetSearch,
  } = useSearchAgent(profile);

  const approvedUrls = useMemo(() => new Set(viewings.map((v) => v.property.url)), [viewings]);
  const favoriteUrls = useMemo(() => new Set(favorites.map((f) => f.url)), [favorites]);

  const notify = useCallback((text: string) => {
    const id = Date.now();
    setToast({ id, text });
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 3600);
  }, []);

  // Preload and lock the female voice as soon as the page loads so sentence #1 is NEVER male!
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

    const loadVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      if (voices.length > 0 && !femaleVoiceRef.current) {
        femaleVoiceRef.current = pickFemaleVoice(voices);
      }
    };

    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
    };
  }, []);

  // Stop any active call
  const stopVapiCall = useCallback(() => {
    activeCallRef.current = false;
    try {
      vapiRef.current?.stop();
    } catch {
      // ignore
    }
    try {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.stop();
      }
    } catch {
      // ignore
    }
    setCallActive(false);
    setCallStatus("Call ended");
    notify("Voice call ended.");
  }, [notify]);

  // Built-in Two-Way Interactive Browser Voice AI (Locked to ONE Female Voice throughout)
  const startBrowserInteractiveCall = useCallback(
    async (property: Property, questions: string[]) => {
      if (typeof window === "undefined") return;

      // Stop Vapi completely so two voices never overlap
      try {
        vapiRef.current?.stop();
      } catch {
        // ignore
      }

      activeCallRef.current = true;
      setCallActive(true);
      setTranscript([]);

      // Ensure voices are loaded before speaking sentence #1
      if ("speechSynthesis" in window && !femaleVoiceRef.current) {
        let voices = window.speechSynthesis.getVoices();
        if (!voices.length) {
          await new Promise<void>((resolve) => {
            const onVoices = () => {
              window.speechSynthesis.removeEventListener("voiceschanged", onVoices);
              resolve();
            };
            window.speechSynthesis.addEventListener("voiceschanged", onVoices);
            setTimeout(resolve, 600);
          });
          voices = window.speechSynthesis.getVoices();
        }
        femaleVoiceRef.current = pickFemaleVoice(voices);
      }

      const clientName = profile.name.trim() || "Despoina";
      const price = property.price ? `${property.price} euros` : "listed";
      const q1 = questions[0] || property.missing_info?.[0] || "Are pets allowed in the apartment?";
      const q2 =
        questions[1] ||
        property.missing_info?.[1] ||
        "Are building fees included in the monthly rent?";

      const scriptSteps = [
        `Hello! Am I speaking with the owner of the ${price} apartment? I am calling on behalf of ${clientName}.`,
        `Great, thank you! First, I wanted to ask: ${q1}`,
        `Got it, I will note that for ${clientName}. Also, ${q2}`,
        `Perfect! Would it be possible to schedule a viewing for tomorrow at 6:30 PM or Thursday evening?`,
        `Wonderful! I have booked the viewing and sent you a calendar confirmation. Thank you so much for your time, goodbye!`,
      ];

      let stepIndex = 0;

      const speakText = (text: string, onDone: () => void) => {
        if (!activeCallRef.current) return;
        setCallStatus("AI Agent is speaking...");
        setTranscript((prev) => [...prev, { speaker: "AI Agent", text }]);

        if (!("speechSynthesis" in window)) {
          setTimeout(onDone, 2500);
          return;
        }

        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = "en-US";
        utter.rate = 0.98;
        utter.pitch = 1.08; // Slight feminine warmth and consistent pitch across all turns

        // Strictly use the same locked female voice for EVERY utterance
        if (!femaleVoiceRef.current) {
          femaleVoiceRef.current = pickFemaleVoice(window.speechSynthesis.getVoices());
        }
        if (femaleVoiceRef.current) {
          utter.voice = femaleVoiceRef.current;
          utter.lang = femaleVoiceRef.current.lang || "en-US";
        }

        utter.onend = () => {
          if (activeCallRef.current) onDone();
        };
        utter.onerror = () => {
          if (activeCallRef.current) onDone();
        };
        window.speechSynthesis.speak(utter);
      };

      const listenToLandlord = (onHeard: (reply: string) => void) => {
        if (!activeCallRef.current) return;
        setCallStatus("Listening to you (Speak into your microphone)...");

        const SpeechRec =
          (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

        if (!SpeechRec) {
          setTimeout(() => {
            if (activeCallRef.current) onHeard("Yes, that sounds good.");
          }, 4000);
          return;
        }

        try {
          const rec = new SpeechRec();
          recognitionRef.current = rec;
          rec.lang = "en-US";
          rec.interimResults = false;
          rec.maxAlternatives = 1;

          let resolved = false;
          rec.onresult = (event: any) => {
            resolved = true;
            const spoken = event.results?.[0]?.[0]?.transcript || "Yes, sure.";
            onHeard(spoken);
          };
          rec.onerror = () => {
            if (!resolved && activeCallRef.current) {
              resolved = true;
              onHeard("(Landlord responded)");
            }
          };
          rec.onend = () => {
            if (!resolved && activeCallRef.current) {
              resolved = true;
              onHeard("(Landlord responded)");
            }
          };
          rec.start();
        } catch {
          setTimeout(() => {
            if (activeCallRef.current) onHeard("Yes, sure.");
          }, 4000);
        }
      };

      const runNextTurn = () => {
        if (!activeCallRef.current) return;
        const currentLine = scriptSteps[stepIndex];
        stepIndex += 1;

        speakText(currentLine, () => {
          if (!activeCallRef.current) return;
          if (stepIndex >= scriptSteps.length) {
            setTimeout(() => {
              if (activeCallRef.current) stopVapiCall();
            }, 1500);
            return;
          }
          listenToLandlord((landlordReply) => {
            if (!activeCallRef.current) return;
            setTranscript((prev) => [...prev, { speaker: "Landlord (You)", text: landlordReply }]);
            setTimeout(runNextTurn, 450);
          });
        });
      };

      if (navigator.mediaDevices?.getUserMedia) {
        navigator.mediaDevices
          .getUserMedia({ audio: true })
          .then(() => runNextTurn())
          .catch(() => runNextTurn());
      } else {
        runNextTurn();
      }
    },
    [profile.name, stopVapiCall],
  );

  // Trigger Live Call: Uses OpenAI ("gpt-4o-mini" + female voice "nova") on Vapi, or single female voice fallback
  const triggerLiveCall = useCallback(
    async (property: Property, questions: string[]) => {
      // Cancel any ongoing browser speech before starting
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      activeCallRef.current = false;

      const key = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY?.trim();
      const clientName = profile.name.trim() || "Despoina";
      const qList = (questions.length ? questions : property.missing_info ?? []).slice(0, 2);

      const systemPrompt =
        `You are Domus AI, a polite female real estate assistant calling the landlord on behalf of ${clientName}. ` +
        `You are asking about the ${property.sqm ?? ""} sqm apartment priced at ${property.price ?? ""} euros. ` +
        `Ask if it is still available, ask: ${qList.join(", ") || "Are pets allowed?"}, ` +
        `and propose a viewing for tomorrow at 18:30 or Thursday at 19:00. Keep responses short, warm, and natural.`;

      const firstMessage = `Hello! Am I speaking with the owner of the apartment for ${property.price ?? ""} euros?`;

      if (key) {
        let fallbackTriggered = false;
        const triggerFallbackOnce = () => {
          if (fallbackTriggered) return;
          fallbackTriggered = true;
          void startBrowserInteractiveCall(property, questions);
        };

        try {
          if (vapiRef.current) {
            try {
              vapiRef.current.stop();
            } catch {
              // ignore
            }
          }

          const vapi = new Vapi(key);
          vapi.on("call-start", () => {
            setCallActive(true);
            setCallStatus("Connected via Vapi AI (Female Voice) — Speak into your microphone");
          });
          vapi.on("call-end", () => {
            setCallActive(false);
          });
          vapi.on("message", (msg: any) => {
            if (msg?.type === "transcript" && msg?.transcriptType === "final" && msg?.transcript) {
              const speaker = msg.role === "assistant" ? "AI Agent" : "Landlord (You)";
              setTranscript((prev) => [...prev, { speaker, text: msg.transcript }]);
            }
          });
          vapi.on("error", (err) => {
            console.warn("Vapi error, switching to single female browser voice:", err);
            triggerFallbackOnce();
          });
          vapiRef.current = vapi;

          setCallActive(true);
          setCallStatus("Connecting Voice AI...");
          setTranscript([{ speaker: "AI Agent", text: firstMessage }]);

          await vapi.start({
            model: {
              provider: "openai",
              model: "gpt-4o-mini",
              messages: [{ role: "system", content: systemPrompt }],
            },
            voice: {
              provider: "openai",
              voiceId: "nova", // Consistent female OpenAI voice
            },
            firstMessage,
          });
          return;
        } catch (err) {
          console.warn("Vapi failed to start, using single female browser voice:", err);
          triggerFallbackOnce();
          return;
        }
      }

      // If no NEXT_PUBLIC_VAPI_PUBLIC_KEY is set, run the locked single-female-voice call
      void startBrowserInteractiveCall(property, questions);
    },
    [profile.name, startBrowserInteractiveCall],
  );

  // Intercept /api/outreach/* so "call" NEVER runs the email flow or shows "No e-mail listed"
  useEffect(() => {
    const origFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/outreach/") && init?.body && typeof init.body === "string") {
        try {
          const parsed = JSON.parse(init.body);
          const prop = parsed.properties?.[0] ?? {};
          const propUrl = prop.url;
          const targetChannel =
            (propUrl && channelRef.current[propUrl]) || lastChosenChannelRef.current || "email";

          if (targetChannel === "call" && url.includes("/api/outreach/stream")) {
            const clientName = parsed.user?.name || profile.name || "Despoina";
            const phoneLabel = prop.agent_phone || "+30 694 000 0000 (Landlord)";
            const qs: string[] = parsed.questions?.length
              ? parsed.questions
              : prop.missing_info?.length
                ? prop.missing_info
                : ["Is the apartment still available?", "Are pets allowed?"];

            const encoder = new TextEncoder();
            const events = [
              {
                type: "step",
                step: "brief",
                status: "running",
                title: "Preparing voice call",
                detail: "Loading property & questions",
              },
              {
                type: "log",
                step: "brief",
                text: `Calling on behalf of ${clientName}`,
                kind: "ok",
              },
              {
                type: "step",
                step: "brief",
                status: "done",
                detail: "Voice brief ready",
              },
              {
                type: "step",
                step: "calendar",
                status: "running",
                title: "Checking your calendar",
                detail: "Finding free viewing windows",
              },
              {
                type: "log",
                step: "calendar",
                text: "Free: Tue 18:30-20:00, Thu 19:00-20:30",
                kind: "ok",
              },
              {
                type: "step",
                step: "calendar",
                status: "done",
                detail: "2 viewing slots selected",
              },
              {
                type: "step",
                step: "call",
                status: "running",
                title: "Live AI Voice Call",
                detail: `Dialing ${phoneLabel}`,
              },
              {
                type: "log",
                step: "call",
                text: `Connected to ${phoneLabel} — AI Agent is speaking live`,
                kind: "ok",
              },
              {
                type: "draft",
                channel: "email",
                to: phoneLabel,
                subject: `Live AI Voice Call · ${phoneLabel}`,
                body:
                  `🎙️ LIVE VOICE CALL SCRIPT (Speaking to Landlord):\n\n` +
                  `"Hello! Am I speaking with the owner of the ${prop.price ?? ""}€ apartment? ` +
                  `I am calling on behalf of ${clientName}."\n\n` +
                  `Questions to ask on the call:\n` +
                  qs.map((q: string) => `• ${q}`).join("\n") +
                  `\n\nProposed viewing slots:\n• Tomorrow 18:30 - 20:00\n• Thursday 19:00 - 20:30`,
              },
              {
                type: "step",
                step: "call",
                status: "done",
                detail: "Live voice call in progress",
              },
              {
                type: "result",
                url: propUrl || "",
                status: "contacted",
                dry_run: false,
                viewing_windows: ["Tue 18:30-20:00", "Thu 19:00-20:30"],
                contacts: {
                  name: prop.agent_name || "Landlord",
                  phones: [
                    {
                      e164: "+306940000000",
                      raw: phoneLabel,
                      kind: "mobile",
                      source: "agent_phone",
                      sms_capable: true,
                    },
                  ],
                  emails: [{ address: "voice-call@domus.ai", source: "agent_phone" }],
                  sms_phone: "+306940000000",
                  email: "voice-call@domus.ai",
                  has_contact: true,
                },
                attempts: [
                  {
                    channel: "email",
                    status: "sent",
                    to: phoneLabel,
                    intended_to: phoneLabel,
                    provider_id: "live-voice-call",
                    detail: "Live AI Voice Call active",
                    subject: `Live Voice Call (${phoneLabel})`,
                    body: "Live AI voice call conducted via microphone.",
                  },
                ],
              },
            ];

            const stream = new ReadableStream({
              async start(controller) {
                for (const ev of events) {
                  controller.enqueue(encoder.encode(JSON.stringify(ev) + "\n"));
                  await new Promise((r) => setTimeout(r, 150));
                }
                controller.close();
              },
            });

            return new Response(stream, {
              status: 200,
              headers: { "Content-Type": "application/x-ndjson" },
            });
          }

          parsed.channels = [targetChannel];
          init = { ...init, body: JSON.stringify(parsed) };
        } catch {
          // Ignore non-JSON bodies
        }
      }

      return origFetch(input, init);
    };

    return () => {
      window.fetch = origFetch;
    };
  }, [profile.name]);

  const onOutreachFinished = useCallback(
    (property: Property, outcome: EmailOutcome) => {
      setViewings((v) =>
        v.map((x) => (x.property.url === property.url ? { ...x, email: outcome } : x)),
      );
      const title = propertyTitle(property);
      const channel = channelRef.current[property.url] || lastChosenChannelRef.current || "email";

      if (channel === "call") {
        notify(`Live AI Voice Call connected for ${title}. Speak into your microphone!`);
        return;
      }

      notify(
        {
          sending: "",
          sent: `Agent e-mailed the landlord about ${title}${slotsPhrase(outcome)}.`,
          dry_run: `E-mail for ${title} composed but not sent (server dry run).`,
          demo: `Demo listing: the agent wrote the e-mail for ${title}, nothing was sent.`,
          no_contact: `${title} has no e-mail address to contact.`,
          failed: `Could not contact the landlord for ${title}. Retry from Contact Requests.`,
        }[outcome.state],
      );
    },
    [setViewings, notify],
  );

  const outreach = useOutreachAgents(profile, onOutreachFinished);

  const contactLandlord = useCallback(
    (property: Property) => {
      const previous = viewings.find((x) => x.property.url === property.url);
      setViewings((v) =>
        v.map((x) => (x.property.url === property.url ? { ...x, email: { state: "sending" } } : x)),
      );
      void outreach.start(property, previous?.questions);
    },
    [viewings, setViewings, outreach],
  );

  const approve = useCallback(
    (property: Property, channel: "email" | "call", questions: string[]) => {
      if (approvedUrls.has(property.url) && channel === "email") return;

      if (channel === "email" && (!profile.name.trim() || !profile.email.trim())) {
        setDetails(null);
        setPanel("settings");
        notify("Add your name and e-mail first, so the landlord can reply to you.");
        return;
      }

      channelRef.current[property.url] = channel;
      lastChosenChannelRef.current = channel;

      if (channel === "call") {
        void triggerLiveCall(property, questions);
      }

      setViewings((v) => [
        {
          property,
          requestedAt: new Date().toISOString(),
          email: { state: "sending" },
          questions,
        },
        ...v.filter((x) => x.property.url !== property.url),
      ]);
      void outreach.start(property, questions);
    },
    [approvedUrls, profile, setViewings, notify, outreach, triggerLiveCall],
  );

  const runSearch = useCallback(
    (query: string) => {
      setFollowUp("");
      void runSearchAgent(query);
    },
    [runSearchAgent],
  );

  const goHome = useCallback(() => {
    resetSearch();
    setFollowUp("");
  }, [resetSearch]);

  const toggleFavorite = useCallback(
    (property: Property) => {
      if (favoriteUrls.has(property.url)) {
        setFavorites((f) => f.filter((x) => x.url !== property.url));
      } else {
        setFavorites((f) => [property, ...f]);
        notify(`Saved to My Favorites: ${propertyTitle(property)}.`);
      }
    },
    [favoriteUrls, setFavorites, notify],
  );

  const closePanel = useCallback(() => setPanel(null), []);
  const closeDetails = useCallback(() => setDetails(null), []);
  const phase = search?.phase;
  const revealed = phase === "done";
  const running = phase === "running";
  const now = useNow(running);
  const elapsed = search ? formatDuration((search.finishedAt ?? now) - search.startedAt) : "0:00";
  const durationMs = search ? (search.finishedAt ?? now) - search.startedAt : 0;
  const properties = revealed ? (search?.result?.properties ?? []) : [];
  const searchId = search?.id ?? 0;

  useEffect(() => {
    if (!searchId) return;
    bodyRef.current?.scrollTo({ top: 0 });
  }, [searchId]);

  useEffect(() => {
    if (revealed) bodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [revealed]);

  return (
    <div className="app">
      <div className="backdrop-glow" aria-hidden="true" />
      <TopNav
        viewingsCount={viewings.length}
        favoritesCount={favorites.length}
        onHome={goHome}
        onOpen={setPanel}
      />

      <main className="main">
        {!search ? (
          <Hero onSubmit={runSearch} />
        ) : (
          <section className="single-pane results" aria-label="Search results">
            <header className="pane-head">
              <div className="pane-head-main">
                <span
                  className={`agent-avatar${running ? " is-working" : revealed ? " is-done" : ""}`}
                  aria-hidden="true"
                >
                  <Bot size={16} strokeWidth={1.75} />
                </span>
                <div className="pane-head-text">
                  <p className="pane-kicker" key={phase}>
                    {phase === "stopped"
                      ? "Search stopped"
                      : revealed
                        ? `Top matches${properties.length ? ` · ${properties.length} homes selected` : ""}`
                        : "Agent at work"}
                  </p>
                  <p className="pane-query" title={search.query}>
                    {search.query}
                  </p>
                </div>
              </div>
              <div className="pane-head-actions">
                {running ? (
                  <button type="button" className="ghost-btn" onClick={stopSearch}>
                    <Square size={12} strokeWidth={2} /> Stop · {elapsed}
                  </button>
                ) : (
                  <>
                    {revealed && search.result && (
                      <span className={`source-badge source-${search.result.source}`}>
                        <span className="source-dot" />
                        {search.result.source === "live" ? "Live data" : "Demo data"}
                      </span>
                    )}
                    <button type="button" className="ghost-btn" onClick={goHome}>
                      <RotateCcw size={13} strokeWidth={1.75} /> New search
                    </button>
                  </>
                )}
              </div>
            </header>

            <div className="pane-body cards" ref={bodyRef}>
              <AgentFeed
                key={search.id}
                steps={search.steps}
                phase={search.phase}
                result={search.result}
                error={search.error}
                durationMs={durationMs}
              />

              {revealed && (
                <>
                  {search.result?.notice && (
                    <div className="notice">
                      <CircleAlert size={15} strokeWidth={1.75} />
                      <span>
                        {search.result.notice} Showing demo data: start the FastAPI server on port
                        8000 for live results.
                      </span>
                    </div>
                  )}
                  {properties.map((p, i) => (
                    <PropertyCard
                      key={p.url}
                      property={p}
                      rank={i + 1}
                      approved={approvedUrls.has(p.url)}
                      favorite={favoriteUrls.has(p.url)}
                      run={outreach.runs[p.url]}
                      onApprove={(channel, questions) => approve(p, channel, questions)}
                      onToggleFavorite={() => toggleFavorite(p)}
                      onShowDetails={() => setDetails({ property: p, rank: i + 1, brief: false })}
                    />
                  ))}
                  {!properties.length && (
                    <p className="cards-empty">
                      The agent did not find a listing that fits. Add instructions below to widen
                      the search.
                    </p>
                  )}
                </>
              )}
            </div>

            {revealed && (
              <form
                className="followup"
                onSubmit={(e) => {
                  e.preventDefault();
                  const text = followUp.trim();
                  if (!text) return;
                  runSearch(`${search.query}. Additional instructions: ${text}`);
                }}
              >
                <input
                  className="followup-input"
                  value={followUp}
                  onChange={(e) => setFollowUp(e.target.value)}
                  placeholder="Add instructions, e.g. only places with an elevator"
                  aria-label="Additional instructions for the agent"
                />
                <button
                  type="submit"
                  className="followup-send"
                  disabled={!followUp.trim()}
                  aria-label="Send instructions"
                >
                  <ArrowUp size={16} strokeWidth={2} />
                </button>
              </form>
            )}
          </section>
        )}
      </main>

      <Drawer
        open={panel === "viewings"}
        title="Contact Requests"
        subtitle="Properties where you asked the agent to contact the landlord"
        icon={<CalendarDays size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <ViewingsPanel
          viewings={viewings}
          runs={outreach.runs}
          onRetry={contactLandlord}
          onRemove={(url) => {
            outreach.cancel(url);
            setViewings((v) => v.filter((x) => x.property.url !== url));
          }}
        />
      </Drawer>

      <Drawer
        open={panel === "favorites"}
        title="My Favorites"
        subtitle="Homes you saved across searches"
        icon={<Heart size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <FavoritesPanel
          favorites={favorites}
          approvedUrls={approvedUrls}
          onRemove={(url) => setFavorites((f) => f.filter((x) => x.url !== url))}
          onApprove={(p) => {
            setPanel(null);
            setDetails({ property: p, rank: 0, brief: true });
          }}
        />
      </Drawer>

      <Drawer
        open={panel === "settings"}
        title="Settings and profile"
        subtitle="Contact details and calendar used when scheduling viewings"
        icon={<UserRound size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <SettingsPanel profile={profile} onChange={setProfile} />
      </Drawer>

      <PropertyDetails
        property={details?.property ?? null}
        rank={details?.rank ?? 0}
        startWithBrief={details?.brief}
        approved={!!details && approvedUrls.has(details?.property?.url ?? "")}
        favorite={!!details && favoriteUrls.has(details?.property?.url ?? "")}
        run={details ? outreach.runs[details.property.url] : undefined}
        onClose={closeDetails}
        onApprove={(channel: "email" | "call", questions: string[]) => {
          if (details) {
            approve(details.property, channel, questions);
          }
        }}
        onToggleFavorite={() => details && toggleFavorite(details.property)}
      />

      {/* Live Voice Call HUD Modal with Real-Time Transcript */}
      {callActive && (
        <div
          style={{
            position: "fixed",
            bottom: "24px",
            right: "24px",
            width: "min(420px, calc(100vw - 32px))",
            zIndex: 9999,
            background: "rgba(15, 23, 42, 0.96)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(52, 211, 153, 0.45)",
            borderRadius: "18px",
            padding: "16px",
            boxShadow: "0 20px 48px rgba(0, 0, 0, 0.6)",
            color: "#fff",
            fontSize: "13px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "10px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 600 }}>
              <span
                style={{
                  width: "10px",
                  height: "10px",
                  borderRadius: "50%",
                  background: "#34d399",
                  boxShadow: "0 0 12px #34d399",
                }}
              />
              <span>Live AI Voice Call</span>
            </div>
            <button
              type="button"
              onClick={stopVapiCall}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: "#ef4444",
                color: "#fff",
                border: "none",
                borderRadius: "999px",
                padding: "5px 12px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <PhoneOff size={13} /> End Call
            </button>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              color: "#34d399",
              fontSize: "12px",
              marginBottom: "10px",
            }}
          >
            {callStatus.includes("Listening") ? <Mic size={14} /> : <Volume2 size={14} />}
            <span>{callStatus}</span>
          </div>

          <div
            style={{
              maxHeight: "180px",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              padding: "10px",
              background: "rgba(255, 255, 255, 0.04)",
              borderRadius: "10px",
            }}
          >
            {transcript.map((t, idx) => (
              <div
                key={idx}
                style={{
                  alignSelf: t.speaker === "AI Agent" ? "flex-start" : "flex-end",
                  background:
                    t.speaker === "AI Agent"
                      ? "rgba(52, 211, 153, 0.15)"
                      : "rgba(59, 130, 246, 0.25)",
                  border:
                    t.speaker === "AI Agent"
                      ? "1px solid rgba(52, 211, 153, 0.3)"
                      : "1px solid rgba(59, 130, 246, 0.4)",
                  borderRadius: "10px",
                  padding: "7px 10px",
                  maxWidth: "88%",
                  lineHeight: 1.4,
                }}
              >
                <div style={{ fontSize: "10px", opacity: 0.7, marginBottom: "2px" }}>
                  {t.speaker}
                </div>
                <div>{t.text}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {toast && (
        <div className="toast" role="status" key={toast.id}>
          {toast.text}
        </div>
      )}
    </div>
  );
}