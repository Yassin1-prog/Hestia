"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export const QUICK_CHIPS = [
  "Pet-friendly penthouse in central Athens",
  "Student opportunities near NTUA campus",
  "Bright two-bedroom in Pangrati with a home office",
  "Quiet studio under €450 near a metro station",
];

interface HeroProps {
  onSubmit: (query: string) => void;
}

export function Hero({ onSubmit }: HeroProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => ref.current?.focus(), []);

  function submit(text = value) {
    const query = text.trim();
    if (query) onSubmit(query);
  }

  return (
    <section className="hero">
      <div className="hero-inner">
        <p className="eyebrow">
          <span className="eyebrow-dot" />
          Searching Spitogatos, screening scams, contacting landlords
        </p>
        <h1 className="hero-title">
          Describe the home.
          <br />
          <span className="hero-title-muted">The agent does the rest.</span>
        </h1>

        <form
          className="prompt"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            ref={ref}
            className="prompt-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                submit();
              }
            }}
            rows={2}
            aria-label="Describe the home you are looking for"
          />
          <div className="prompt-footer">
            <span className="prompt-hint">
              <kbd>Enter</kbd> to send · <kbd>Shift</kbd> + <kbd>Enter</kbd> new line
            </span>
            <button
              type="submit"
              className="prompt-send"
              disabled={!value.trim()}
              aria-label="Start search"
            >
              <ArrowUp size={18} strokeWidth={2} />
            </button>
          </div>
        </form>

        <div className="chips" aria-label="Example searches">
          {QUICK_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              className="chip"
              onClick={() => {
                setValue(chip);
                submit(chip);
              }}
            >
              {chip}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
