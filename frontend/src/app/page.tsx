"use client";

import { CalendarDays, Heart, UserRound } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";

import { AgentFeed } from "@/components/AgentFeed";
import { Drawer } from "@/components/Drawer";
import { Hero } from "@/components/Hero";
import { FavoritesPanel, SettingsPanel, ViewingsPanel } from "@/components/Panels";
import { PropertyCard, PropertyCardSkeleton } from "@/components/PropertyCard";
import { TopNav, type PanelKey } from "@/components/TopNav";
import { searchProperties } from "@/lib/api";
import { propertyTitle } from "@/lib/format";
import { usePersistentState } from "@/lib/storage";
import {
  EMPTY_PROFILE,
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

export default function HomePage() {
  const [search, setSearch] = useState<Search | null>(null);
  /** Id of the search whose thought process has finished; cards are revealed after it. */
  const [revealedId, setRevealedId] = useState<number | null>(null);
  const [panel, setPanel] = useState<PanelKey | null>(null);
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  const [profile, setProfile] = usePersistentState<Profile>("hestia.profile", EMPTY_PROFILE);
  const [viewings, setViewings] = usePersistentState<Viewing[]>("hestia.viewings", []);
  const [favorites, setFavorites] = usePersistentState<Property[]>("hestia.favorites", []);
  const abortRef = useRef<AbortController | null>(null);
  const idRef = useRef(0);

  const approvedUrls = useMemo(() => new Set(viewings.map((v) => v.property.url)), [viewings]);
  const favoriteUrls = useMemo(() => new Set(favorites.map((f) => f.url)), [favorites]);
  const constraintsCount = profile.attachToSearch ? profile.constraints.length : 0;

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
    setSearch(null);
  }, []);

  const approve = useCallback(
    (property: Property) => {
      if (approvedUrls.has(property.url)) return;
      setViewings((v) => [{ property, requestedAt: new Date().toISOString() }, ...v]);
      notify(`Viewing approved: ${propertyTitle(property)}. Added to My Viewings.`);
    },
    [approvedUrls, setViewings, notify],
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

  const focusProperty = useCallback((rank: number) => {
    const el = document.getElementById(`property-${rank}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("is-flash");
    setTimeout(() => el?.classList.remove("is-flash"), 1200);
  }, []);

  const closePanel = useCallback(() => setPanel(null), []);
  const revealed = !!search && revealedId === search.id;
  const properties = revealed ? (search?.result?.properties ?? []) : [];
  const loading = !!search && !revealed && !search.error;

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
          <Hero
            constraintsCount={constraintsCount}
            onSubmit={runSearch}
            onOpenSettings={() => setPanel("settings")}
          />
        ) : (
          <div className="split">
            <AgentFeed
              key={search.id}
              query={search.query}
              result={search.result}
              error={search.error}
              constraintsCount={constraintsCount}
              onFollowUp={(text) => runSearch(`${search.query}. Additional instructions: ${text}`)}
              onStop={() => abortRef.current?.abort()}
              onNewSearch={goHome}
              onFocusProperty={focusProperty}
              onComplete={() => setRevealedId(search.id)}
            />

            <section className="results" aria-label="Top matches">
              <header className="pane-head">
                <div>
                  <p className="pane-kicker">Top matches</p>
                  <p className="pane-query">
                    {loading
                      ? "The agent is evaluating listings"
                      : properties.length
                        ? `${properties.length} homes selected for you`
                        : "No matches"}
                  </p>
                </div>
                {revealed && search.result && (
                  <span className={`source-badge source-${search.result.source}`}>
                    <span className="source-dot" />
                    {search.result.source === "live" ? "Live data" : "Demo data"}
                  </span>
                )}
              </header>
              <div className="pane-body cards">
                {loading && [0, 1, 2].map((i) => <PropertyCardSkeleton key={i} index={i} />)}
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
                {revealed && !properties.length && (
                  <p className="cards-empty">
                    The agent did not find a listing that fits. Add instructions on the left to
                    widen the search.
                  </p>
                )}
              </div>
            </section>
          </div>
        )}
      </main>

      <Drawer
        open={panel === "viewings"}
        title="My Viewings"
        subtitle="Appointments you approved for the agent to arrange"
        icon={<CalendarDays size={16} strokeWidth={1.75} />}
        onClose={closePanel}
      >
        <ViewingsPanel
          viewings={viewings}
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
        subtitle="Permanent information the agent always takes into account"
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
