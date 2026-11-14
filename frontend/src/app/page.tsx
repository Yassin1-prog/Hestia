"use client";

import {
  ArrowUp,
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
import { TopNav, type PanelKey } from "@/components/TopNav";
import { requestViewing, searchProperties } from "@/lib/api";
import { propertyTitle } from "@/lib/format";
import { usePersistentState } from "@/lib/storage";
import {
  EMPTY_PROFILE,
  type EmailOutcome,
  type Profile,
  type Property,
  type SearchResult,
  type Viewing,
} from "@/lib/types";

interface Search {
  id: number;
  query: string;
  result: SearchResult | null;
  error: string | null;
}

function useElapsed(running: boolean, resetKey: number) {
  const [state, setState] = useState({ key: resetKey, seconds: 0 });
  const seconds = state.key === resetKey && running ? state.seconds : 0;

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setState((prev) => ({
        key: resetKey,
        seconds: prev.key === resetKey ? prev.seconds + 1 : 1,
      }));
    }, 1000);
    return () => clearInterval(id);
  }, [running, resetKey]);

  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function HomePage() {
  const [search, setSearch] = useState<Search | null>(null);
  /** Id of the search whose steps have finished; the property list appears below the steps after it. */
  const [revealedId, setRevealedId] = useState<number | null>(null);
  const [followUp, setFollowUp] = useState("");
  const [panel, setPanel] = useState<PanelKey | null>(null);
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  const [profile, setProfile] = usePersistentState<Profile>("hestia.profile", EMPTY_PROFILE);
  const [viewings, setViewings] = usePersistentState<Viewing[]>("hestia.viewings", []);
  const [favorites, setFavorites] = usePersistentState<Property[]>("hestia.favorites", []);
  const abortRef = useRef<AbortController | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);

  const approvedUrls = useMemo(() => new Set(viewings.map((v) => v.property.url)), [viewings]);
  const favoriteUrls = useMemo(() => new Set(favorites.map((f) => f.url)), [favorites]);

  const notify = useCallback((text: string) => {
    const id = Date.now();
    setToast({ id, text });
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 3200);
  }, []);

  const runSearch = useCallback(
    async (query: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const id = ++idRef.current;
      setRevealedId(null);
      setFollowUp("");
      setSearch({ id, query, result: null, error: null });
      try {
        const result = await searchProperties(query, profile, controller.signal);
        setSearch((s) => (s?.id === id ? { ...s, result } : s));
      } catch {
        setSearch((s) =>
          s?.id === id ? { ...s, error: "Search stopped. Adjust your request and try again." } : s,
        );
      }
    },
    [profile],
  );

  const goHome = useCallback(() => {
    abortRef.current?.abort();
    setRevealedId(null);
    setFollowUp("");
    setSearch(null);
  }, []);

  const stopSearch = useCallback(() => {
    abortRef.current?.abort();
    setSearch((s) =>
      s && !s.error ? { ...s, error: "Search stopped. Adjust your request and try again." } : s,
    );
  }, []);

  /** E-mails the landlord (the only outreach channel) and records the outcome on the viewing. */
  const sendViewingEmail = useCallback(
    async (property: Property) => {
      const setEmail = (email: EmailOutcome) =>
        setViewings((v) => v.map((x) => (x.property.url === property.url ? { ...x, email } : x)));
      setEmail({ state: "sending" });
      const outcome = await requestViewing(property, profile);
      setEmail(outcome);
      const title = propertyTitle(property);
      notify(
        {
          sending: "",
          sent: `Agent e-mailed the landlord: ${title}. Added to Contact Requests.`,
          dry_run: `Added to Contact Requests: ${title}. E-mail composed but not sent (server dry run).`,
          demo: `Added to Contact Requests: ${title}. Demo listing, so no e-mail was sent.`,
          no_contact: `Added to Contact Requests: ${title}. The listing has no e-mail address to contact.`,
          failed: `Could not e-mail the landlord for ${title}. Retry from Contact Requests.`,
        }[outcome.state],
      );
    },
    [profile, setViewings, notify],
  );

  const approve = useCallback(
    (property: Property) => {
      if (approvedUrls.has(property.url)) return;
      if (!profile.name.trim() || !profile.email.trim()) {
        setPanel("settings");
        notify("Add your name and e-mail first, so the landlord can reply to you.");
        return;
      }
      setViewings((v) => [{ property, requestedAt: new Date().toISOString() }, ...v]);
      void sendViewingEmail(property);
    },
    [approvedUrls, profile, setViewings, notify, sendViewingEmail],
  );

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
  const revealed = !!search && revealedId === search.id;
  const running = !!search && !revealed && !search.error;
  const searchId = search?.id ?? 0;
  const elapsed = useElapsed(running, searchId);
  const properties = revealed ? (search?.result?.properties ?? []) : [];

  useEffect(() => {
    if (!searchId) return;
    bodyRef.current?.scrollTo({ top: 0 });
  }, [searchId]);

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
              <div>
                <p className="pane-kicker">
                  {search.error
                    ? "Search stopped"
                    : revealed
                      ? `Top matches${properties.length ? ` · ${properties.length} homes selected` : ""}`
                      : "Agent steps"}
                </p>
                <p className="pane-query" title={search.query}>
                  {search.query}
                </p>
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
                result={search.result}
                error={search.error}
                onComplete={() => setRevealedId(search.id)}
              />

              {revealed && (
                <>
                  {search.result?.notice && (
                    <div className="notice">
                      <CircleAlert size={15} strokeWidth={1.75} />
                      <span>
                        Showing demo data — start the FastAPI server on port 8000 for live results.
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
                      onApprove={() => approve(p)}
                      onToggleFavorite={() => toggleFavorite(p)}
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
                  setFollowUp("");
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
          onRetry={(p) => void sendViewingEmail(p)}
          onRemove={(url) => setViewings((v) => v.filter((x) => x.property.url !== url))}
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
          onApprove={approve}
        />
      </Drawer>

      <Drawer
        open={panel === "settings"}
        title="Settings and profile"
        subtitle="Contact details used when scheduling viewings"
        icon={<UserRound size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <SettingsPanel profile={profile} onChange={setProfile} />
      </Drawer>

      {toast && (
        <div className="toast" role="status" key={toast.id}>
          {toast.text}
        </div>
      )}
    </div>
  );
}
