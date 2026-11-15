"use client";

import { Check, MessageCircleQuestion, PhoneCall, Plus, Send, ShieldAlert, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { scamWarningText } from "@/lib/format";
import type { OutreachChannel, Property } from "@/lib/types";

const DEFAULT_QUESTIONS = [
  "Is the apartment still available?",
  "What is the earliest move-in date and the minimum lease term?",
  "Are utilities / building fees included in the rent?",
];

const SUGGESTIONS = [
  "Are pets allowed?",
  "Is there an elevator?",
  "What deposit is required?",
  "Is it furnished?",
  "Is there parking?",
  "How is the apartment heated?",
  "Can I register my residence at this address?",
];

/** Matches the server's limit for user-approved questions (MAX_APPROVED_QUESTIONS). */
const MAX_QUESTIONS = 10;

interface Question {
  text: string;
  checked: boolean;
  mine: boolean;
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

interface ContactBriefProps {
  property: Property;
  /** Questions approved for this listing before (a retry), if any. */
  initial?: string[];
  /** E-mail the landlord (default) or call them: the same questions, asked on the phone. */
  channel?: OutreachChannel;
  onSend: (questions: string[]) => void;
  onCancel: () => void;
}

/**
 * The approval gate before the outreach agent writes to (or calls) a landlord: review the
 * questions it will ask, untick any, and add your own.
 */
export function ContactBrief({
  property,
  initial,
  channel = "email",
  onSend,
  onCancel,
}: ContactBriefProps) {
  const calling = channel === "call";
  const [questions, setQuestions] = useState<Question[]>(() => {
    const ranker = property.missing_info.length ? property.missing_info : DEFAULT_QUESTIONS;
    const base = ranker.map((text) => ({ text, checked: true, mine: false }));
    const extra = (initial ?? [])
      .filter((q) => !ranker.some((r) => norm(r) === norm(q)))
      .map((text) => ({ text, checked: true, mine: true }));
    if (initial?.length) {
      const chosen = new Set(initial.map(norm));
      base.forEach((q) => (q.checked = chosen.has(norm(q.text))));
    }
    return [...base, ...extra];
  });
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = questions.filter((q) => q.checked);
  const full = selected.length >= MAX_QUESTIONS;
  const scamLocked = property.scam_verdict === "POSSIBLY_SCAM";
  const suggestions = useMemo(
    () => SUGGESTIONS.filter((s) => !questions.some((q) => norm(q.text) === norm(s))).slice(0, 4),
    [questions],
  );

  const add = (text: string) => {
    const clean = text.trim().replace(/\s+/g, " ");
    if (!clean || full) return;
    const withMark = /[?.!]$/.test(clean) ? clean : `${clean}?`;
    setQuestions((qs) =>
      qs.some((q) => norm(q.text) === norm(withMark))
        ? qs.map((q) => (norm(q.text) === norm(withMark) ? { ...q, checked: true } : q))
        : [...qs, { text: withMark, checked: true, mine: true }],
    );
    setDraft("");
    inputRef.current?.focus();
  };

  return (
    <section
      className="brief"
      aria-label={calling ? "Questions to ask on the call" : "Questions for the landlord"}
    >
      <header className="brief-head">
        <MessageCircleQuestion size={15} strokeWidth={1.75} />
        <div>
          <p className="brief-title">
            {calling ? "What should the agent ask on the call?" : "What should the agent ask?"}
          </p>
          <p className="brief-sub">
            {calling
              ? "It will ask these one at a time, then propose viewing times from your calendar. "
              : "It will also propose viewing times from your calendar. "}
            Untick anything you don&apos;t need.
          </p>
        </div>
      </header>

      {scamLocked && (
        <p className="scam-warning" role="note">
          <ShieldAlert size={14} strokeWidth={2} />
          <span>{scamWarningText(property)}</span>
        </p>
      )}

      <ul className="brief-list">
        {questions.map((q, i) => (
          <li
            key={q.text}
            className={`brief-q${q.checked ? " is-on" : ""}${q.mine ? " is-mine" : ""}`}
          >
            <button
              type="button"
              className="brief-check"
              role="checkbox"
              aria-checked={q.checked}
              disabled={!q.checked && full}
              onClick={() =>
                setQuestions((qs) =>
                  qs.map((x, j) => (j === i ? { ...x, checked: !x.checked } : x)),
                )
              }
            >
              <span className="brief-box">{q.checked && <Check size={11} strokeWidth={3} />}</span>
              <span className="brief-text">{q.text}</span>
            </button>
            {q.mine ? (
              <button
                type="button"
                className="brief-remove"
                aria-label={`Remove "${q.text}"`}
                onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}
              >
                <X size={13} strokeWidth={2} />
              </button>
            ) : (
              <span className="brief-source">from the listing</span>
            )}
          </li>
        ))}
      </ul>

      <form
        className="brief-add"
        onSubmit={(e) => {
          e.preventDefault();
          add(draft);
        }}
      >
        <input
          ref={inputRef}
          className="brief-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={full ? "Question limit reached" : "Add your own question…"}
          aria-label="Add a question for the landlord"
          maxLength={200}
          disabled={full}
        />
        <button type="submit" className="brief-add-btn" disabled={!draft.trim() || full}>
          <Plus size={14} strokeWidth={2} /> Add
        </button>
      </form>

      {suggestions.length > 0 && !full && (
        <div className="brief-suggest">
          {suggestions.map((s) => (
            <button key={s} type="button" className="chip chip-small" onClick={() => add(s)}>
              <Plus size={11} strokeWidth={2} /> {s}
            </button>
          ))}
        </div>
      )}

      <footer className="brief-foot">
        <span className="brief-count">
          {selected.length
            ? `${selected.length} of ${MAX_QUESTIONS} questions`
            : "No questions: the agent will only ask for a viewing"}
        </span>
        <div className="brief-actions">
          <button type="button" className="text-btn" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="approve-btn"
            onClick={() => onSend(selected.map((q) => q.text))}
            disabled={calling && scamLocked}
            title={calling && scamLocked ? "Oumi Iris flagged this listing: no call" : undefined}
          >
            {calling ? (
              scamLocked ? (
                <>
                  <ShieldAlert size={14} strokeWidth={1.75} /> Call blocked
                </>
              ) : (
                <>
                  <PhoneCall size={14} strokeWidth={1.75} /> Start call
                </>
              )
            ) : scamLocked ? (
              <>
                <ShieldAlert size={14} strokeWidth={1.75} /> Draft e-mail only
              </>
            ) : (
              <>
                <Send size={14} strokeWidth={1.75} /> Send agent
              </>
            )}
          </button>
        </div>
      </footer>
    </section>
  );
}
