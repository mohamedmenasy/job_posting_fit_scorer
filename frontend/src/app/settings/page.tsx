"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { S } from "@/lib/api/client";
import { useSaveScoring, useScoringSettings } from "@/lib/api/hooks";
import { COMPONENT_LABEL, cnJoin, pct } from "@/lib/format";

type Config = S["ScoringConfig"];
type Tree = Record<string, unknown>;

function getIn(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => (acc as Tree | undefined)?.[key], obj);
}

function setIn<T>(obj: T, path: string, value: unknown): T {
  const copy = structuredClone(obj) as Tree;
  const keys = path.split(".");
  let node = copy;
  for (const key of keys.slice(0, -1)) node = node[key] as Tree;
  node[keys.at(-1)!] = value;
  return copy as T;
}

export default function SettingsPage() {
  const settings = useScoringSettings();
  if (settings.isPending) return <Skeleton className="h-96 max-w-4xl" />;
  if (settings.isError) return <p className="text-status-blocked">Could not load scoring settings.</p>;
  return <SettingsForm key={settings.data.version} active={settings.data.config} defaults={settings.data.defaults} version={settings.data.version} />;
}

function NumberField({ label, path, draft, onChange, step = 0.05, min = 0, max, help }: { label: string; path: string; draft: Config; onChange: (path: string, v: number) => void; step?: number; min?: number; max?: number; help?: string }) {
  const value = getIn(draft, path) as number;
  return (
    <label className="grid grid-cols-[1fr_96px_56px] items-center gap-3 py-1">
      <span>
        {label}
        {help && <span className="text-muted-foreground block text-xs">{help}</span>}
      </span>
      <Input
        type="number"
        step={step}
        min={min}
        max={max}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(path, e.target.value === "" ? NaN : Number(e.target.value))}
        className="tabular h-8 text-right"
      />
    </label>
  );
}

function ToggleRow({ label, path, draft, onChange, children }: { label: string; path: string; draft: Config; onChange: (path: string, v: boolean) => void; children?: React.ReactNode }) {
  const enabled = getIn(draft, `${path}.enabled`) as boolean;
  return (
    <div className="border-b py-3 last:border-b-0">
      <label className="flex items-center justify-between gap-3">
        <span className="font-medium">{label}</span>
        <Switch checked={enabled} onCheckedChange={(v) => onChange(`${path}.enabled`, v)} />
      </label>
      {children && <div className={cnJoin("mt-1 grid gap-0.5 pl-3", !enabled && "opacity-50")}>{children}</div>}
    </div>
  );
}

function Group({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t py-6 md:grid-cols-[240px_1fr] md:gap-8">
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{description}</p>
      </div>
      <div className="max-w-xl">{children}</div>
    </section>
  );
}

const ARRANGEMENTS = ["remote", "hybrid", "onsite", "multiple_options", "unclear"] as const;

