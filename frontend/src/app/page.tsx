"use client";

import {
  ArrowUp,
  Bot,
  CalendarDays,
  CircleAlert,
  Heart,
  RotateCcw,
  Square,
  UserRound,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentFeed } from "@/components/AgentFeed";
import { Drawer } from "@/components/Drawer";
import { Hero } from "@/components/Hero";
import { FavoritesPanel, SettingsPanel, ViewingsPanel } from "@/components/Panels";
import { PropertyCard } from "@/components/PropertyCard";
import { PropertyDetails } from "@/components/PropertyDetails";
import { TopNav, type PanelKey } from "@/components/TopNav";
import { VoiceCallPanel } from "@/components/VoiceCallPanel";
import { formatDuration, isScamLockedOutcome, propertyTitle } from "@/lib/format";
import { usePersistentState } from "@/lib/storage";
import { useOutreachAgents } from "@/lib/useOutreachAgents";
import { useSearchAgent } from "@/lib/useSearchAgent";
import { useVoiceCall, type VoiceCall } from "@/lib/useVoiceCall";
import {
  EMPTY_PROFILE,
  type CallBrief,
  type EmailOutcome,
  type OutreachChannel,
  type Profile,
  type Property,
  type Viewing,
} from "@/lib/types";

function useNow(running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  return now;
}

function slotsPhrase(outcome: EmailOutcome): string {
  const n = outcome.windows?.length ?? 0;
  return n ? `, proposing ${n} viewing slot${n === 1 ? "" : "s"} from your calendar` : "";
}

