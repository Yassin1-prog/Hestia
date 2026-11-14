"use client";

import { useId } from "react";
import {
  Check,
  ExternalLink,
  Heart,
  Mail,
  MapPin,
  Phone,
  Send,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  matchPercent,
  propertyFacts,
  propertyLocation,
  propertyTitle,
  scoreLabel,
  scoreTier,
  telHref,
} from "@/lib/format";
import type { Property } from "@/lib/types";

interface PropertyCardProps {
  property: Property;
  rank: number;
  approved: boolean;
  favorite: boolean;
  onApprove: () => void;
  onToggleFavorite: () => void;
}

export function PropertyCard({
  property: p,
  rank,
  approved,
  favorite,
  onApprove,
  onToggleFavorite,
}: PropertyCardProps) {
  const tier = scoreTier(p.agentic_score);
  const starGradientId = useId();

  return (
    <article
      id={`property-${rank}`}
      className="card"
      style={{ animationDelay: `${(rank - 1) * 120}ms` }}
    >
      <header className="card-head">
        <span className="card-rank">{String(rank).padStart(2, "0")}</span>
        <div className="card-heading">
          <p className="card-location">
            <MapPin size={13} strokeWidth={1.75} />
            {propertyLocation(p)}
          </p>
          <h3 className="card-title">{propertyTitle(p)}</h3>
          <p className="card-facts">
            {propertyFacts(p).map((fact) => (
              <span key={fact}>{fact}</span>
            ))}
          </p>
        </div>
        <div className={`score score-${tier}`} aria-label={`Agent score ${p.agentic_score} of 10`}>
          <span className="score-value">
            {scoreLabel(p.agentic_score)}
            <small>/10</small>
          </span>
          <span className="score-label">Match {matchPercent(p.agentic_score)}%</span>
        </div>
      </header>

      {(p.features.length > 0 || p.scam_verdict) && (
        <ul className="card-tags">
          {p.scam_verdict === "SAFE" && (
            <li className="tag tag-safe">
              <ShieldCheck size={12} strokeWidth={2} /> Scam check passed
            </li>
          )}
          {p.scam_verdict === "POSSIBLY_SCAM" && (
            <li className="tag tag-risk">
              <ShieldAlert size={12} strokeWidth={2} /> Possible scam
            </li>
          )}
          {p.features.slice(0, 5).map((f) => (
            <li key={f} className="tag">
              {f}
            </li>
          ))}
        </ul>
      )}

      {p.score_reason && (
        <section className="why">
          <svg className="why-star" viewBox="0 0 24 24" aria-hidden="true">
            <defs>
              <linearGradient id={starGradientId} x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="var(--gold)" />
                <stop offset="100%" stopColor="var(--emerald)" />
              </linearGradient>
            </defs>
            <path
              d="M12 2C12.9 7.8 16.2 11.1 22 12C16.2 12.9 12.9 16.2 12 22C11.1 16.2 7.8 12.9 2 12C7.8 11.1 11.1 7.8 12 2Z"
              fill={`url(#${starGradientId})`}
            />
          </svg>
          <p className="why-text">{p.score_reason}</p>
        </section>
      )}

      <footer className="card-foot">
        <div className="contact">
          {p.agent_phone ? (
            <a className="contact-phone" href={telHref(p.agent_phone)} title="Call agent">
              <Phone size={14} strokeWidth={1.75} />
              {p.agent_phone}
            </a>
          ) : p.agent_email ? (
            <a className="contact-phone" href={`mailto:${p.agent_email}`} title="Email agent">
              <Mail size={14} strokeWidth={1.75} />
              {p.agent_email}
            </a>
          ) : (
            <span className="contact-phone contact-missing">
              <Phone size={14} strokeWidth={1.75} />
              No contact listed
            </span>
          )}
          {p.agent_name && <span className="contact-name">{p.agent_name}</span>}
        </div>
        <div className="card-actions">
          <button
            type="button"
            className={`icon-btn${favorite ? " is-active" : ""}`}
            onClick={onToggleFavorite}
            aria-pressed={favorite}
            aria-label={favorite ? "Remove from favorites" : "Save to favorites"}
            title={favorite ? "Remove from favorites" : "Save to favorites"}
          >
            <Heart size={16} strokeWidth={1.75} fill={favorite ? "currentColor" : "none"} />
          </button>
          <a
            className="icon-btn"
            href={p.url}
            target="_blank"
            rel="noreferrer"
            aria-label="Open listing"
            title="Open listing"
          >
            <ExternalLink size={16} strokeWidth={1.75} />
          </a>
          <button
            type="button"
            className={`approve-btn${approved ? " is-approved" : ""}`}
            onClick={onApprove}
            disabled={approved}
          >
            {approved ? (
              <>
                <Check size={15} strokeWidth={2} /> Agent Contacting
              </>
            ) : (
              <>
                <Send size={15} strokeWidth={1.75} /> Ask Agent to Contact
              </>
            )}
          </button>
        </div>
      </footer>
    </article>
  );
}

export function PropertyCardSkeleton({ index }: { index: number }) {
  return (
    <div className="card card-skeleton" style={{ animationDelay: `${index * 120}ms` }}>
      <div className="sk sk-line" style={{ width: "30%" }} />
      <div className="sk sk-title" style={{ width: "62%" }} />
      <div className="sk sk-line" style={{ width: "44%" }} />
      <div className="sk sk-block" />
      <div className="sk sk-line" style={{ width: "80%" }} />
    </div>
  );
}
