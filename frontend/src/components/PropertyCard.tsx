"use client";

import { useId, useState } from "react";
import {
  Check,
  ExternalLink,
  Heart,
  Images,
  LoaderCircle,
  Mail,
  MapPin,
  Maximize2,
  Phone,
  PhoneCall,
  Send,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  matchPercent,
  propertyFacts,
  propertyLocation,
  propertyTitle,
  scamLabel,
  scamWarningText,
  scoreTier,
} from "@/lib/format";
import { ContactBrief } from "@/components/ContactBrief";
import { CountUp } from "@/components/CountUp";
import { ListingPhoto } from "@/components/ListingPhoto";
import { SiteBadge, siteForUrl } from "@/components/SiteLogo";
import { OutreachWorkspace } from "@/components/OutreachWorkspace";
import { useTilt } from "@/lib/motion";
import type { OutreachChannel, OutreachRun, Property } from "@/lib/types";

interface PropertyCardProps {
  property: Property;
  rank: number;
  approved: boolean;
  favorite: boolean;
  /** The live outreach agent for this listing, if one was started in this session. */
  run?: OutreachRun;
  /** Called once the user approved the questions in the briefing (for an e-mail or a call). */
  onApprove: (channel: OutreachChannel, questions: string[]) => void;
  onToggleFavorite: () => void;
  onShowDetails: () => void;
}

export function PropertyCard({
  property: p,
  rank,
  approved,
  favorite,
  run,
  onApprove,
  onToggleFavorite,
  onShowDetails,
}: PropertyCardProps) {
  const working = run?.phase === "running";
  /** The question briefing is open, for an e-mail or a call. */
  const [briefing, setBriefing] = useState<OutreachChannel | null>(null);
  const tilt = useTilt();
  const tier = scoreTier(p.agentic_score);
  const starGradientId = useId();
  const site = p.source ?? siteForUrl(p.url);

  return (
    <article
      id={`property-${rank}`}
      className={`card card-tilt${working ? " is-working" : ""}`}
      style={{ animationDelay: `${(rank - 1) * 140}ms` }}
      {...tilt}
    >
      <span className="card-glare" aria-hidden="true" />
      <button
        type="button"
        className="card-media"
        onClick={onShowDetails}
        aria-label={`View photos and details of ${propertyTitle(p)}`}
      >
        <ListingPhoto images={p.images} alt={propertyTitle(p)} priority={rank === 1} />
        {(p.images?.length ?? 0) > 1 && (
          <span className="photo-count">
            <Images size={12} strokeWidth={2} /> {p.images?.length}
          </span>
        )}
      </button>
      <header className="card-head">
        <span className="card-rank">{String(rank).padStart(2, "0")}</span>
        <div className="card-heading">
          <p className="card-location">
            {(p.location || !site) && (
              <>
                <MapPin size={13} strokeWidth={1.75} />
                {propertyLocation(p)}
              </>
            )}
            {site && <SiteBadge source={site} />}
          </p>
          <h3 className="card-title">
            <button type="button" className="card-title-btn" onClick={onShowDetails}>
              {propertyTitle(p)}
            </button>
          </h3>
          <p className="card-facts">
            {propertyFacts(p).map((fact) => (
              <span key={fact}>{fact}</span>
            ))}
          </p>
        </div>
        <div className={`score score-${tier}`} aria-label={`Agent score ${p.agentic_score} of 10`}>
          <span className="score-value">
            <CountUp value={p.agentic_score} delay={(rank - 1) * 140 + 250} />
            <small>/10</small>
          </span>
          <span className="score-label">
            Match <CountUp value={matchPercent(p.agentic_score)} delay={(rank - 1) * 140 + 250} />%
          </span>
        </div>
      </header>

      {(p.features.length > 0 || p.scam_verdict) && (
        <ul className="card-tags">
          {p.scam_verdict && (
            <li
              className={`tag ${p.scam_verdict === "SAFE" ? "tag-safe" : "tag-risk"}`}
              title="Checked by the Oumi Iris decision model"
            >
              {p.scam_verdict === "SAFE" ? (
                <ShieldCheck size={12} strokeWidth={2} />
              ) : (
                <ShieldAlert size={12} strokeWidth={2} />
              )}
              Oumi Iris · {scamLabel(p)}
            </li>
          )}
          {p.features.slice(0, 5).map((f) => (
            <li key={f} className="tag">
              {f}
            </li>
          ))}
        </ul>
      )}

      {p.scam_verdict === "POSSIBLY_SCAM" && (
        <p className="scam-warning" role="note">
          <ShieldAlert size={14} strokeWidth={2} />
          <span>{scamWarningText(p)}</span>
        </p>
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
          {p.agent_email ? (
            <a className="contact-phone" href={`mailto:${p.agent_email}`} title="E-mail agent">
              <Mail size={14} strokeWidth={1.75} />
              {p.agent_email}
            </a>
          ) : p.agent_phone ? (
            <span className="contact-phone" title="The agent can call this landlord">
              <Phone size={14} strokeWidth={1.75} />
              {p.agent_phone}
            </span>
          ) : (
            <span
              className="contact-phone contact-missing"
              title="No e-mail on the listing: the agent can still place a voice call"
            >
              <Mail size={14} strokeWidth={1.75} />
              No e-mail listed
            </span>
          )}
          {p.agent_name && <span className="contact-name">{p.agent_name}</span>}
        </div>
        <div className="card-actions">
          <button
            type="button"
            className="details-btn"
            onClick={onShowDetails}
            title="Pros, cons and score breakdown"
          >
            <Maximize2 size={14} strokeWidth={1.75} /> Details
          </button>
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
            className={`approve-btn${approved || working ? " is-approved" : ""}`}
            onClick={() => setBriefing("email")}
            disabled={approved || working || !!briefing}
          >
            {/* Keyed so the label cross-fades when the state changes. */}
            <span className="btn-swap" key={working ? "w" : approved ? "a" : "n"}>
              {working ? (
                <>
                  <LoaderCircle size={15} strokeWidth={2} className="spin" /> Agent at work
                </>
              ) : approved ? (
                p.scam_verdict === "POSSIBLY_SCAM" ? (
                  <>
                    <ShieldAlert size={15} strokeWidth={2} /> Drafted · Not Sent
                  </>
                ) : (
                  <>
                    <Check size={15} strokeWidth={2} className="check-draw" />{" "}
                    {run?.channel === "call" ? "Agent Called" : "Agent Contacted"}
                  </>
                )
              ) : (
                <>
                  <Send size={15} strokeWidth={1.75} /> Ask Agent to Contact
                </>
              )}
            </span>
          </button>
          {!approved && !working && (
            <button
              type="button"
              className="call-btn"
              onClick={() => setBriefing("call")}
              disabled={!!briefing}
              title="Have the agent call the landlord now (live voice call)"
            >
              <PhoneCall size={15} strokeWidth={1.75} /> Call
            </button>
          )}
        </div>
      </footer>

      {briefing && !run && !approved && (
        <ContactBrief
          property={p}
          channel={briefing}
          onCancel={() => setBriefing(null)}
          onSend={(questions) => {
            setBriefing(null);
            onApprove(briefing, questions);
          }}
        />
      )}
      {run && <OutreachWorkspace run={run} />}
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
