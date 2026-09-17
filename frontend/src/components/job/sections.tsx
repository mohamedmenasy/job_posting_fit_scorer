"use client";

import { Check, ChevronRight, CircleHelp, OctagonX, TriangleAlert } from "lucide-react";
import { Fragment, useState } from "react";

import { ConfidenceBadge, Section, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { S } from "@/lib/api/client";
import { useEvaluationDetail, useEvaluations } from "@/lib/api/hooks";
import {
  COMPONENT_LABEL,
  COMPONENT_SCALE,
  cnJoin,
  dateTime,
  enumLabel,
  fixed,
  humanize,
  pct,
  score,
  shortId,
} from "@/lib/format";

type Fit = S["FitResultOut"];
type Signals = S["SemanticSignals"];
type Meta = S["MetaOut"] | undefined;
type Choice = S["ChoiceSignal"];
type ScoreSig = S["ScoreSignal"];
type Noul = S["NoulSignal"];

const EVIDENCE_MIN = 0.5;

/** Scroll to a posting line and flash it. */
export function goToLine(lineId: string) {
  const el = document.getElementById(`line-${lineId}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("bg-brand-soft");
  window.setTimeout(() => el.classList.remove("bg-brand-soft"), 1600);
}

export function LineLink({ lineId }: { lineId: string }) {
  return (
    <button
      type="button"
      onClick={() => goToLine(lineId)}
      className="text-brand hover:bg-brand-soft rounded px-1 font-mono text-[11px] transition-colors duration-150"
      aria-label={`Show posting line ${lineId}`}
    >
      {lineId}
    </button>
  );
}

function evidenceFor(signals: Signals | null | undefined, target: string) {
  const ev = signals?.evidence[target];
  return ev && ev.line_id && ev.probability >= EVIDENCE_MIN ? ev : null;
}

function Quote({ text, lineId }: { text: string | null | undefined; lineId?: string | null }) {
  if (!text) return <p className="text-muted-foreground text-xs">No supporting line found</p>;
  return (
    <blockquote className="border-muted-foreground/30 text-muted-foreground mt-1 flex items-start gap-2 border-l-2 pl-3 text-xs leading-relaxed">
      <span className="flex-1">“{text}”</span>
      {lineId && <LineLink lineId={lineId} />}
    </blockquote>
  );
}

// ---------------------------------------------------------------- 2. Why apply

export function WhyApply({ fit }: { fit: Fit }) {
  const strengths = fit.explanations.filter((e) => e.section === "strength");
  const concerns = fit.explanations.filter((e) => e.section === "concern");
  const uncertain = fit.explanations.filter((e) => e.section === "uncertain");
  const notes = fit.explanations.filter((e) => e.section === "note");
  const item = (e: S["Explanation"], icon: React.ReactNode) => (
    <li key={e.text} className="flex items-start gap-2 py-1">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="flex-1 leading-snug">{e.text}</span>
      {e.evidence_line_id && <LineLink lineId={e.evidence_line_id} />}
    </li>
  );
  return (
    <Section id="why" title="Why apply">
      <div className="grid gap-6 lg:grid-cols-3">
        <div>
          <h3 className="text-muted-foreground mb-1 text-xs font-medium">Strengths</h3>
          <ul>
            {strengths.length ? strengths.map((e) => item(e, <Check className="text-status-strong size-3.5" />)) : <li className="text-muted-foreground py-1">None detected</li>}
          </ul>
        </div>
        <div>
          <h3 className="text-muted-foreground mb-1 text-xs font-medium">Concerns</h3>
          <ul>
            {concerns.length ? concerns.map((e) => item(e, <TriangleAlert className="text-status-review size-3.5" />)) : <li className="text-muted-foreground py-1">None detected</li>}
          </ul>
        </div>
        <div>
          <h3 className="text-muted-foreground mb-1 text-xs font-medium">Blockers</h3>
          <ul>
            {fit.hard_blockers.length ? (
              fit.hard_blockers.map((b) => (
                <li key={b.type} className="flex items-start gap-2 py-1">
                  <OctagonX className="text-status-blocked mt-0.5 size-3.5 shrink-0" />
                  <span className="leading-snug">{b.reason}</span>
                </li>
              ))
            ) : (
              <li className="text-muted-foreground py-1">None detected</li>
            )}
          </ul>
        </div>
      </div>
      {(uncertain.length > 0 || notes.length > 0) && (
        <div className="text-muted-foreground mt-4 grid gap-1 border-t pt-3 text-xs">
          {notes.map((e) => (
            <p key={e.text}>{e.text}</p>
          ))}
          {uncertain.map((e) => (
            <p key={e.text} className="flex items-center gap-1.5">
              <CircleHelp className="size-3" /> Low confidence: {e.text}
            </p>
          ))}
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- 3. Fit overview

export function FitOverview({ fit }: { fit: Fit }) {
  const penaltyTotal = fit.penalties.reduce((sum, p) => sum + p.points, 0);
  return (
    <Section
      id="fit"
      title="Fit overview"
      aside={<span className="text-muted-foreground text-xs">Deterministic scoring from the signals below, no model involved</span>}
    >
      <div className="grid grid-cols-[minmax(140px,180px)_1fr_56px_96px_64px] items-center gap-x-4 gap-y-2.5">
        <span className="text-muted-foreground text-xs">Component</span>
        <span className="text-muted-foreground text-xs">Value</span>
        <span className="text-muted-foreground text-right text-xs">Signal</span>
        <span className="text-muted-foreground text-right text-xs">Weight</span>
        <span className="text-muted-foreground text-right text-xs">Points</span>
        {fit.components.map((c) => (
          <Fragment key={c.name}>
            <span className={cnJoin(!c.applicable && "text-muted-foreground")}>{COMPONENT_LABEL[c.name] ?? c.name}</span>
            {c.applicable && c.value != null ? (
              <div className="bg-muted h-2 overflow-hidden rounded-sm">
                <div className="bg-brand h-full" style={{ width: `${c.value * 100}%` }} />
              </div>
            ) : (
              <span className="text-muted-foreground text-xs">{c.reason}</span>
            )}
            <span className="tabular text-right">
              {c.applicable && c.value != null
                ? COMPONENT_SCALE[c.name]
                  ? `${fixed(c.value * COMPONENT_SCALE[c.name]!)}/${COMPONENT_SCALE[c.name]}`
                  : pct(c.value)
                : "—"}
            </span>
            <span className="tabular text-muted-foreground text-right">
              {c.weight}
              {c.applicable && <span className="text-foreground"> ({pct(c.effective_weight)})</span>}
            </span>
            <span className="tabular text-right font-medium">{c.applicable ? `+${fixed(c.contribution)}` : "—"}</span>
          </Fragment>
        ))}
      </div>
      <div className="mt-4 grid gap-1 border-t pt-3">
        <div className="tabular flex justify-between">
          <span>Base score</span>
          <span>{fixed(fit.base_score)}</span>
        </div>
        {fit.penalties.map((p) => (
          <div key={p.type} className="tabular text-status-blocked flex justify-between">
            <span>{p.reason}</span>
            <span>−{fixed(p.points)}</span>
          </div>
        ))}
        <div className="tabular flex justify-between font-semibold">
          <span>Overall score{penaltyTotal > 0 && fit.base_score - penaltyTotal < 0 ? " (floored at 0)" : ""}</span>
          <span>{fixed(fit.overall_score)}</span>
        </div>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- 4. Classification

export function Classification({ signals, meta }: { signals: Signals; meta: Meta }) {
  const rows: [string, React.ReactNode, number | null, boolean?][] = [
    ["Platform", enumLabel(meta, "RoleFamily", signals.role_family.value), signals.role_family.confidence],
    ["Level from scope", enumLabel(meta, "Seniority", signals.seniority.value), signals.seniority.confidence],
    ["Level from title", enumLabel(meta, "Seniority", signals.title_level.value), signals.title_level.confidence],
    ["Domain", enumLabel(meta, "Domain", signals.domain.value), signals.domain.confidence],
    ["Work arrangement", enumLabel(meta, "WorkArrangement", signals.work_arrangement.value), signals.work_arrangement.confidence],
    ["Kotlin Multiplatform", enumLabel(meta, "RequirementLevel", signals.kmp_requirement.value), signals.kmp_requirement.confidence],
    ["Years required", enumLabel(meta, "YearsBucket", signals.min_years_required.value), signals.min_years_required.confidence],
    ["Android relevance", `${fixed(signals.android_relevance.score)}/4`, signals.android_relevance.confidence],
    ["Management intensity", `${fixed(signals.management_intensity.score)}/4`, signals.management_intensity.confidence],
    ["Cross-platform intensity", `${fixed(signals.cross_platform_intensity.score)}/4`, signals.cross_platform_intensity.confidence],
    ["Staff-level IC role", pct(signals.staff_ic_signal.probability), signals.staff_ic_signal.derived_confidence, true],
  ];
  return (
    <Section id="classification" title="Classification">
      <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2 xl:grid-cols-3">
        {rows.map(([label, value, conf, derived]) => (
          <div key={label} className="flex items-baseline justify-between gap-3 border-b border-dashed py-1.5">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="flex items-baseline gap-3">
              <span className="font-medium">{value}</span>
              <ConfidenceBadge value={conf} derived={derived} />
            </dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

// ---------------------------------------------------------------- 5. Skills

const IMPORTANCE_LABEL = { critical: "Critical", important: "Required", nice_to_have: "Nice to have" } as const;
const EVIDENCE_CLASS = { none: "text-status-blocked", weak: "text-status-review", partial: "text-muted-foreground" } as const;

export function Skills({ fit, signals }: { fit: Fit; signals: Signals }) {
  return (
    <Section id="skills" title="Skills">
      <h3 className="text-muted-foreground mb-2 text-xs font-medium">Missing or weak</h3>
      {fit.missing_skills.length === 0 ? (
        <p className="text-muted-foreground">No explicit requirements are missing from your resume.</p>
      ) : (
        <ul className="divide-y">
          {fit.missing_skills.map((m, i) => (
            <li key={`${m.skill}-${i}`} className="grid gap-1 py-2">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className={cnJoin("font-medium", m.source === "requirement_line" && "font-normal italic")}>
                  {m.source === "requirement_line" ? `“${m.skill}”` : m.skill}
                </span>
                <span className="text-muted-foreground text-xs">{IMPORTANCE_LABEL[m.importance]}</span>
                <span className={cnJoin("text-xs", EVIDENCE_CLASS[m.candidate_evidence])}>{humanize(m.candidate_evidence)} resume evidence</span>
                {m.impact === "significant" && <span className="text-status-review text-xs">Significant gap</span>}
                <span className="ml-auto flex gap-1">
                  {m.line_ids.map((id) => (
                    <LineLink key={id} lineId={id} />
                  ))}
                </span>
              </div>
              {m.source === "tracked_skill" &&
                m.line_ids.map((id) => <Quote key={id} text={signals.all_lines[id]} />)}
            </li>
          ))}
        </ul>
      )}
      <h3 className="text-muted-foreground mt-6 mb-2 text-xs font-medium">Asked for in the posting</h3>
      {fit.skill_matches.length === 0 ? (
        <p className="text-muted-foreground">None of your tracked skills appear in this posting.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Skill</TableHead>
              <TableHead>In posting</TableHead>
              <TableHead className="text-right">Your evidence</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Lines</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fit.skill_matches.map((m) => (
              <TableRow key={m.skill}>
                <TableCell className="font-medium">{m.skill}</TableCell>
                <TableCell>{humanize(m.requirement_level)}</TableCell>
                <TableCell className="tabular text-right">{pct(m.candidate_match)}</TableCell>
                <TableCell className="text-right">
                  <ConfidenceBadge value={m.confidence} />
                </TableCell>
                <TableCell>
                  {m.evidence_line_ids.map((id) => (
                    <LineLink key={id} lineId={id} />
                  ))}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- 6. Blockers

export function Blockers({ fit }: { fit: Fit }) {
  const all = [
    ...fit.hard_blockers.map((b) => ({ ...b, kind: "Blocker" as const })),
    ...fit.possible_blockers.map((b) => ({ ...b, kind: "Possible blocker, verify" as const })),
  ];
  return (
    <Section id="blockers" title="Blockers">
      {all.length === 0 ? (
        <p className="text-muted-foreground">None detected. Blockers need an explicit statement in the posting and a matching answer in your profile.</p>
      ) : (
        <ul className="divide-y">
          {all.map((b) => (
            <li key={`${b.kind}-${b.type}-${b.reason}`} className="py-2">
              <div className="flex flex-wrap items-baseline gap-3">
                <span className={cnJoin("text-xs font-medium", b.kind === "Blocker" ? "text-status-blocked" : "text-status-review")}>{b.kind}</span>
                <span className="font-medium">{b.reason}</span>
                <span className="text-muted-foreground tabular ml-auto text-xs">posting signal {pct(b.confidence)}</span>
              </div>
              {b.evidence && <Quote text={b.evidence} />}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- 7. Work authorization

export function WorkAuthorization({ signals, meta }: { signals: Signals; meta: Meta }) {
  const noul = (label: string, sig: Noul, target: string) => ({ label, value: `${pct(sig.probability)} likely`, conf: sig.derived_confidence, derived: true, target });
  const rows = [
    {
      label: "Sponsorship",
      value: enumLabel(meta, "WorkAuthSignal", signals.work_authorization_signal.value),
      conf: signals.work_authorization_signal.confidence,
      derived: false,
      target: "work_authorization_signal",
    },
    noul("Security clearance required", signals.security_clearance_required, "security_clearance_required"),
    noul("US citizenship required", signals.us_citizenship_required, "us_citizenship_required"),
    noul("Relocation required", signals.requires_relocation, "requires_relocation"),
  ];
  return (
    <Section id="authorization" title="Work authorization">
      <ul className="divide-y">
        {rows.map((r) => {
          const ev = evidenceFor(signals, r.target);
          return (
            <li key={r.label} className="grid gap-1 py-2 sm:grid-cols-[220px_1fr]">
              <div className="flex items-baseline justify-between gap-3 sm:block">
                <div className="text-muted-foreground">{r.label}</div>
                <div className="flex items-baseline gap-2">
                  <span className="font-medium">{r.value}</span>
                  <ConfidenceBadge value={r.conf} derived={r.derived} />
                </div>
              </div>
              <Quote text={ev?.text} lineId={ev?.line_id} />
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground mt-2 text-xs">
        Only explicit statements count. “Not stated” never means sponsorship is available.
      </p>
    </Section>
  );
}

// ---------------------------------------------------------------- 8. Signals

type SignalRow = { id: string; kind: "choice" | "score" | "noul"; display: string; conf: number; probabilities: [string, number][] };

function toRow(id: string, sig: Choice | ScoreSig | Noul): SignalRow {
  if ("value" in sig) {
    return { id, kind: "choice", display: sig.value, conf: sig.confidence, probabilities: Object.entries(sig.probabilities) };
  }
  if ("levels" in sig) {
    return { id, kind: "score", display: `${fixed(sig.score, 2)} / ${sig.levels - 1}`, conf: sig.confidence, probabilities: Object.entries(sig.probabilities) };
  }
  return { id, kind: "noul", display: `p = ${fixed(sig.probability, 2)}`, conf: sig.derived_confidence, probabilities: [["yes", sig.probability], ["no", 1 - sig.probability]] };
}

const NAMED_SIGNALS = [
  "role_family", "android_relevance", "seniority", "title_level", "staff_ic_signal", "management_intensity",
  "kmp_requirement", "cross_platform_intensity", "domain", "work_arrangement", "requires_relocation",
  "security_clearance_required", "us_citizenship_required", "work_authorization_signal", "min_years_required",
  "technical_fit", "seniority_fit", "domain_fit", "role_preference_fit", "location_match",
] as const;

export function SignalsTable({ evaluation }: { evaluation: S["EvaluationDetailOut"] }) {
  const signals = evaluation.signals!;
  const [open, setOpen] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);
  const detail = useEvaluationDetail(evaluation.id, rawOpen);
  const rows: SignalRow[] = [
    ...NAMED_SIGNALS.flatMap((id) => (signals[id] ? [toRow(id, signals[id]!)] : [])),
    ...Object.entries(signals.skills).flatMap(([sid, s]) => [toRow(`skill_req.${sid}`, s.requirement), toRow(`skill_ev.${sid}`, s.evidence)]),
    ...Object.entries(signals.technologies).map(([slug, s]) => toRow(`tech_centrality.${slug}`, s)),
    ...signals.lines.flatMap((l) => [toRow(`line_kind.${l.id}`, l.kind), toRow(`line_skill.${l.id}`, l.skill), toRow(`line_ev.${l.id}`, l.evidence)]),
  ];
  return (
    <Section
      id="signals"
      title="TypeSafe signals"
      aside={
        <Dialog open={rawOpen} onOpenChange={setRawOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm">
              Raw responses
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden sm:max-w-4xl">
            <DialogHeader>
              <DialogTitle>Raw TypeSafe responses</DialogTitle>
            </DialogHeader>
            <pre className="bg-muted max-h-[70vh] overflow-auto rounded p-3 font-mono text-[11px] leading-relaxed">
              {detail.isPending
                ? "Loading"
                : JSON.stringify(detail.data?.raw_typesafe_response ?? [], null, 2) === "[]"
                  ? "No raw responses stored (fake evaluator)."
                  : JSON.stringify(detail.data?.raw_typesafe_response, null, 2)}
            </pre>
          </DialogContent>
        </Dialog>
      }
    >
      <dl className="text-muted-foreground mb-4 flex flex-wrap gap-x-8 gap-y-1 text-xs">
        <div>Model <span className="text-foreground font-mono">{evaluation.model}</span></div>
        <div>Evaluator <span className="text-foreground font-mono">{evaluation.evaluator_version}</span></div>
        <div>Input tokens <span className="text-foreground tabular">{evaluation.input_tokens ?? "—"}</span></div>
        <div>Output tokens <span className="text-foreground tabular">{evaluation.output_tokens ?? "—"}</span></div>
        <div>Latency <span className="text-foreground tabular">{evaluation.latency_ms ?? "—"} ms</span></div>
        <div>Questions <span className="text-foreground tabular">{rows.length + Object.keys(signals.evidence).length}</span></div>
      </dl>
      <div className="max-h-[480px] overflow-auto rounded border">
        <Table>
          <TableHeader className="bg-background sticky top-0">
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Signal</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Answer</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <TableRow className="cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                  <TableCell>
                    <ChevronRight className={cnJoin("size-3.5 transition-transform duration-150", open === r.id && "rotate-90")} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="text-muted-foreground">{humanize(r.kind)}</TableCell>
                  <TableCell className="tabular">{r.display}</TableCell>
                  <TableCell className="text-right">
                    <ConfidenceBadge value={r.conf} derived={r.kind === "noul"} />
                  </TableCell>
                </TableRow>
                {open === r.id && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell />
                    <TableCell colSpan={4}>
                      <div className="grid max-w-lg gap-1 py-1">
                        {[...r.probabilities]
                          .sort((a, b) => (r.kind === "score" ? Number(a[0]) - Number(b[0]) : b[1] - a[1]))
                          .slice(0, 12)
                          .map(([label, p]) => (
                            <div key={label} className="grid grid-cols-[140px_1fr_48px] items-center gap-3 text-xs">
                              <span className="truncate font-mono">{r.kind === "score" ? `level ${label}` : label}</span>
                              <div className="bg-muted h-1.5 rounded-sm">
                                <div className="bg-brand h-full rounded-sm" style={{ width: `${p * 100}%` }} />
                              </div>
                              <span className="tabular text-right">{pct(p)}</span>
                            </div>
                          ))}
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </div>
      <details className="mt-4 text-xs">
        <summary className="text-muted-foreground cursor-pointer">Evidence line picks</summary>
        <ul className="mt-2 grid gap-1">
          {Object.entries(signals.evidence).map(([target, ev]) => (
            <li key={target} className="flex items-center gap-3">
              <span className="w-56 font-mono">evidence.{target}</span>
              {ev.line_id ? <LineLink lineId={ev.line_id} /> : <span className="text-muted-foreground">none</span>}
              <span className="tabular text-muted-foreground">{pct(ev.probability)}</span>
            </li>
          ))}
        </ul>
      </details>
    </Section>
  );
}

// ---------------------------------------------------------------- 9. Posting

export function Posting({ signals, fit }: { signals: Signals; fit: Fit | null }) {
  const citations = new Map<string, string[]>();
  const cite = (lineId: string | null | undefined, by: string) => {
    if (!lineId) return;
    citations.set(lineId, [...(citations.get(lineId) ?? []), by]);
  };
  for (const [target, ev] of Object.entries(signals.evidence)) {
    if (ev.probability >= EVIDENCE_MIN) cite(ev.line_id, `evidence for ${target}`);
  }
  for (const e of fit?.explanations ?? []) cite(e.evidence_line_id, e.text);
  for (const m of fit?.missing_skills ?? []) m.line_ids.forEach((id) => cite(id, `missing: ${m.source === "tracked_skill" ? m.skill : "requirement"}`));
  return (
    <Section id="posting" title="Original posting" aside={<span className="text-muted-foreground text-xs">Highlighted lines are cited by signals or explanations</span>}>
      <ol className="grid gap-px">
        {Object.entries(signals.all_lines).map(([id, text]) => {
          const cited = citations.get(id);
          const line = (
            <li
              id={`line-${id}`}
              className={cnJoin(
                "grid scroll-mt-24 grid-cols-[48px_1fr] gap-3 rounded-sm px-2 py-1 transition-colors duration-150",
                cited && "bg-status-review/10",
              )}
            >
              <span className="text-muted-foreground pt-px font-mono text-[11px]">{id}</span>
              <span className={cnJoin("leading-relaxed", text.endsWith(":") && "font-medium")}>{text}</span>
            </li>
          );
          return cited ? (
            <Tooltip key={id}>
              <TooltipTrigger asChild>{line}</TooltipTrigger>
              <TooltipContent side="left" className="max-w-72">
                <ul className="grid gap-0.5">
                  {[...new Set(cited)].map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </TooltipContent>
            </Tooltip>
          ) : (
            <Fragment key={id}>{line}</Fragment>
          );
        })}
      </ol>
    </Section>
  );
}

// ---------------------------------------------------------------- 10. History

export function History({ jobId }: { jobId: string }) {
  const history = useEvaluations(jobId);
  const rows = (history.data ?? []).flatMap((ev): { ev: S["EvaluationOut"]; fit: Fit | null }[] =>
    ev.fit_results.length ? ev.fit_results.map((fit) => ({ ev, fit })) : [{ ev, fit: null }],
  );
  return (
    <Section id="history" title="History" aside={<span className="text-muted-foreground text-xs">Evaluations call TypeSafe; re-scores reuse stored signals</span>}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Scored</TableHead>
            <TableHead>Evaluation</TableHead>
            <TableHead>Evaluator</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Profile</TableHead>
            <TableHead>Scoring</TableHead>
            <TableHead className="text-right">Score</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...rows].reverse().map(({ ev, fit }) => (
            <TableRow key={fit?.id ?? ev.id}>
              <TableCell className="tabular">{dateTime(fit?.created_at ?? ev.created_at)}</TableCell>
              <TableCell className="font-mono text-xs">{shortId(ev.id)}</TableCell>
              <TableCell className="font-mono text-xs">{ev.evaluator_version ?? "—"}</TableCell>
              <TableCell className="font-mono text-xs">{ev.model ?? "—"}</TableCell>
              <TableCell className="font-mono text-xs">{fit ? shortId(fit.profile_version_id) : "—"}</TableCell>
              <TableCell className="tabular">{fit ? `v${fit.scoring_config_version}` : "—"}</TableCell>
              <TableCell className="tabular text-right">{fit ? score(fit.overall_score) : "—"}</TableCell>
              <TableCell>{fit ? <StatusBadge status={fit.status} /> : <span className="text-muted-foreground">{humanize(ev.status)}</span>}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Section>
  );
}
