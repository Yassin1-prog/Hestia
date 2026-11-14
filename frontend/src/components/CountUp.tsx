"use client";

import { useCountUp } from "@/lib/motion";

interface CountUpProps {
  value: number;
  /** Decimals to show; defaults to the target's own (9 → 0, 9.5 → 1). */
  decimals?: number;
  duration?: number;
  delay?: number;
}

/** A number that counts up to its value instead of appearing. */
export function CountUp({ value, decimals, duration, delay }: CountUpProps) {
  const places = decimals ?? (Number.isInteger(value) ? 0 : 1);
  const current = useCountUp(value, duration, delay);
  return <span className="count-up">{current.toFixed(places)}</span>;
}