function SettingsForm({ active, defaults, version }: { active: Config; defaults: Config; version: number }) {
  const [draft, setDraft] = useState<Config>(active);
  const save = useSaveScoring();
  const set = (path: string, value: unknown) => setDraft((d) => setIn(d, path, value));
  const dirty = JSON.stringify(draft) !== JSON.stringify(active);
  const weights = draft.weights as unknown as Record<string, number>;
  const totalWeight = Object.values(weights).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
  const invalid = JSON.stringify(draft).includes("null");
  const p = draft.penalties;

  return (
    <form
      className="max-w-5xl pb-24"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(draft);
      }}
    >
      <PageHeader
        title="Scoring"
        description={`Version ${version}. Saving creates a new version and re-scores every job from its stored signals. No TypeSafe calls are made.`}
      />

      <Group title="Weights" description="Relative importance of each component. Components that do not apply to a job have their weight shared among the rest.">
        {Object.keys(weights).map((name) => (
          <div key={name} className="grid grid-cols-[1fr_96px_56px] items-center gap-3 py-1">
            <span>{COMPONENT_LABEL[name] ?? name}</span>
            <Input
              type="number"
              min={0}
              step={1}
              value={Number.isFinite(weights[name]) ? weights[name] : ""}
              onChange={(e) => set(`weights.${name}`, e.target.value === "" ? NaN : Number(e.target.value))}
              className="tabular h-8 text-right"
              aria-label={`${COMPONENT_LABEL[name] ?? name} weight`}
            />
            <span className="tabular text-muted-foreground text-right text-xs">{totalWeight ? pct((weights[name] ?? 0) / totalWeight) : "—"}</span>
          </div>
        ))}
        <NumberField label="Neutral platform preference" help="Value for role families you neither prefer nor avoid" path="neutral_platform_preference" draft={draft} onChange={set} />
        <NumberField label="Preferred domain blend" help="Share of the domain component taken from preferred-domain probability" path="domain_preference_blend" draft={draft} onChange={set} />
        <NumberField label="Relocation location factor" help="Credit for jobs outside preferred locations when you would relocate" path="relocation_location_factor" draft={draft} onChange={set} />
      </Group>

      <Group title="Penalties" description="Points subtracted from the base score. Each penalty applies at most once per job.">
        <ToggleRow label="Heavy use of avoided technology" path="penalties.avoided_tech_heavy" draft={draft} onChange={set}>
          <NumberField label="Points" path="penalties.avoided_tech_heavy.points" step={1} draft={draft} onChange={set} />
          <NumberField label="Min cross-platform intensity (0–4)" path="penalties.avoided_tech_heavy.min_cross_platform_intensity" step={0.1} max={4} draft={draft} onChange={set} />
          <NumberField label="Min avoided technology centrality (0–3)" path="penalties.avoided_tech_heavy.min_tech_centrality" step={0.1} max={3} draft={draft} onChange={set} />
        </ToggleRow>
        <ToggleRow label="Management-heavy role for IC preference" path="penalties.management_heavy_for_ic" draft={draft} onChange={set}>
          <NumberField label="Points" path="penalties.management_heavy_for_ic.points" step={1} draft={draft} onChange={set} />
          <NumberField label="Min management intensity (0–4)" path="penalties.management_heavy_for_ic.min_intensity" step={0.1} max={4} draft={draft} onChange={set} />
        </ToggleRow>
        <ToggleRow label="Seniority outside preferred levels" path="penalties.seniority_mismatch" draft={draft} onChange={set}>
          <NumberField label="Points" path="penalties.seniority_mismatch.points" step={1} draft={draft} onChange={set} />
          <NumberField label="Fires below preferred-level probability" path="penalties.seniority_mismatch.max_preferred_probability" max={1} draft={draft} onChange={set} />
          <NumberField label="Skipped at or above unclear probability" path="penalties.seniority_mismatch.max_unclear_probability" max={1} draft={draft} onChange={set} />
        </ToggleRow>
        <ToggleRow label="Required technology not central" path="penalties.required_tech_weak" draft={draft} onChange={set}>
          <NumberField label="Points" path="penalties.required_tech_weak.points" step={1} draft={draft} onChange={set} />
          <NumberField label="Max centrality (0–3)" path="penalties.required_tech_weak.max_centrality" step={0.1} max={3} draft={draft} onChange={set} />
        </ToggleRow>
        <ToggleRow label="Missing required skills" path="penalties.missing_required_skill" draft={draft} onChange={set}>
          <NumberField label="Points per skill with no evidence" path="penalties.missing_required_skill.points_none" step={1} draft={draft} onChange={set} />
          <NumberField label="Points per skill with weak evidence" path="penalties.missing_required_skill.points_weak" step={1} draft={draft} onChange={set} />
          <NumberField label="Cap" path="penalties.missing_required_skill.cap" step={1} draft={draft} onChange={set} />
        </ToggleRow>
        {!p.avoided_tech_heavy.enabled && !p.management_heavy_for_ic.enabled && !p.seniority_mismatch.enabled && !p.required_tech_weak.enabled && !p.missing_required_skill.enabled && (
          <p className="text-muted-foreground mt-2 text-xs">All penalties are off. Scores equal the weighted base score.</p>
        )}
      </Group>

      <Group title="Blockers" description="A blocker needs an explicit posting signal at or above the threshold and a matching answer in your profile. Signals between the two thresholds show as possible blockers to verify.">
        <NumberField label="Blocker threshold" path="blockers.threshold" max={1} draft={draft} onChange={set} />
        <NumberField label="Possible blocker threshold" path="blockers.possible_threshold" max={1} draft={draft} onChange={set} />
        {(
          [
            ["security_clearance", "Security clearance"],
            ["us_citizenship", "US citizenship"],
            ["no_sponsorship", "No visa sponsorship"],
            ["relocation", "Required relocation"],
            ["onsite_location", "In-office outside preferred locations"],
          ] as const
        ).map(([key, label]) => (
          <ToggleRow key={key} label={label} path={`blockers.${key}`} draft={draft} onChange={set} />
        ))}
        <ToggleRow label="Technology mismatch" path="blockers.technology_mismatch" draft={draft} onChange={set}>
          <NumberField label="Avoided technology is core, probability" path="blockers.technology_mismatch.avoid_core_probability" max={1} draft={draft} onChange={set} />
          <NumberField label="Required technology absent, probability" path="blockers.technology_mismatch.required_absent_probability" max={1} draft={draft} onChange={set} />
        </ToggleRow>
        <ToggleRow label="Seniority far below preference" path="blockers.seniority_far_below" draft={draft} onChange={set}>
          <NumberField label="Levels below your lowest preferred level" path="blockers.seniority_far_below.min_steps_below" step={1} min={1} draft={draft} onChange={set} />
        </ToggleRow>
      </Group>

      <Group title="Status and confidence" description="Status comes from the score and blockers only. Confidence never changes status; it decides when review is recommended.">
        <NumberField label="Strong match from" path="status_thresholds.strong_match" step={1} max={100} draft={draft} onChange={set} />
        <NumberField label="Good match from" path="status_thresholds.good_match" step={1} max={100} draft={draft} onChange={set} />
        <NumberField label="Review from" path="status_thresholds.review" step={1} max={100} draft={draft} onChange={set} />
        <NumberField label="Confident at or above" path="confidence_bands.accept" max={1} draft={draft} onChange={set} />
        <NumberField label="Uncertain below" path="confidence_bands.review" max={1} draft={draft} onChange={set} />
        <NumberField label="Min evidence line probability" path="evidence_min_probability" max={1} draft={draft} onChange={set} />
        <NumberField label="Min requirement-line kind probability" path="missing_skills.min_line_kind_probability" max={1} draft={draft} onChange={set} />
        <NumberField label="Min unlisted-skill probability" path="missing_skills.min_line_skill_none_probability" max={1} draft={draft} onChange={set} />
      </Group>

      <Group title="Work arrangement" description="How well each job arrangement suits each of your preferences, from 0 to 1.">
        <div className="overflow-x-auto">
          <table className="tabular w-full text-xs">
            <thead>
              <tr>
                <th className="text-muted-foreground py-1 text-left font-normal">You prefer</th>
                {ARRANGEMENTS.map((a) => (
                  <th key={a} className="text-muted-foreground px-1 py-1 text-right font-normal">
                    {a === "multiple_options" ? "Multiple" : a[0]!.toUpperCase() + a.slice(1)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(["remote", "hybrid", "onsite"] as const).map((pref) => (
                <tr key={pref}>
                  <td className="py-1 pr-2 text-sm">{pref[0]!.toUpperCase() + pref.slice(1)}</td>
                  {ARRANGEMENTS.map((a) => (
                    <td key={a} className="px-1 py-1">
                      <Input
                        type="number"
                        min={0}
                        max={1}
                        step={0.1}
                        aria-label={`${pref} preference, ${a} job`}
                        value={draft.arrangement_matrix?.[pref]?.[a] ?? ""}
                        onChange={(e) => set(`arrangement_matrix.${pref}.${a}`, e.target.value === "" ? NaN : Number(e.target.value))}
                        className="h-8 min-w-16 text-right"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Group>

      <div className="bg-background/95 fixed inset-x-0 bottom-0 z-20 border-t backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4">
          <Button type="submit" disabled={!dirty || invalid || save.isPending}>
            {save.isPending ? "Saving" : "Save and re-score"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setDraft(defaults)} disabled={JSON.stringify(draft) === JSON.stringify(defaults)}>
            <RotateCcw className="size-3.5" />
            Reset to defaults
          </Button>
          <span className="text-muted-foreground text-xs">
            {invalid ? "Fill in every field" : dirty ? "Unsaved changes" : "Matches the active version"}
          </span>
        </div>
      </div>
    </form>
  );
}
