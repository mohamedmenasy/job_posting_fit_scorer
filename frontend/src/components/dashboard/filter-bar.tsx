"use client";

import { Search, X } from "lucide-react";
import { useRef, useState } from "react";

import { MultiSelect } from "@/components/multi-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { S } from "@/lib/api/client";
import type { JobsQuery } from "@/lib/api/hooks";
import { enumOptions } from "@/lib/format";

import type { MultiKey } from "./use-filters";

type Update = (patch: Record<string, string | string[] | number | boolean | null>) => void;

const MULTI: [MultiKey, string, string][] = [
  ["status", "FitStatus", "Status"],
  ["role_family", "RoleFamily", "Platform"],
  ["seniority", "Seniority", "Level"],
  ["domain", "Domain", "Domain"],
  ["work_arrangement", "WorkArrangement", "Work type"],
  ["kmp_requirement", "RequirementLevel", "KMP"],
  ["work_authorization_signal", "WorkAuthSignal", "Sponsorship"],
  ["source", "JobSource", "Source"],
];

export function FilterBar({ query, update, clear, active, meta }: { query: JobsQuery; update: Update; clear: () => void; active: boolean; meta: S["MetaOut"] | undefined }) {
  const [search, setSearch] = useState(query.q ?? "");
  const [company, setCompany] = useState(query.company ?? "");
  const timer = useRef<number | undefined>(undefined);
  const debounced = (key: "q" | "company", value: string) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => update({ [key]: value || null }), 250);
  };

  return (
    <div className="mb-4 grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
          <Input
            id="job-search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              debounced("q", e.target.value);
            }}
            placeholder="Search company, title, location"
            className="h-8 pl-8 text-xs md:text-xs"
            aria-keyshortcuts="/"
          />
          <kbd className="text-muted-foreground absolute top-1/2 right-2 -translate-y-1/2 rounded border px-1 font-mono text-[10px]">/</kbd>
        </div>
        <Input value={company} onChange={(e) => {
            setCompany(e.target.value);
            debounced("company", e.target.value);
          }} placeholder="Exact company" className="h-8 w-40 text-xs md:text-xs" aria-label="Company" />
        <Input
          type="number"
          min={0}
          max={100}
          defaultValue={query.min_score ?? ""}
          onBlur={(e) => update({ min_score: e.target.value || null })}
          onKeyDown={(e) => e.key === "Enter" && update({ min_score: e.currentTarget.value || null })}
          placeholder="Min score"
          className="tabular h-8 w-28 text-xs md:text-xs"
          aria-label="Minimum score"
        />
        <Select value={query.min_android_relevance?.toString() ?? "any"} onValueChange={(v) => update({ min_android_relevance: v === "any" ? null : v })}>
          <SelectTrigger size="sm" className="w-52 text-xs" aria-label="Minimum Android relevance">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any Android relevance</SelectItem>
            {[1, 2, 3, 4].map((n) => (
              <SelectItem key={n} value={String(n)}>
                Android relevance ≥ {n}/4
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={query.clearance ?? "any"} onValueChange={(v) => update({ clearance: v === "any" ? null : v })}>
          <SelectTrigger size="sm" className="w-44 text-xs" aria-label="Security clearance">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any clearance</SelectItem>
            <SelectItem value="required">Clearance required</SelectItem>
            <SelectItem value="possible">Clearance possible</SelectItem>
            <SelectItem value="not_required">No clearance</SelectItem>
          </SelectContent>
        </Select>
        <label className="text-muted-foreground flex items-center gap-2 px-1 text-xs">
          <Switch checked={!!query.needs_review} onCheckedChange={(v) => update({ needs_review: v || null })} />
          Review recommended
        </label>
        {active && (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => {
              setSearch("");
              setCompany("");
              clear();
            }}
          >
            <X className="size-3.5" />
            Clear filters
          </Button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
        {MULTI.map(([key, enumName, label]) => (
          <MultiSelect
            key={key}
            options={enumOptions(meta, enumName)}
            value={query[key] ?? []}
            onChange={(v) => update({ [key]: v })}
            placeholder={label}
            className="h-8 text-xs"
          />
        ))}
      </div>
    </div>
  );
}
