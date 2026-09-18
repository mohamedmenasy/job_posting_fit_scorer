"use client";

import { useState } from "react";

import { MIN_DESCRIPTION } from "@/components/import/posting-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { S } from "@/lib/api/client";
import { usePatchJob } from "@/lib/api/hooks";

/** A draft is editable until its first successful evaluation; after that the posting is frozen. */
export function DraftEditor({ job }: { job: S["JobOut"] }) {
  const patch = usePatchJob(job.id);
  const [draft, setDraft] = useState({
    company: job.company,
    title: job.title,
    location: job.location ?? "",
    description: job.description,
  });
  const short = draft.description.trim().length < MIN_DESCRIPTION;

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        patch.mutate({ ...draft, location: draft.location || null });
      }}
    >
      <p className="text-muted-foreground">
        This job was imported without a full description, so it has not been evaluated. Paste the posting text to finish it.
      </p>
      <div className="grid gap-4 sm:grid-cols-3">
        {(
          [
            ["company", "Company"],
            ["title", "Title"],
            ["location", "Location"],
          ] as const
        ).map(([key, label]) => (
          <div key={key} className="grid gap-1.5">
            <Label htmlFor={`draft-${key}`}>{label}</Label>
            <Input
              id={`draft-${key}`}
              value={draft[key]}
              required={key !== "location"}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          </div>
        ))}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="draft-description">Job description</Label>
        <Textarea
          id="draft-description"
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          className="min-h-80 text-sm leading-relaxed"
          placeholder="Paste the full posting here"
        />
        <p className="text-muted-foreground tabular text-xs">
          {short
            ? `${MIN_DESCRIPTION - draft.description.trim().length} more characters needed before this job can be evaluated`
            : `${draft.description.trim().length} characters`}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={patch.isPending}>
          {patch.isPending ? "Saving" : short ? "Save draft" : "Save and unlock evaluation"}
        </Button>
        {job.source_url && (
          <a href={job.source_url} target="_blank" rel="noreferrer" className="text-brand text-xs hover:underline">
            Open the original posting
          </a>
        )}
      </div>
    </form>
  );
}
