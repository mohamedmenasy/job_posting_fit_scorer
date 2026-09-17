"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { S } from "@/lib/api/client";
import {
  BAND_CLASS,
  BAND_LABEL,
  COMPONENT_LABEL,
  type FitStatus,
  STATUS_CLASS,
  STATUS_FILL,
  STATUS_LABEL,
  band,
  cnJoin,
  pct,
} from "@/lib/format";

export function StatusBadge({ status }: { status: FitStatus }) {
  return (
    <span className={cnJoin("inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium", STATUS_CLASS[status])}>
      {STATUS_LABEL[status]}
    </span>
  );
}

export function ConfidenceBadge({ value, derived = false }: { value: number | null | undefined; derived?: boolean }) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  const b = band(value);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cnJoin("tabular inline-flex items-baseline gap-1 font-medium", BAND_CLASS[b])}>
          {pct(value)}
          {derived && <span className="text-muted-foreground text-[11px] font-normal">derived</span>}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {BAND_LABEL[b]} confidence{derived ? " (derived as |2p − 1| from a yes/no probability)" : ""}
      </TooltipContent>
    </Tooltip>
  );
}

export function EvaluationState({ status, error }: { status: string | null | undefined; error?: string | null }) {
  if (status === "pending" || status === "running") {
    return (
      <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        {status === "pending" ? "Queued" : "Evaluating"}
      </span>
    );
  }
  if (status === "failed") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-status-blocked inline-flex items-center gap-1.5 text-xs">
            <AlertCircle className="size-3.5" aria-hidden />
            Failed
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-80">{error ?? "Evaluation failed"}</TooltipContent>
      </Tooltip>
    );
  }
  return null;
}

/**
 * The score ledger: each weighted component's contribution laid end to end on a 0–100 track, with penalties
 * shown as a hatched bite taken from the end. The score is arithmetic, so the bar shows the arithmetic.
 */
export function ScoreLedger({ fit, compact = false }: { fit: S["FitResultOut"]; compact?: boolean }) {
  const parts = fit.components.filter((c) => c.applicable && c.contribution > 0);
  const penalty = Math.max(0, fit.base_score - fit.overall_score);
  const shades = [1, 0.8, 0.64, 0.5, 0.4, 0.32, 0.25, 0.2];
  return (
    <div
      className={cnJoin("bg-muted relative flex w-full overflow-hidden rounded-sm", compact ? "h-1.5" : "h-3")}
      role="img"
      aria-label={`Score ${Math.round(fit.overall_score)} of 100: base ${fit.base_score.toFixed(1)} minus ${penalty.toFixed(1)} penalty points`}
    >
      {parts.map((c, i) => {
        const segment = (
          <div
            key={c.name}
            className={cnJoin("h-full", STATUS_FILL[fit.status], i > 0 && "border-background border-l")}
            style={{ width: `${c.contribution}%`, opacity: shades[i] ?? 0.2 }}
          />
        );
        return compact ? (
          segment
        ) : (
          <Tooltip key={c.name}>
            <TooltipTrigger asChild>{segment}</TooltipTrigger>
            <TooltipContent>
              {COMPONENT_LABEL[c.name] ?? c.name}: +{c.contribution.toFixed(1)}
            </TooltipContent>
          </Tooltip>
        );
      })}
      {penalty > 0 && (
        <div
          className="hatch text-status-blocked/70 absolute top-0 h-full"
          style={{ left: `${fit.overall_score}%`, width: `${Math.min(penalty, fit.base_score)}%` }}
          title={`Penalties −${penalty.toFixed(1)}`}
        />
      )}
    </div>
  );
}

export function Section({
  id,
  title,
  aside,
  children,
}: {
  id: string;
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 border-t py-6 first:border-t-0 first:pt-0">
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <h2 className="text-base font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-start gap-2 py-16">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="text-muted-foreground">{body}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-muted-foreground mt-1 max-w-2xl">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
