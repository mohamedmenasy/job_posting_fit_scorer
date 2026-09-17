"use client";

import { Plus, RotateCcw, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common";
import { MultiSelect } from "@/components/multi-select";
import { TagInput } from "@/components/tag-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { S } from "@/lib/api/client";
import { type ProfileIn, useExtractResume, useMeta, useProfile, useSaveProfile } from "@/lib/api/hooks";
import { cnJoin, enumOptions } from "@/lib/format";

type Prefs = S["CandidatePreferences"];
type Facts = S["BlockerFacts"];

const EMPTY_PREFS: Prefs = {
  preferred_roles: [],
  preferred_locations: [],
  required_technologies: [],
  preferred_technologies: [],
  avoid_technologies: [],
  preferred_levels: [],
  preferred_role_families: [],
  avoided_role_families: [],
  preferred_domains: [],
  remote_preference: "any",
  willing_to_relocate: false,
  management_preference: "any",
  years_experience: null,
  work_authorization_notes: null,
};

export default function ProfilePage() {
  const profile = useProfile();
  const meta = useMeta();
  if (profile.isPending || meta.isPending) {
    return <Skeleton className="h-96 max-w-3xl" />;
  }
  if (profile.isError || meta.isError) {
    return <p className="text-status-blocked">Could not load your profile. Check that the backend is running.</p>;
  }
  const initial: ProfileIn = profile.data
    ? {
        resume_text: profile.data.resume_text,
        preferences: { ...EMPTY_PREFS, ...profile.data.preferences },
        blocker_facts: profile.data.blocker_facts,
        tracked_skills: profile.data.tracked_skills,
      }
    : { resume_text: "", preferences: EMPTY_PREFS, blocker_facts: {}, tracked_skills: meta.data.default_tracked_skills };
  return <ProfileForm key={profile.data?.id ?? "new"} initial={initial} meta={meta.data} isNew={!profile.data} />;
}

function Hint({ kind }: { kind: "rescore" | "reevaluate" }) {
  return (
    <span
      className={cnJoin(
        "rounded px-1.5 py-px text-[11px] font-normal",
        kind === "rescore" ? "bg-muted text-muted-foreground" : "bg-status-review/10 text-status-review",
      )}
    >
      {kind === "rescore" ? "Instant re-score" : "Needs re-evaluation"}
    </span>
  );
}

function Field({
  label,
  htmlFor,
  hint,
  help,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: "rescore" | "reevaluate";
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <div className="flex items-center gap-2">
        <Label htmlFor={htmlFor}>{label}</Label>
        {hint && <Hint kind={hint} />}
      </div>
      {children}
      {help && <p className="text-muted-foreground text-xs">{help}</p>}
    </div>
  );
}

function Group({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t py-6 md:grid-cols-[220px_1fr] md:gap-8">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {description && <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{description}</p>}
      </div>
      <div className="grid gap-5">{children}</div>
    </section>
  );
}

const SELECTED = "px-3 data-[state=on]:bg-brand-soft data-[state=on]:text-brand data-[state=on]:font-medium";

function FactControl({ id, label, value, onChange }: { id: string; label: string; value: boolean | null | undefined; onChange: (v: boolean | null) => void }) {
  const current = value === true ? "yes" : value === false ? "no" : "unset";
  return (
    <ToggleGroup
      id={id}
      aria-label={label}
      type="single"
      variant="outline"
      size="sm"
      value={current}
      onValueChange={(v) => v && onChange(v === "yes" ? true : v === "no" ? false : null)}
    >
      <ToggleGroupItem value="yes" className={SELECTED}>Yes</ToggleGroupItem>
      <ToggleGroupItem value="no" className={SELECTED}>No</ToggleGroupItem>
      <ToggleGroupItem value="unset" className={SELECTED}>Not set</ToggleGroupItem>
    </ToggleGroup>
  );
}

function ProfileForm({ initial, meta, isNew }: { initial: ProfileIn; meta: S["MetaOut"]; isNew: boolean }) {
  const [draft, setDraft] = useState<ProfileIn>(initial);
  const save = useSaveProfile();
  const extract = useExtractResume();
  const fileRef = useRef<HTMLInputElement>(null);
  const prefs = draft.preferences;
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const setPrefs = (patch: Partial<Prefs>) => setDraft((d) => ({ ...d, preferences: { ...d.preferences, ...patch } }));
  const setFacts = (patch: Partial<Facts>) => setDraft((d) => ({ ...d, blocker_facts: { ...d.blocker_facts, ...patch } }));
  const setSkills = (tracked_skills: S["TrackedSkill"][]) => setDraft((d) => ({ ...d, tracked_skills }));

  const techLists = ["required_technologies", "preferred_technologies", "avoid_technologies"] as const;
  const techConflict = (() => {
    const seen = new Map<string, string>();
    for (const list of techLists) {
      for (const t of prefs[list]) {
        const key = t.toLowerCase();
        if (seen.has(key) && seen.get(key) !== list) return t;
        seen.set(key, list);
      }
    }
    return null;
  })();
  const levels = enumOptions(meta, "Seniority").filter((o) => o.value !== "unclear");
  const families = enumOptions(meta, "RoleFamily");

  async function onUpload(file: File | undefined) {
    if (!file) return;
    const result = await extract.mutateAsync(file).catch(() => null);
    if (result) {
      setDraft((d) => ({ ...d, resume_text: result.text }));
      toast.success("Resume text extracted. Review it before saving.");
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <form
      className="max-w-4xl pb-24"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(draft);
      }}
    >
      <PageHeader
        title="Profile"
        description={
          isNew
            ? "Add your resume and preferences. Jobs are evaluated against this profile."
            : "Each save creates a new profile version. Scoring preferences re-score your jobs instantly; resume, roles, locations, technologies and skills need a re-evaluation."
        }
      />

      <Group title="Resume" description="Sent to TypeSafe with each evaluation, so fit questions can compare it with the posting.">
        <Field label="Resume text" htmlFor="resume" hint="reevaluate">
          <Textarea
            id="resume"
            required
            value={draft.resume_text}
            onChange={(e) => setDraft((d) => ({ ...d, resume_text: e.target.value }))}
            className="max-h-[28rem] min-h-72 font-mono text-xs leading-relaxed"
            placeholder="Paste your resume, or upload a file"
          />
        </Field>
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt"
            className="sr-only"
            id="resume-file"
            onChange={(e) => onUpload(e.target.files?.[0])}
          />
          <Button type="button" variant="outline" size="sm" disabled={extract.isPending} onClick={() => fileRef.current?.click()}>
            <Upload className="size-3.5" />
            {extract.isPending ? "Extracting text" : "Upload .pdf, .docx or .txt"}
          </Button>
          <span className="text-muted-foreground text-xs">Up to 5 MB. Only the extracted text is kept.</span>
        </div>
      </Group>

      <Group title="Roles and locations" description="Used in fit questions sent to TypeSafe.">
        <Field label="Preferred roles" htmlFor="roles" hint="reevaluate">
          <TagInput id="roles" value={prefs.preferred_roles} onChange={(v) => setPrefs({ preferred_roles: v })} placeholder="Staff Android Engineer, Mobile Tech Lead" />
        </Field>
        <Field label="Preferred locations" htmlFor="locations" hint="reevaluate">
          <TagInput id="locations" value={prefs.preferred_locations} onChange={(v) => setPrefs({ preferred_locations: v })} placeholder="Remote US, Bay Area" />
        </Field>
      </Group>

      <Group title="Technologies" description="Each technology gets a centrality question. A technology can be in only one list.">
        {techLists.map((list) => (
          <Field
            key={list}
            label={{ required_technologies: "Required", preferred_technologies: "Preferred", avoid_technologies: "Avoid" }[list]}
            htmlFor={list}
            hint="reevaluate"
          >
            <TagInput id={list} value={prefs[list]} onChange={(v) => setPrefs({ [list]: v })} placeholder="Type and press Enter" />
          </Field>
        ))}
        {techConflict && <p className="text-status-blocked text-xs">“{techConflict}” appears in more than one list.</p>}
      </Group>

      <Group title="Scoring preferences" description="Never sent to TypeSafe. Changing these re-scores stored signals with no API calls.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Preferred levels" htmlFor="levels" hint="rescore">
            <MultiSelect id="levels" options={levels} value={prefs.preferred_levels} onChange={(v) => setPrefs({ preferred_levels: v })} />
          </Field>
          <Field label="Preferred domains" htmlFor="domains" hint="rescore">
            <MultiSelect id="domains" options={enumOptions(meta, "Domain")} value={prefs.preferred_domains} onChange={(v) => setPrefs({ preferred_domains: v })} />
          </Field>
          <Field label="Preferred platforms" htmlFor="families" hint="rescore">
            <MultiSelect
              id="families"
              options={families}
              value={prefs.preferred_role_families}
              disabledValues={prefs.avoided_role_families}
              onChange={(v) => setPrefs({ preferred_role_families: v })}
            />
          </Field>
          <Field label="Avoided platforms" htmlFor="avoided" hint="rescore">
            <MultiSelect
              id="avoided"
              options={families}
              value={prefs.avoided_role_families}
              placeholder="None"
              disabledValues={prefs.preferred_role_families}
              onChange={(v) => setPrefs({ avoided_role_families: v })}
            />
          </Field>
          <Field label="Work arrangement" htmlFor="remote" hint="rescore">
            <Select value={prefs.remote_preference} onValueChange={(v) => setPrefs({ remote_preference: v as Prefs["remote_preference"] })}>
              <SelectTrigger id="remote" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any</SelectItem>
                <SelectItem value="remote">Remote</SelectItem>
                <SelectItem value="hybrid">Hybrid</SelectItem>
                <SelectItem value="onsite">Onsite</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Management" htmlFor="management" hint="rescore">
            <Select
              value={prefs.management_preference}
              onValueChange={(v) => setPrefs({ management_preference: v as Prefs["management_preference"] })}
            >
              <SelectTrigger id="management" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any</SelectItem>
                <SelectItem value="ic">Individual contributor</SelectItem>
                <SelectItem value="tech_lead">Tech lead</SelectItem>
                <SelectItem value="manager">People manager</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Years of experience" htmlFor="years" hint="rescore">
            <Input
              id="years"
              type="number"
              min={0}
              step={0.5}
              className="tabular"
              value={prefs.years_experience ?? ""}
              onChange={(e) => setPrefs({ years_experience: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </Field>
          <Field label="Willing to relocate" htmlFor="relocate" hint="rescore">
            <div className="flex h-9 items-center">
              <Switch id="relocate" checked={prefs.willing_to_relocate} onCheckedChange={(v) => setPrefs({ willing_to_relocate: v })} />
            </div>
          </Field>
        </div>
        <Field label="Work authorization notes" htmlFor="auth-notes" help="Shown for your reference only. Not used in scoring and never sent to TypeSafe.">
          <Textarea
            id="auth-notes"
            value={prefs.work_authorization_notes ?? ""}
            onChange={(e) => setPrefs({ work_authorization_notes: e.target.value || null })}
          />
        </Field>
      </Group>

      <Group
        title="Blocker facts"
        description="Stored locally; never sent to TypeSafe. A job is blocked only when the posting states the requirement explicitly and your answer here rules you out."
      >
        {(
          [
            ["needs_visa_sponsorship", "Do you need visa sponsorship?"],
            ["can_meet_us_citizenship_requirement", "Can you meet a US citizenship requirement?"],
            ["can_meet_clearance_requirement", "Can you meet a security clearance requirement?"],
          ] as const
        ).map(([key, label]) => (
          <Field key={key} label={label} htmlFor={key} hint="rescore">
            <FactControl id={key} label={label} value={draft.blocker_facts[key]} onChange={(v) => setFacts({ [key]: v })} />
          </Field>
        ))}
      </Group>

      <Group
        title="Tracked skills"
        description="Each skill gets a requirement question for the posting and an evidence question for your resume. IDs are lowercase slugs."
      >
        <div className="grid gap-2">
          <div className="text-muted-foreground grid grid-cols-[160px_180px_1fr_32px] gap-2 text-xs">
            <span>ID</span>
            <span>Label</span>
            <span>Description</span>
          </div>
          {draft.tracked_skills.map((skill, i) => (
            <div key={i} className="grid grid-cols-[160px_180px_1fr_32px] gap-2">
              {(["id", "label", "description"] as const).map((field) => (
                <Input
                  key={field}
                  aria-label={`Skill ${i + 1} ${field}`}
                  value={skill[field] ?? ""}
                  pattern={field === "id" ? "[a-z][a-z0-9_]*" : undefined}
                  required={field !== "description"}
                  className={cnJoin("h-8", field === "id" && "font-mono text-xs")}
                  onChange={(e) =>
                    setSkills(draft.tracked_skills.map((s, j) => (j === i ? { ...s, [field]: e.target.value } : s)))
                  }
                />
              ))}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove skill ${skill.label || i + 1}`}
                onClick={() => setSkills(draft.tracked_skills.filter((_, j) => j !== i))}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={() => setSkills([...draft.tracked_skills, { id: "", label: "", description: "" }])}>
              <Plus className="size-3.5" />
              Add skill
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setSkills(meta.default_tracked_skills)}>
              <RotateCcw className="size-3.5" />
              Reset to defaults
            </Button>
          </div>
        </div>
      </Group>

      <div className="bg-background/95 fixed inset-x-0 bottom-0 z-20 border-t backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4">
          <Button type="submit" disabled={save.isPending || !!techConflict || (!dirty && !isNew)}>
            {save.isPending ? "Saving" : "Save profile"}
          </Button>
          <span className="text-muted-foreground text-xs">{dirty ? "Unsaved changes" : isNew ? "" : "All changes saved"}</span>
        </div>
      </div>
    </form>
  );
}
