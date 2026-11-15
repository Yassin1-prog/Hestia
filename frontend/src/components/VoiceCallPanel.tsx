"use client";

import { Mic, PhoneCall, PhoneOff, Volume2, VolumeX, X } from "lucide-react";
import { useEffect, useRef } from "react";

import type { VoiceCall } from "@/lib/useVoiceCall";

/** Floating panel for the live voice call: status, live transcript, hang up. */
export function VoiceCallPanel({
  call,
  onHangUp,
  onDismiss,
  onEnableSound,
}: {
  call: VoiceCall;
  onHangUp: () => void;
  onDismiss: () => void;
  /** The browser blocked the agent's audio until the user clicks. */
  onEnableSound: () => void;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  const ended = call.phase === "ended";

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
  }, [call.transcript.length]);

  return (
    <section className={`voice-call voice-call-${call.phase}`} aria-label="Live voice call">
      <header className="voice-call-head">
        <span className="voice-call-dot" aria-hidden="true" />
        <div className="voice-call-heading">
          <p className="voice-call-kicker">
            <PhoneCall size={12} strokeWidth={2} />
            {ended ? "Voice call" : "Live voice call"}
            {call.engine === "browser" && <span className="voice-call-engine">browser voice</span>}
          </p>
          <p className="voice-call-title" title={call.title}>
            {call.title}
          </p>
        </div>
        {ended ? (
          <button type="button" className="icon-btn" onClick={onDismiss} aria-label="Close">
            <X size={16} strokeWidth={1.75} />
          </button>
        ) : (
          <button type="button" className="voice-call-hangup" onClick={onHangUp}>
            <PhoneOff size={13} strokeWidth={2} /> End call
          </button>
        )}
      </header>

      <p className="voice-call-status" aria-live="polite">
        {call.talking === "landlord" ? (
          <Mic size={14} strokeWidth={1.75} />
        ) : (
          <Volume2 size={14} strokeWidth={1.75} />
        )}
        {call.status}
      </p>

      {call.needsSound && !ended && (
        <button type="button" className="voice-call-sound" onClick={onEnableSound}>
          <VolumeX size={14} strokeWidth={1.75} /> Your browser muted the agent: click to turn on
          sound
        </button>
      )}

      <div className="voice-call-log" ref={logRef}>
        {call.transcript.length === 0 ? (
          <p className="voice-call-empty">
            {ended ? "Nothing was said." : "Allow microphone access: you answer as the landlord."}
          </p>
        ) : (
          call.transcript.map((t, i) => (
            <div key={i} className={`voice-turn voice-turn-${t.speaker}`}>
              <span className="voice-turn-who">
                {t.speaker === "agent" ? "Agent" : "Landlord (you)"}
              </span>
              {t.text}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
