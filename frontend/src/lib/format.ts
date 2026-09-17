import type { S } from "./api/client";

export type Band = "accepted" | "review" | "uncertain";
export type FitStatus = S["FitResultOut"]["status"];

export function band(confidence: number): Band {
  if (confidence >= 0.8) return "accepted";
  return confidence >= 0.6 ? "review" : "uncertain";
}

export const BAND_LABEL: Record<Band, string> = {
  accepted: "Confident",
  review: "Review recommended",
  uncertain: "Uncertain",
};

export const BAND_CLASS: Record<Band, string> = {
  accepted: "text-status-strong",
  review: "text-status-review",
  uncertain: "text-status-blocked",
};

export const STATUS_LABEL: Record<FitStatus, string> = {
  STRONG_MATCH: "Strong match",
  GOOD_MATCH: "Good match",
  REVIEW: "Review",
  LOW_MATCH: "Low match",
  BLOCKED: "Blocked",
};

/** Text + tinted background per fit status; colors come from --status-* tokens. */
export const STATUS_CLASS: Record<FitStatus, string> = {
  STRONG_MATCH: "text-status-strong bg-status-strong/10 border-status-strong/30",
  GOOD_MATCH: "text-status-good bg-status-good/10 border-status-good/30",
  REVIEW: "text-status-review bg-status-review/10 border-status-review/30",
  LOW_MATCH: "text-status-low bg-status-low/10 border-status-low/30",
  BLOCKED: "text-status-blocked bg-status-blocked/10 border-status-blocked/30",
};

export const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);
export const score = (x: number | null | undefined) => (x == null ? "—" : Math.round(x).toString());
export const fixed = (x: number, digits = 1) => x.toFixed(digits);

export function humanize(value: string): string {
  const text = value.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

type Meta = S["MetaOut"] | undefined;

export function enumLabel(meta: Meta, enumName: string, value: string | null | undefined): string {
  if (value == null) return "—";
  return meta?.enums[enumName]?.find((o) => o.value === value)?.label ?? humanize(value);
}

export function enumOptions(meta: Meta, enumName: string): S["EnumOption"][] {
  return meta?.enums[enumName] ?? [];
}

export const COMPONENT_LABEL: Record<string, string> = {
  technical: "Technical fit",
  android: "Android relevance",
  seniority: "Seniority fit",
  role_preference: "Role preference",
  platform: "Platform",
  domain: "Domain",
  work_arrangement: "Work arrangement",
  management: "Management",
};

/** Components that are exactly one Score question, shown as x/levels-1 (spec §11.1). Domain is excluded: it blends
 * domain fit with preferred-domain probability when preferred domains are set. */
export const COMPONENT_SCALE: Record<string, number> = { technical: 4, android: 4, seniority: 4, role_preference: 3 };

export function shortId(id: string) {
  return id.slice(0, 8);
}

export function dateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function cnJoin(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}
