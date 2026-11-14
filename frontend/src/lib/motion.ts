"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Animates a number from its previous value (0 on mount) to `target`.
 * Jumps straight to the value when the user prefers reduced motion.
 */
export function useCountUp(target: number, duration = 900, delay = 0): number {
  const [value, setValue] = useState(() => (reducedMotion() ? target : 0));
  const fromRef = useRef(value);

  useEffect(() => {
    if (reducedMotion()) {
      setValue(target);
      fromRef.current = target;
      return;
    }
    const from = fromRef.current;
    let raf = 0;
    let start = 0;
    const timer = setTimeout(() => {
      const tick = (now: number) => {
        if (!start) start = now;
        const t = Math.min(1, (now - start) / duration);
        const v = from + (target - from) * easeOutCubic(t);
        fromRef.current = v;
        setValue(v);
        if (t < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, delay);
    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
  }, [target, duration, delay]);

  return value;
}

/** Subtle 3D tilt toward the pointer. Returns props to spread on the element. */
export function useTilt(maxDeg = 2.2) {
  const ref = useRef<HTMLElement | null>(null);
  const enabled = useRef(true);

  useEffect(() => {
    enabled.current = !reducedMotion() && !window.matchMedia?.("(pointer: coarse)").matches;
  }, []);

  const onMouseMove = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      const el = ref.current;
      if (!el || !enabled.current) return;
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      // Tall cards (an outreach agent at work) tilt less, so text stays steady.
      const scale = Math.min(1, 420 / r.height);
      el.style.setProperty("--tilt-x", `${(-y * maxDeg * scale).toFixed(2)}deg`);
      el.style.setProperty("--tilt-y", `${(x * maxDeg * scale).toFixed(2)}deg`);
      el.style.setProperty("--glare-x", `${((x + 0.5) * 100).toFixed(1)}%`);
      el.style.setProperty("--glare-y", `${((y + 0.5) * 100).toFixed(1)}%`);
    },
    [maxDeg],
  );

  const onMouseLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--tilt-x", "0deg");
    el.style.setProperty("--tilt-y", "0deg");
  }, []);

  return {
    ref: (el: HTMLElement | null) => {
      ref.current = el;
    },
    onMouseMove,
    onMouseLeave,
  };
}

export type StyleWithVars = CSSProperties & Record<`--${string}`, string | number>;
