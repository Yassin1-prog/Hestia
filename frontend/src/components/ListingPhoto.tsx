"use client";

import { ChevronLeft, ChevronRight, Home, Images } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { API_BASE } from "@/lib/api";

const isRemote = (src: string) => /^(https?:)?\/\//.test(src);

/** Ways to load one photo: straight from the portal, then through our proxy (hot-link blocks). */
function sourcesFor(src: string): string[] {
  if (!isRemote(src)) return [src];
  const absolute = src.startsWith("//") ? `https:${src}` : src;
  return [absolute, `${API_BASE}/api/image?url=${encodeURIComponent(absolute)}`];
}

interface ListingPhotoProps {
  /** Candidate photos in order; the first one that loads is shown. */
  images: string[] | undefined;
  alt: string;
  className?: string;
  /** Eager-load (above the fold / dialog). */
  priority?: boolean;
}

/**
 * A listing photo that never shows a broken image: it tries each photo directly, then via the
 * backend proxy, then falls back to a placeholder. Fades in once loaded.
 */
export function ListingPhoto({ images, alt, className = "", priority = false }: ListingPhotoProps) {
  const attempts = (images ?? []).flatMap(sourcesFor);
  const key = attempts.join("|");
  // State is tied to the photo list, so a new list starts over without a stale frame.
  const [state, setState] = useState({ key, index: 0, loaded: false });
  const { index, loaded } = state.key === key ? state : { index: 0, loaded: false };
  const setLoaded = (value: boolean) => setState({ key, index, loaded: value });
  const next = () => setState({ key, index: index + 1, loaded: false });

  const src = attempts[index];
  return (
    <div className={`photo ${loaded ? "is-loaded" : ""} ${className}`}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- remote portal photos, unknown hosts
        <img
          key={src}
          src={src}
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setLoaded(true)}
          onError={next}
        />
      ) : (
        <span className="photo-empty" role="img" aria-label="No photos available">
          <Home size={22} strokeWidth={1.5} />
          <span>No photos on the listing</span>
        </span>
      )}
    </div>
  );
}

/** Photo gallery for the details dialog: main photo, arrows, counter and thumbnails. */
export function PhotoGallery({ images, alt }: { images: string[] | undefined; alt: string }) {
  const photos = images ?? [];
  const [current, setCurrent] = useState(0);
  const count = photos.length;

  const go = useCallback(
    (delta: number) => count > 1 && setCurrent((c) => (c + delta + count) % count),
    [count],
  );

  useEffect(() => {
    if (count < 2) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, go]);

  if (!count) {
    return <ListingPhoto images={[]} alt={alt} className="gallery-main" />;
  }

  return (
    <div className="gallery">
      <div className="gallery-stage">
        {/* Remaining photos act as fallbacks if this one fails to load. */}
        <ListingPhoto
          images={[...photos.slice(current), ...photos.slice(0, current)]}
          alt={`${alt}, photo ${current + 1} of ${count}`}
          className="gallery-main"
          priority
        />
        {count > 1 && (
          <>
            <button
              type="button"
              className="gallery-nav gallery-prev"
              onClick={() => go(-1)}
              aria-label="Previous photo"
            >
              <ChevronLeft size={18} strokeWidth={2} />
            </button>
            <button
              type="button"
              className="gallery-nav gallery-next"
              onClick={() => go(1)}
              aria-label="Next photo"
            >
              <ChevronRight size={18} strokeWidth={2} />
            </button>
          </>
        )}
        <span className="photo-count">
          <Images size={12} strokeWidth={2} /> {current + 1} / {count}
        </span>
      </div>
      {count > 1 && (
        <div className="gallery-thumbs" role="tablist" aria-label="Photos">
          {photos.map((src, i) => (
            <button
              key={src}
              type="button"
              role="tab"
              aria-selected={i === current}
              aria-label={`Photo ${i + 1}`}
              className={`gallery-thumb${i === current ? " is-active" : ""}`}
              onClick={() => setCurrent(i)}
            >
              <ListingPhoto images={[src]} alt="" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
