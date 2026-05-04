import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmt(n: number | undefined | null, decimals = 2): string {
  if (n == null || isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function fmtPct(n: number | undefined | null, decimals = 2): string {
  if (n == null || isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(decimals)}%`;
}

export function fmtPrice(n: number | undefined | null): string {
  if (n == null || isNaN(n)) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtVolume(n: number | undefined | null): string {
  if (n == null || isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toString();
}

export function changeColor(n: number | undefined | null): string {
  if (n == null) return "text-nexus-muted";
  return n >= 0 ? "text-nexus-green" : "text-nexus-red";
}

export function confidenceColor(c: number): string {
  if (c >= 0.75) return "text-nexus-green";
  if (c >= 0.55) return "text-nexus-yellow";
  return "text-nexus-red";
}

export function directionColor(d: string): string {
  if (d === "bullish") return "text-nexus-green";
  if (d === "bearish") return "text-nexus-red";
  return "text-nexus-yellow";
}

// Generate a stable session ID stored in localStorage
export function getSessionId(): string {
  if (typeof window === "undefined") return "ssr-session";
  let id = localStorage.getItem("nexus_session_id");
  if (!id) {
    id = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem("nexus_session_id", id);
  }
  return id;
}
