"use client";

import type { S } from "@/lib/api/client";
import type { JobsQuery } from "@/lib/api/hooks";
import { cnJoin } from "@/lib/format";

type Update = (patch: Record<string, string | string[] | boolean | null>) => void;

export function StatStrip({ stats, query, update }: { stats: S["JobStatsOut"]; query: JobsQuery; update: Update }) {
  const onlyStatus = (s: string) => query.status?.length === 1 && query.status[0] === s;
  const tiles: { label: string; value: number; sub?: string; active: boolean; onClick: () => void; tone: string }[] = [
    { label: "Jobs evaluated", value: stats.evaluated, sub: stats.pending ? `${stats.pending} in progress` : stats.failed ? `${stats.failed} failed` : `of ${stats.total}`, active: !query.status && !query.needs_review && !query.state, onClick: () => update({ status: null, needs_review: null, state: null }), tone: "" },
    { label: "Strong matches", value: stats.strong, active: onlyStatus("STRONG_MATCH"), onClick: () => update({ status: ["STRONG_MATCH"], needs_review: null, state: null }), tone: "text-status-strong" },
    { label: "Good matches", value: stats.good, active: onlyStatus("GOOD_MATCH"), onClick: () => update({ status: ["GOOD_MATCH"], needs_review: null, state: null }), tone: "text-status-good" },
    { label: "Need review", value: stats.review, active: onlyStatus("REVIEW"), onClick: () => update({ status: ["REVIEW"], needs_review: null, state: null }), tone: "text-status-review" },
    { label: "Blocked", value: stats.blocked, active: onlyStatus("BLOCKED"), onClick: () => update({ status: ["BLOCKED"], needs_review: null, state: null }), tone: "text-status-blocked" },
  ];
  if (stats.drafts > 0) {
    tiles.push({
      label: "Drafts",
      value: stats.drafts,
      sub: "need a description",
      active: query.state?.includes("draft") ?? false,
      onClick: () => update({ state: ["draft"], status: null, needs_review: null }),
      tone: "text-muted-foreground",
    });
  }
  return (
    <div className="mb-4 grid grid-cols-2 border-y sm:grid-cols-5">
      {tiles.map((t) => (
        <button
          key={t.label}
          type="button"
          onClick={t.onClick}
          aria-pressed={t.active}
          className={cnJoin(
            "hover:bg-muted/60 flex flex-col items-start gap-0.5 border-r px-4 py-3 text-left transition-colors duration-150 last:border-r-0",
            t.active && "bg-muted/60 shadow-[inset_0_-2px_0_var(--brand)]",
          )}
        >
          <span className={cnJoin("tabular text-2xl font-semibold", t.tone)}>{t.value}</span>
          <span className="text-muted-foreground text-xs">
            {t.label}
            {t.sub && <span className="block">{t.sub}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}
