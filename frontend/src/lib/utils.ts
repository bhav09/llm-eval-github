import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPct(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatUsd(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toFixed(4)}`;
}

export function msToSec(ms: number | undefined) {
  if (ms === undefined || Number.isNaN(ms)) return "—";
  const sec = ms / 1000;
  // Show 2 decimals for sub-second latencies, 1 for longer ones.
  const decimals = sec < 1 ? 2 : 1;
  return `${sec.toFixed(decimals)}s`;
}
