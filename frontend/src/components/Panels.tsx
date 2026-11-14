"use client";

import {
  CalendarDays,
  CalendarPlus,
  Check,
  ExternalLink,
  Heart,
  Phone,
  Plus,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { useState } from "react";

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
        title="No viewings yet"
        text="Press Approve Viewing on a property card and the agent will arrange it with the landlord."
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
            Approved {formatRequested(requestedAt)} · agent will contact the landlord
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
                    <Check size={13} strokeWidth={2} /> Viewing requested
                  </>
                ) : (
                  <>
                    <CalendarPlus size={13} strokeWidth={1.75} /> Approve Viewing
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
const SUGGESTIONS = [
  "I have 2 cats",
  "Max budget €700",
  "Need space for a home office",
  "No ground-floor apartments",
  "Within 10 minutes of a metro station",
];

export function SettingsPanel({
  profile,
  onChange,
}: {
  profile: Profile;
  onChange: (profile: Profile) => void;
}) {
  const [draft, setDraft] = useState("");

  function addConstraint(text: string) {
    const value = text.trim();
    if (!value || profile.constraints.some((c) => c.toLowerCase() === value.toLowerCase())) return;
    onChange({ ...profile, constraints: [...profile.constraints, value] });
    setDraft("");
  }

  const suggestions = SUGGESTIONS.filter(
    (s) => !profile.constraints.some((c) => c.toLowerCase() === s.toLowerCase()),
  );

  return (
    <div className="settings">
      <section className="settings-section">
        <h3 className="settings-title">Permanent preferences</h3>
        <p className="settings-hint">
          Attached to every search automatically, so you never have to repeat them.
        </p>
        <form
          className="field-row"
          onSubmit={(e) => {
            e.preventDefault();
            addConstraint(draft);
          }}
        >
          <input
            className="field"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. I have 2 cats"
            aria-label="New preference"
          />
          <button type="submit" className="square-btn" disabled={!draft.trim()} aria-label="Add">
            <Plus size={16} strokeWidth={1.75} />
          </button>
        </form>

        {profile.constraints.length > 0 && (
          <ul className="constraint-list">
            {profile.constraints.map((c) => (
              <li key={c} className="constraint">
                <span>{c}</span>
                <button
                  type="button"
                  onClick={() =>
                    onChange({
                      ...profile,
                      constraints: profile.constraints.filter((x) => x !== c),
                    })
                  }
                  aria-label={`Remove ${c}`}
                >
                  <X size={13} strokeWidth={1.75} />
                </button>
              </li>
            ))}
          </ul>
        )}

        {suggestions.length > 0 && (
          <div className="suggestions">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                className="chip chip-small"
                onClick={() => addConstraint(s)}
              >
                <Plus size={12} strokeWidth={1.75} /> {s}
              </button>
            ))}
          </div>
        )}

        <label className="toggle">
          <input
            type="checkbox"
            checked={profile.attachToSearch}
            onChange={(e) => onChange({ ...profile, attachToSearch: e.target.checked })}
          />
          <span className="toggle-track" aria-hidden="true" />
          Attach preferences to every search
        </label>
      </section>

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
