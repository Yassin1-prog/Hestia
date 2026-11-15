"use client";

import {
  Check,
  ExternalLink,
  Heart,
  LoaderCircle,
  Mail,
  MapPin,
  MessageCircleQuestion,
  Minus,
  Plus,
  Phone,
  PhoneCall,
  Send,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ContactBrief } from "@/components/ContactBrief";
import { CountUp } from "@/components/CountUp";
import { PhotoGallery } from "@/components/ListingPhoto";
import { SiteBadge, siteForUrl } from "@/components/SiteLogo";
import { OutreachWorkspace } from "@/components/OutreachWorkspace";
import {
  formatPrice,
  matchPercent,
  propertyFacts,
  propertyLocation,
  propertyTitle,
  scamWarningText,
  scoreTier,
} from "@/lib/format";
import { useCountUp } from "@/lib/motion";
import type { MetricScore, OutreachChannel, OutreachRun, Property } from "@/lib/types";

function ScoreRing({ score }: { score: number }) {
  const r = 34;
  const circumference = 2 * Math.PI * r;
  const shown = useCountUp(Math.max(0, Math.min(10, score)), 1100, 150);
  const tier = scoreTier(score);
  return (
    <div className={`ring ring-${tier}`} aria-label={`Agent score ${score} of 10`}>
      <svg viewBox="0 0 80 80" aria-hidden="true">
        <circle className="ring-track" cx="40" cy="40" r={r} />
        <circle
          className="ring-fill"
          cx="40"
          cy="40"
          r={r}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - shown / 10)}
        />
      </svg>
      <span className="ring-value">
        {shown.toFixed(Number.isInteger(score) ? 0 : 1)}
        <small>/10</small>
      </span>
      <span className="ring-label">
        Match <CountUp value={matchPercent(score)} duration={1100} delay={150} />%
      </span>
    </div>
  );
}

function MetricBar({ metric, index }: { metric: MetricScore; index: number }) {
  const score = Math.max(0, Math.min(10, Number(metric.score) || 0));
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const delay = 200 + index * 110;
  return (
    <li className="metric" style={{ animationDelay: `${delay - 120}ms` }}>
      <div className="metric-row">
        <span className="metric-name">{metric.name}</span>
        <span className={`metric-score metric-${scoreTier(score)}`}>
          <CountUp value={score} delay={delay} />
          <small>/10</small>
        </span>
      </div>
      <div className="metric-track">
        <span
          className={`metric-fill metric-fill-${scoreTier(score)}`}
          style={{ width: filled ? `${score * 10}%` : 0, transitionDelay: `${delay}ms` }}
        />
      </div>
      {metric.note && <p className="metric-note">{metric.note}</p>}
    </li>
  );
}

/** Older results (or a listing the agent could not judge) fall back to what the card knows. */
function insights(p: Property) {
  const pros = p.pros?.length ? p.pros : p.features.slice(0, 4);
  const cons = p.cons?.length ? p.cons : p.missing_info.slice(0, 3).map((q) => `Unconfirmed: ${q}`);
  const metrics: MetricScore[] = p.metrics?.length
    ? p.metrics
    : [{ name: "Overall match", score: p.agentic_score, note: p.score_reason }];
  return { pros, cons, metrics, detailed: !!p.metrics?.length };
}

interface PropertyDetailsProps {
  property: Property | null;
  rank: number;
  approved: boolean;
  favorite: boolean;
  run?: OutreachRun;
  /** Open with the question briefing already showing (e.g. from My Favorites). */
  startWithBrief?: boolean;
  initialQuestions?: string[];
  onClose: () => void;
  /** Called once the user approved the questions in the briefing (for an e-mail or a call). */
  onApprove: (channel: OutreachChannel, questions: string[]) => void;
  onToggleFavorite: () => void;
}

