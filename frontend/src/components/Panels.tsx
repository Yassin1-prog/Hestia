"use client";

import {
  CalendarDays,
  Check,
  ExternalLink,
  Heart,
  Mail,
  RotateCw,
  Send,
  Trash2,
  UserRound,
} from "lucide-react";

import { EmptyState } from "@/components/Drawer";
import { formatPrice, propertyLocation, propertyTitle, scoreLabel } from "@/lib/format";
import type { EmailOutcome, Profile, Property, Viewing } from "@/lib/types";

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
    <div className="mini-main">
      <p className="mini-title">{propertyTitle(p)}</p>
      <p className="mini-sub">
        {propertyLocation(p)} · {formatPrice(p.price)}
        {p.sqm ? ` · ${p.sqm} m²` : ""}
      </p>
    </div>
  );
}

/** One-line status of the viewing-request e-mail to the landlord. */
function emailStatus(email: EmailOutcome | undefined): { text: string; tone: string } {
  switch (email?.state) {
    case "sending":
      return { text: "Sending the e-mail to the landlord…", tone: "pending" };
    case "sent":
      return { text: `E-mail sent${email.to ? ` to ${email.to}` : ""}`, tone: "ok" };
    case "dry_run":
      return { text: "E-mail composed, not sent (server dry run)", tone: "muted" };
    case "demo":
      return { text: "Demo listing: no e-mail sent", tone: "muted" };
    case "no_contact":
      return { text: "No e-mail address on the listing: use the listing page", tone: "warn" };
    case "failed":
      return { text: `E-mail failed${email.detail ? `: ${email.detail}` : ""}`, tone: "error" };
    default:
      return { text: "Not e-mailed yet", tone: "muted" };
  }
}

// ---------------------------------------------------------------------------
// My Viewings
// ---------------------------------------------------------------------------
export function ViewingsPanel({
  viewings,
  onRemove,
  onRetry,
}: {
  viewings: Viewing[];
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
        const status = emailStatus(email);
        const canRetry = !email || email.state === "failed";
        return (
          <li key={p.url} className="mini">
            <div className="mini-row">
              <MiniProperty property={p} />
              <span className="mini-score">{scoreLabel(p.agentic_score)}</span>
            </div>
            <div className={`status status-${status.tone}`}>
              <span className="status-dot" />
              <span>
                Requested {formatRequested(requestedAt)} · {status.text}
              </span>
            </div>
            <div className="mini-actions">
              {canRetry && (
                <button
                  type="button"
                  className="text-btn text-btn-accent"
                  onClick={() => onRetry(p)}
                >
                  <RotateCw size={13} strokeWidth={1.75} /> {email ? "Retry e-mail" : "Send e-mail"}
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
        return (
          <li key={p.url} className="mini">
            <div className="mini-row">
              <MiniProperty property={p} />
              <span className="mini-score">{scoreLabel(p.agentic_score)}</span>
            </div>
            {p.score_reason && <p className="mini-reason">{p.score_reason}</p>}
            <div className="mini-actions">
              <button
                type="button"
                className="text-btn text-btn-accent"
                onClick={() => onApprove(p)}
                disabled={approved}
              >
                {approved ? (
                  <>
                    <Check size={13} strokeWidth={2} /> Agent Contacting
                  </>
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

      <p className="settings-saved">
        <UserRound size={13} strokeWidth={1.75} /> Saved automatically in this browser
      </p>
    </div>
  );
}