export default function HomePage() {
  const [followUp, setFollowUp] = useState("");
  const [panel, setPanel] = useState<PanelKey | null>(null);
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  const [profile, setProfile] = usePersistentState<Profile>("hestia.profile", EMPTY_PROFILE);
  const [viewings, setViewings] = usePersistentState<Viewing[]>("hestia.viewings", []);
  const [favorites, setFavorites] = usePersistentState<Property[]>("hestia.favorites", []);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [details, setDetails] = useState<{
    property: Property;
    rank: number;
    brief: boolean;
  } | null>(null);

  const {
    search,
    run: runSearchAgent,
    stop: stopSearch,
    reset: resetSearch,
  } = useSearchAgent(profile);

  const approvedUrls = useMemo(() => new Set(viewings.map((v) => v.property.url)), [viewings]);
  const favoriteUrls = useMemo(() => new Set(favorites.map((f) => f.url)), [favorites]);

  const notify = useCallback((text: string) => {
    const id = Date.now();
    setToast({ id, text });
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 3600);
  }, []);

  /** The outreach agent finished: persist the outcome on the viewing and tell the user. */
  const onOutreachFinished = useCallback(
    (property: Property, outcome: EmailOutcome) => {
      setViewings((v) =>
        v.map((x) => (x.property.url === property.url ? { ...x, email: outcome } : x)),
      );
      const title = propertyTitle(property);
      const scamLocked = property.scam_verdict === "POSSIBLY_SCAM" || isScamLockedOutcome(outcome);
      if (outcome.channel === "call") {
        notify(
          outcome.state === "sent" || outcome.state === "demo"
            ? `The agent is calling the landlord about ${title}: answer as the landlord.`
            : scamLocked
              ? `Oumi Iris flagged ${title} as a possible scam: the call was not placed.`
              : `Could not call the landlord for ${title}${outcome.detail ? `: ${outcome.detail}` : "."}`,
        );
        return;
      }
      notify(
        {
          sending: "",
          sent: `Agent e-mailed the landlord about ${title}${slotsPhrase(outcome)}.`,
          dry_run: scamLocked
            ? `Oumi Iris flagged ${title} as a possible scam: e-mail drafted, not sent.`
            : `E-mail for ${title} composed but not sent (server dry run).`,
          demo: scamLocked
            ? `Demo listing (Oumi Iris scam lock): e-mail drafted for ${title}, not sent.`
            : `Demo listing: the agent wrote the e-mail for ${title}, nothing was sent.`,
          no_contact: `${title} has no e-mail address to contact.`,
          failed: `Could not contact the landlord for ${title}. Retry from Contact Requests.`,
        }[outcome.state],
      );
    },
    [setViewings, notify],
  );

  const voice = useVoiceCall(
    useCallback((call: VoiceCall) => notify(`Voice call about ${call.title} ended.`), [notify]),
  );
  const startVoiceCall = voice.start;
  const primeCall = voice.prime;
  const onCall = useCallback(
    (property: Property, brief: CallBrief) =>
      void startVoiceCall(propertyTitle(property), brief, profile.name.trim() || "my client"),
    [startVoiceCall, profile.name],
  );

  const outreach = useOutreachAgents(profile, onOutreachFinished, onCall);

  /** Retry from Contact Requests, reusing the questions approved the first time. */
  const contactLandlord = useCallback(
    (property: Property) => {
      const previous = viewings.find((x) => x.property.url === property.url);
      const channel = previous?.channel ?? "email";
      if (channel === "call") primeCall();
      setViewings((v) =>
        v.map((x) =>
          x.property.url === property.url ? { ...x, email: { state: "sending", channel } } : x,
        ),
      );
      void outreach.start(property, previous?.questions, channel);
    },
    [viewings, setViewings, outreach, primeCall],
  );

  const approve = useCallback(
    (property: Property, channel: OutreachChannel, questions: string[]) => {
      if (approvedUrls.has(property.url)) return;
      // The agent introduces you by name on a call; an e-mail also needs your address for replies.
      if (!profile.name.trim() || (channel === "email" && !profile.email.trim())) {
        setDetails(null);
        setPanel("settings");
        notify(
          channel === "call"
            ? "Add your name first, so the agent can introduce you to the landlord."
            : "Add your name and e-mail first, so the landlord can reply to you.",
        );
        return;
      }
      // Still inside the click: unlock audio now, the call starts once the brief is written.
      if (channel === "call") primeCall();
      setViewings((v) => [
        {
          property,
          requestedAt: new Date().toISOString(),
          email: { state: "sending", channel },
          questions,
          channel,
        },
        ...v,
      ]);
      void outreach.start(property, questions, channel);
    },
    [approvedUrls, profile, setViewings, notify, outreach, primeCall],
  );

  const runSearch = useCallback(
    (query: string) => {
      setFollowUp("");
      void runSearchAgent(query);
    },
    [runSearchAgent],
  );

  const goHome = useCallback(() => {
    resetSearch();
    setFollowUp("");
  }, [resetSearch]);

  const toggleFavorite = useCallback(
    (property: Property) => {
      if (favoriteUrls.has(property.url)) {
        setFavorites((f) => f.filter((x) => x.url !== property.url));
      } else {
        setFavorites((f) => [property, ...f]);
        notify(`Saved to My Favorites: ${propertyTitle(property)}.`);
      }
    },
    [favoriteUrls, setFavorites, notify],
  );

  const closePanel = useCallback(() => setPanel(null), []);
  const closeDetails = useCallback(() => setDetails(null), []);
  const phase = search?.phase;
  const revealed = phase === "done";
  const running = phase === "running";
  const now = useNow(running);
  const elapsed = search ? formatDuration((search.finishedAt ?? now) - search.startedAt) : "0:00";
  const durationMs = search ? (search.finishedAt ?? now) - search.startedAt : 0;
  const properties = revealed ? (search?.result?.properties ?? []) : [];
  const searchId = search?.id ?? 0;

  useEffect(() => {
    if (!searchId) return;
    bodyRef.current?.scrollTo({ top: 0 });
  }, [searchId]);

  useEffect(() => {
    if (revealed) bodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [revealed]);

  return (
    <div className="app">
      <div className="backdrop-glow" aria-hidden="true" />
      <TopNav
        viewingsCount={viewings.length}
        favoritesCount={favorites.length}
        onHome={goHome}
        onOpen={setPanel}
      />

      <main className="main">
        {!search ? (
          <Hero onSubmit={runSearch} />
        ) : (
          <section className="single-pane results" aria-label="Search results">
            <header className="pane-head">
              <div className="pane-head-main">
                <span
                  className={`agent-avatar${running ? " is-working" : revealed ? " is-done" : ""}`}
                  aria-hidden="true"
                >
                  <Bot size={16} strokeWidth={1.75} />
                </span>
                <div className="pane-head-text">
                  <p className="pane-kicker" key={phase}>
                    {phase === "stopped"
                      ? "Search stopped"
                      : revealed
                        ? `Top matches${properties.length ? ` · ${properties.length} homes selected` : ""}`
                        : "Agent at work"}
                  </p>
                  <p className="pane-query" title={search.query}>
                    {search.query}
                  </p>
                </div>
              </div>
              <div className="pane-head-actions">
                {running ? (
                  <button type="button" className="ghost-btn" onClick={stopSearch}>
                    <Square size={12} strokeWidth={2} /> Stop · {elapsed}
                  </button>
                ) : (
                  <>
                    {revealed && search.result && (
                      <span className={`source-badge source-${search.result.source}`}>
                        <span className="source-dot" />
                        {search.result.source === "live" ? "Live data" : "Demo data"}
                      </span>
                    )}
                    <button type="button" className="ghost-btn" onClick={goHome}>
                      <RotateCcw size={13} strokeWidth={1.75} /> New search
                    </button>
                  </>
                )}
              </div>
            </header>

            <div className="pane-body cards" ref={bodyRef}>
              <AgentFeed
                key={search.id}
                steps={search.steps}
                phase={search.phase}
                result={search.result}
                error={search.error}
                durationMs={durationMs}
              />

              {revealed && (
                <>
                  {search.result?.notice && (
                    <div className="notice">
                      <CircleAlert size={15} strokeWidth={1.75} />
                      <span>
                        {search.result.notice} Showing demo data: start the FastAPI server on port
                        8000 for live results.
                      </span>
                    </div>
                  )}
                  {properties.map((p, i) => (
                    <PropertyCard
                      key={p.url}
                      property={p}
                      rank={i + 1}
                      approved={approvedUrls.has(p.url)}
                      favorite={favoriteUrls.has(p.url)}
                      run={outreach.runs[p.url]}
                      onApprove={(channel, questions) => approve(p, channel, questions)}
                      onToggleFavorite={() => toggleFavorite(p)}
                      onShowDetails={() => setDetails({ property: p, rank: i + 1, brief: false })}
                    />
                  ))}
                  {!properties.length && (
                    <p className="cards-empty">
                      The agent did not find a listing that fits. Add instructions below to widen
                      the search.
                    </p>
                  )}
                </>
              )}
            </div>

            {revealed && (
              <form
                className="followup"
                onSubmit={(e) => {
                  e.preventDefault();
                  const text = followUp.trim();
                  if (!text) return;
                  runSearch(`${search.query}. Additional instructions: ${text}`);
                }}
              >
                <input
                  className="followup-input"
                  value={followUp}
                  onChange={(e) => setFollowUp(e.target.value)}
                  placeholder="Add instructions, e.g. only places with an elevator"
                  aria-label="Additional instructions for the agent"
                />
                <button
                  type="submit"
                  className="followup-send"
                  disabled={!followUp.trim()}
                  aria-label="Send instructions"
                >
                  <ArrowUp size={16} strokeWidth={2} />
                </button>
              </form>
            )}
          </section>
        )}
      </main>

      <Drawer
        open={panel === "viewings"}
        title="Contact Requests"
        subtitle="Properties where you asked the agent to contact the landlord"
        icon={<CalendarDays size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <ViewingsPanel
          viewings={viewings}
          runs={outreach.runs}
          onRetry={contactLandlord}
          onRemove={(url) => {
            outreach.cancel(url);
            setViewings((v) => v.filter((x) => x.property.url !== url));
          }}
        />
      </Drawer>

      <Drawer
        open={panel === "favorites"}
        title="My Favorites"
        subtitle="Homes you saved across searches"
        icon={<Heart size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <FavoritesPanel
          favorites={favorites}
          approvedUrls={approvedUrls}
          onRemove={(url) => setFavorites((f) => f.filter((x) => x.url !== url))}
          onApprove={(p) => {
            setPanel(null);
            setDetails({ property: p, rank: 0, brief: true });
          }}
        />
      </Drawer>

      <Drawer
        open={panel === "settings"}
        title="Settings and profile"
        subtitle="Contact details and calendar used when scheduling viewings"
        icon={<UserRound size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <SettingsPanel profile={profile} onChange={setProfile} />
      </Drawer>

      <PropertyDetails
        property={details?.property ?? null}
        rank={details?.rank ?? 0}
        startWithBrief={details?.brief}
        approved={!!details && approvedUrls.has(details.property.url)}
        favorite={!!details && favoriteUrls.has(details.property.url)}
        run={details ? outreach.runs[details.property.url] : undefined}
        onClose={closeDetails}
        onApprove={(channel, questions) =>
          details && approve(details.property, channel, questions)
        }
        onToggleFavorite={() => details && toggleFavorite(details.property)}
      />

      {voice.call && (
        <VoiceCallPanel
          call={voice.call}
          onHangUp={voice.stop}
          onDismiss={voice.dismiss}
          onEnableSound={voice.enableSound}
        />
      )}

      {toast && (
        <div className="toast" role="status" key={toast.id}>
          {toast.text}
        </div>
      )}
    </div>
  );
}