export function PropertyDetails({
  property,
  rank,
  approved,
  favorite,
  run,
  startWithBrief = false,
  initialQuestions,
  onClose,
  onApprove,
  onToggleFavorite,
}: PropertyDetailsProps) {
  const open = !!property;
  /** The question briefing is open, for an e-mail or a call. */
  const [briefing, setBriefing] = useState<OutreachChannel | null>(startWithBrief ? "email" : null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [shown, setShown] = useState<Property | null>(property);
  const [openSeq, setOpenSeq] = useState(0);

  // Keep the last property rendered while the dialog animates out; replay animations per open.
  useEffect(() => {
    if (!property) return;
    setShown(property);
    setOpenSeq((n) => n + 1);
  }, [property]);

  useEffect(() => {
    setBriefing(startWithBrief ? "email" : null);
  }, [property?.url, startWithBrief]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const hasRun = !!run;
  useEffect(() => {
    const body = bodyRef.current;
    if (body && (briefing || hasRun)) body.scrollTo({ top: body.scrollHeight, behavior: "smooth" });
  }, [briefing, hasRun]);

  const p = shown;
  const site = p ? (p.source ?? siteForUrl(p.url)) : undefined;
  const working = run?.phase === "running";

  return (
    <div className={`modal-root${open ? " is-open" : ""}`} aria-hidden={!open} inert={!open}>
      <div className="modal-backdrop" onClick={onClose} />
      {p && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-label={`Details: ${propertyTitle(p)}`}
          key={`${p.url}-${openSeq}`}
        >
          <header className="modal-head">
            <div className="modal-heading">
              <p className="card-location">
                {(p.location || !site) && (
                  <>
                    <MapPin size={13} strokeWidth={1.75} />
                    {propertyLocation(p)}
                  </>
                )}
                {site && <SiteBadge source={site} />}
                {rank > 0 && <span className="modal-rank">#{rank} match</span>}
              </p>
              <h2 className="modal-title">{propertyTitle(p)}</h2>
              <p className="card-facts">
                {propertyFacts(p).map((fact) => (
                  <span key={fact}>{fact}</span>
                ))}
              </p>
            </div>
            <ScoreRing score={p.agentic_score} />
            <button
              ref={closeRef}
              type="button"
              className="icon-btn modal-close"
              onClick={onClose}
              aria-label="Close details"
            >
              <X size={16} strokeWidth={1.75} />
            </button>
          </header>

          <div className="modal-body" ref={bodyRef}>
            <PhotoGallery images={p.images} alt={propertyTitle(p)} />
            <DetailsContent p={p} />

            {briefing && !run && (
              <ContactBrief
                property={p}
                initial={initialQuestions}
                channel={briefing}
                onCancel={() => setBriefing(null)}
                onSend={(questions) => {
                  setBriefing(null);
                  onApprove(briefing, questions);
                }}
              />
            )}
            {run && <OutreachWorkspace run={run} />}
          </div>

          <footer className="modal-foot">
            <div className="contact">
              {p.agent_email ? (
                <a className="contact-phone" href={`mailto:${p.agent_email}`}>
                  <Mail size={14} strokeWidth={1.75} />
                  {p.agent_email}
                </a>
              ) : p.agent_phone ? (
                <span className="contact-phone">
                  <Phone size={14} strokeWidth={1.75} /> {p.agent_phone}
                </span>
              ) : (
                <span className="contact-phone contact-missing">
                  <Mail size={14} strokeWidth={1.75} /> No e-mail listed
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
              >
                <Heart size={16} strokeWidth={1.75} fill={favorite ? "currentColor" : "none"} />
              </button>
              <a
                className="icon-btn"
                href={p.url}
                target="_blank"
                rel="noreferrer"
                aria-label="Open listing"
              >
                <ExternalLink size={16} strokeWidth={1.75} />
              </a>
              <button
                type="button"
                className={`approve-btn${approved || working ? " is-approved" : ""}`}
                onClick={() => setBriefing("email")}
                disabled={approved || working || !!briefing}
              >
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
        </div>
      )}
    </div>
  );
}

function DetailsContent({ p }: { p: Property }) {
  const { pros, cons, metrics, detailed } = insights(p);
  const perSqm = p.price && p.sqm ? Math.round((p.price / p.sqm) * 10) / 10 : null;
  return (
    <>
      {p.scam_verdict === "POSSIBLY_SCAM" && (
        <p className="scam-warning modal-scam-warning" role="note">
          <ShieldAlert size={14} strokeWidth={2} />
          <span>{scamWarningText(p)}</span>
        </p>
      )}
      {p.score_reason && (
        <section className="why modal-why">
          <p className="why-text">{p.score_reason}</p>
        </section>
      )}

      <section className="modal-section">
        <h3 className="modal-section-title">Score breakdown</h3>
        <ul className="metrics">
          {metrics.map((m, i) => (
            <MetricBar key={m.name} metric={m} index={i} />
          ))}
        </ul>
        {!detailed && (
          <p className="modal-hint">
            Per-metric scores appear on listings the agent inspected in a new search.
          </p>
        )}
      </section>

      {(pros.length > 0 || cons.length > 0) && (
        <section className="modal-section proscons">
          <div className="proscons-col">
            <h3 className="modal-section-title">Pros</h3>
            <ul>
              {pros.map((t, i) => (
                <li key={t} className="pro" style={{ animationDelay: `${300 + i * 70}ms` }}>
                  <span className="pc-icon">
                    <Plus size={11} strokeWidth={2.5} />
                  </span>
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <div className="proscons-col">
            <h3 className="modal-section-title">Cons</h3>
            <ul>
              {cons.length ? (
                cons.map((t, i) => (
                  <li key={t} className="con" style={{ animationDelay: `${360 + i * 70}ms` }}>
                    <span className="pc-icon">
                      <Minus size={11} strokeWidth={2.5} />
                    </span>
                    {t}
                  </li>
                ))
              ) : (
                <li className="con con-none">Nothing stood out.</li>
              )}
            </ul>
          </div>
        </section>
      )}

      <section className="modal-section">
        <h3 className="modal-section-title">Key facts</h3>
        <dl className="facts">
          <div>
            <dt>Rent</dt>
            <dd>{formatPrice(p.price)}</dd>
          </div>
          <div>
            <dt>Size</dt>
            <dd>{p.sqm ? `${p.sqm} m²` : "n/a"}</dd>
          </div>
          <div>
            <dt>Per m²</dt>
            <dd>{perSqm ? `€${perSqm}` : "n/a"}</dd>
          </div>
          <div>
            <dt>Floor</dt>
            <dd>{p.floor || "n/a"}</dd>
          </div>
          <div className="fact-wide">
            <dt>Scam check (Oumi Iris)</dt>
            <dd
              className={
                p.scam_verdict === "POSSIBLY_SCAM" ? "fact-risk" : p.scam_verdict ? "fact-safe" : ""
              }
            >
              <span className="fact-status">
                {p.scam_verdict === "POSSIBLY_SCAM" ? (
                  <>
                    <ShieldAlert size={13} strokeWidth={2} /> Possible scam
                  </>
                ) : p.scam_verdict === "SAFE" ? (
                  <>
                    <ShieldCheck size={13} strokeWidth={2} /> Passed
                  </>
                ) : (
                  "Not run"
                )}
                {p.scam_risk_pct != null && ` · ${p.scam_risk_pct}% risk`}
              </span>
              {p.scam_verdict === "POSSIBLY_SCAM" && p.scam_reason && (
                <span className="fact-note">{p.scam_reason}</span>
              )}
            </dd>
          </div>
        </dl>
      </section>

      {p.features.length > 0 && (
        <section className="modal-section">
          <h3 className="modal-section-title">Features</h3>
          <ul className="card-tags modal-tags">
            {p.features.map((f) => (
              <li key={f} className="tag">
                {f}
              </li>
            ))}
          </ul>
        </section>
      )}

      {p.missing_info.length > 0 && (
        <section className="modal-section">
          <h3 className="modal-section-title">What the listing leaves open</h3>
          <ul className="open-qs">
            {p.missing_info.map((q) => (
              <li key={q}>
                <MessageCircleQuestion size={13} strokeWidth={1.75} />
                {q}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
