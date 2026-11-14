"use client";

import {
  CalendarDays,
  Check,
  ExternalLink,
  Heart,
  Phone,
  Send,
  Trash2,
  UserRound,
} from "lucide-react";

import { EmptyState } from "@/components/Drawer";
import { formatPrice, propertyLocation, propertyTitle, scoreLabel, telHref } from "@/lib/format";
import type { Profile, Property, Viewing } from "@/lib/types";

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

// ---------------------------------------------------------------------------
// My Viewings
// ---------------------------------------------------------------------------
export function ViewingsPanel({
  viewings,
  onRemove,
}: {
  viewings: Viewing[];
  onRemove: (url: string) => void;
}) {
  if (!viewings.length) {
    return (
      <EmptyState
        icon={<CalendarDays size={20} strokeWidth={1.5} />}
        title="No contact requests yet"
        text="Press Ask Agent to Contact on a property card and the agent will reach out to the landlord for you."
      />
    );
  }
  return (
    <ul className="mini-list">
      {viewings.map(({ property: p, requestedAt }) => (
        <li key={p.url} className="mini">
          <div className="mini-row">
            <MiniProperty property={p} />
            <span className="mini-score">{scoreLabel(p.agentic_score)}</span>
          </div>
          <div className="status">
            <span className="status-dot" />
            Requested {formatRequested(requestedAt)} · agent will contact the landlord
          </div>
          <div className="mini-actions">
            {p.agent_phone && (
              <a className="text-btn" href={telHref(p.agent_phone)}>
                <Phone size={13} strokeWidth={1.75} /> {p.agent_phone}
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
      ))}
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
          Shared with landlords only after you approve a viewing, so they can reply to you.
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
        <label className="label">
          Phone
          <input
            className="field"
            type="tel"
            value={profile.phone}
            onChange={(e) => onChange({ ...profile, phone: e.target.value })}
            placeholder="+30 690 000 0000"
            autoComplete="tel"
          />
        </label>
      </section>

      <p className="settings-saved">
        <UserRound size={13} strokeWidth={1.75} /> Saved automatically in this browser
      </p>
    </div>
  );
}
