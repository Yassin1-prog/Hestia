"use client";

import {
  CalendarCheck,
  CalendarDays,
  Check,
  ExternalLink,
  Heart,
  Mail,
  RotateCw,
  Send,
  ShieldAlert,
  Trash2,
  UserRound,
} from "lucide-react";

import { EmptyState } from "@/components/Drawer";
import { ListingPhoto } from "@/components/ListingPhoto";
import { formatPrice, propertyLocation, propertyTitle, scamLabel, scoreLabel } from "@/lib/format";
import { outcomeText } from "@/components/OutreachWorkspace";
import type { OutreachRun, Profile, Property, Viewing } from "@/lib/types";

function formatRequested(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("en-GB", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function MiniProperty({ property: p }: { property: Property }) {
  return (
    <div className="mini-main mini-with-photo">
      <ListingPhoto images={p.images} alt="" className="mini-photo" />
      <div className="mini-text">
        <p className="mini-title">{propertyTitle(p)}</p>
        <p className="mini-sub">
          {propertyLocation(p)} · {formatPrice(p.price)}
          {p.sqm ? ` · ${p.sqm} m²` : ""}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// My Viewings
// ---------------------------------------------------------------------------
export function ViewingsPanel({
  viewings,
  runs,
  onRemove,
  onRetry,
}: {
  viewings: Viewing[];
  runs: Record<string, OutreachRun>;
  onRemove: (url: string) => void;
  onRetry: (p: Property) => void;
}) {
  if (!viewings.length) {
    return (
      <EmptyState
        icon={<CalendarDays size={20} strokeWidth={1.5} />}
        title="No contact requests yet"
        text="Press Ask Agent to Contact on a property card and the agent will e-mail the landlord for you."
      />
    );
  }
  return (
    <ul className="mini-list">
      {viewings.map(({ property: p, requestedAt, email }) => {
        const run = runs[p.url];
        const live = run?.phase === "running";
        const current = run?.steps.findLast((st) => st.status === "running");
        const status = live
          ? { text: `Agent at work: ${current?.title ?? "starting"}`, tone: "pending" }
          : email?.state === "sending"
            ? { text: "Interrupted before the agent finished", tone: "warn" }
            : outcomeText(email);
        const canRetry = !live && (!email || email.state === "failed" || email.state === "sending");
        return (
          <li key={p.url} className="mini">
            <div className="mini-row">
              <MiniProperty property={p} />
              <span className="mini-score">{scoreLabel(p.agentic_score)}</span>
            </div>
            <div className={`status status-${status.tone}`} key={status.text}>
              <span className="status-dot" />
              <span>
                Requested {formatRequested(requestedAt)} · {status.text}
              </span>
            </div>
            {!live && email?.windows && email.windows.length > 0 && (
              <p className="mini-slots">
                <CalendarCheck size={13} strokeWidth={1.75} />
                Proposed {email.windows.join(" · ")}
              </p>
            )}
            <div className="mini-actions">
              {canRetry && (
                <button
                  type="button"
                  className="text-btn text-btn-accent"
                  onClick={() => onRetry(p)}
                >
                  <RotateCw size={13} strokeWidth={1.75} /> {email ? "Retry" : "Contact landlord"}
                </button>
              )}
              {p.agent_email && (
                <a className="text-btn" href={`mailto:${p.agent_email}`}>
                  <Mail size={13} strokeWidth={1.75} /> {p.agent_email}
                </a>
              )}
              <a className="text-btn" href={p.url} target="_blank" rel="noreferrer">
                <ExternalLink size={13} strokeWidth={1.75} /> Listing
              </a>
              <button
                type="button"
                className="text-btn text-btn-danger"
                onClick={() => onRemove(p.url)}
              >
                <Trash2 size={13} strokeWidth={1.75} /> Cancel
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// My Favorites
// ---------------------------------------------------------------------------
export function FavoritesPanel({
  favorites,
  approvedUrls,
  onRemove,
  onApprove,
}: {
  favorites: Property[];
  approvedUrls: Set<string>;
  onRemove: (url: string) => void;
  onApprove: (p: Property) => void;
}) {
  if (!favorites.length) {
    return (
      <EmptyState
        icon={<Heart size={20} strokeWidth={1.5} />}
        title="No favorites yet"
        text="Use the heart on any property card to keep it here across searches."
      />
    );
  }
  return (
    <ul className="mini-list">
      {favorites.map((p) => {
        const approved = approvedUrls.has(p.url);
        const scamLocked = p.scam_verdict === "POSSIBLY_SCAM";
        return (
          <li key={p.url} className="mini">
            <div className="mini-row">
              <MiniProperty property={p} />
              <span className="mini-score">{scoreLabel(p.agentic_score)}</span>
            </div>
            {scamLocked && (
              <p className="mini-scam">
                <ShieldAlert size={12} strokeWidth={2} /> Oumi Iris · {scamLabel(p)}
              </p>
            )}
            {p.score_reason && <p className="mini-reason">{p.score_reason}</p>}
            <div className="mini-actions">
              <button
                type="button"
                className="text-btn text-btn-accent"
                onClick={() => onApprove(p)}
                disabled={approved}
              >
                {approved ? (
                  scamLocked ? (
                    <>
                      <ShieldAlert size={13} strokeWidth={2} /> Drafted · Not Sent
                    </>
                  ) : (
                    <>
                      <Check size={13} strokeWidth={2} /> Agent Contacting
                    </>
                  )
                ) : (
                  <>
                    <Send size={13} strokeWidth={1.75} /> Ask Agent to Contact
                  </>
                )}
              </button>
              <a className="text-btn" href={p.url} target="_blank" rel="noreferrer">
                <ExternalLink size={13} strokeWidth={1.75} /> Listing
              </a>
              <button
                type="button"
                className="text-btn text-btn-danger"
                onClick={() => onRemove(p.url)}
              >
                <Trash2 size={13} strokeWidth={1.75} /> Remove
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Settings / Profile
// ---------------------------------------------------------------------------
export function SettingsPanel({
  profile,
  onChange,
}: {
  profile: Profile;
  onChange: (profile: Profile) => void;
}) {
  return (
    <div className="settings">
      <section className="settings-section">
        <h3 className="settings-title">Contact details</h3>
        <p className="settings-hint">
          Shared with landlords only after you approve a viewing. The agent e-mails them, and their
          replies go to this address.
        </p>
        <label className="label">
          Full name
          <input
            className="field"
            value={profile.name}
            onChange={(e) => onChange({ ...profile, name: e.target.value })}
            placeholder="Alex Papadopoulos"
            autoComplete="name"
          />
        </label>
        <label className="label">
          Email
          <input
            className="field"
            type="email"
            value={profile.email}
            onChange={(e) => onChange({ ...profile, email: e.target.value })}
            placeholder="alex@example.com"
            autoComplete="email"
          />
        </label>
      </section>

      <section className="settings-section">
        <h3 className="settings-title">Google Calendar</h3>
        <p className="settings-hint">
          The agent proposes viewing times when you are free. Paste your calendar&apos;s{" "}
          <em>secret address in iCal format</em> (Google Calendar → Settings → your calendar →
          Integrate calendar). It is read-only and only used to find free slots. Without it, the
          agent uses a sample work week.
        </p>
        <label className="label">
          Secret iCal address
          <input
            className="field"
            type="url"
            value={profile.calendarUrl ?? ""}
            onChange={(e) => onChange({ ...profile, calendarUrl: e.target.value })}
            placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
      </section>

      <p className="settings-saved">
        <UserRound size={13} strokeWidth={1.75} /> Saved automatically in this browser
      </p>
    </div>
  );
}
