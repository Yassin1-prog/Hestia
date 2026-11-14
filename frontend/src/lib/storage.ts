"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * useState that is mirrored to localStorage. Starts from `initial` on the server and the
 * first client render (no hydration mismatch), then loads the stored value. Storage
 * failures (private mode, blocked site data) are ignored: the app still works in memory.
 */
export function usePersistentState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) setValue(JSON.parse(raw) as T);
    } catch {
      /* ignore */
    }
    setLoaded(true);
  }, [key]);

  useEffect(() => {
    if (!loaded) return;
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  }, [key, value, loaded]);

  const update = useCallback((next: T | ((prev: T) => T)) => setValue(next), []);
  return [value, update] as const;
}
