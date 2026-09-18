"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { S } from "@/lib/api/client";
import { enumOptions } from "@/lib/format";

export const MIN_DESCRIPTION = 50;

export type PostingForm = {
  company: string;
  title: string;
  location: string;
  source_url: string;
  salary_text: string;
  source: string;
  description: string;
};

export const EMPTY_FORM: PostingForm = {
  company: "",
  title: "",
  location: "",
  source_url: "",
  salary_text: "",
  source: "manual",
  description: "",
};

export function toJobPosting(form: PostingForm) {
  return {
    company: form.company,
    title: form.title,
    description: form.description,
    location: form.location || null,
    source_url: form.source_url || null,
    salary_text: form.salary_text || null,
    source: form.source as S["JobPostingIn"]["source"],
  };
}

/** The fields shared by the Paste and From URL tabs. */
export function PostingFields({
  form,
  onChange,
  meta,
  descriptionLabel = "Job description",
  autoFocusDescription = false,
}: {
  form: PostingForm;
  onChange: (patch: Partial<PostingForm>) => void;
  meta: S["MetaOut"] | undefined;
  descriptionLabel?: string;
  autoFocusDescription?: boolean;
}) {
  const length = form.description.trim().length;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="grid gap-1.5">
        <Label htmlFor="description">{descriptionLabel}</Label>
        <Textarea
          id="description"
          required
          autoFocus={autoFocusDescription}
          minLength={MIN_DESCRIPTION}
          value={form.description}
          onChange={(e) => onChange({ description: e.target.value })}
          placeholder="Paste the full posting, including requirements and any work authorization text"
          className="min-h-[60vh] text-sm leading-relaxed"
        />
        <p className="text-muted-foreground tabular text-xs">
          {length < MIN_DESCRIPTION ? `${MIN_DESCRIPTION - length} more characters needed` : `${length} characters`}
        </p>
      </div>
      <div className="grid content-start gap-4">
        {(
          [
            ["company", "Company", true],
            ["title", "Title", true],
            ["location", "Location", false],
            ["salary_text", "Salary", false],
            ["source_url", "Posting URL", false],
          ] as const
        ).map(([key, label, required]) => (
          <div key={key} className="grid gap-1.5">
            <Label htmlFor={key}>
              {label}
              {!required && <span className="text-muted-foreground font-normal"> (optional)</span>}
            </Label>
            <Input
              id={key}
              required={required}
              type={key === "source_url" ? "url" : "text"}
              maxLength={key === "source_url" ? 2000 : 200}
              value={form[key]}
              onChange={(e) => onChange({ [key]: e.target.value })}
            />
          </div>
        ))}
        <div className="grid gap-1.5">
          <Label htmlFor="source">Source</Label>
          <Select value={form.source} onValueChange={(v) => onChange({ source: v })}>
            <SelectTrigger id="source" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {enumOptions(meta, "JobSource").map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

export function SubmitBar({ disabled, pending, children }: { disabled: boolean; pending: boolean; children?: React.ReactNode }) {
  return (
    <div className="mt-4 flex items-center gap-3">
      <Button type="submit" disabled={disabled}>
        {pending ? "Saving" : "Save and evaluate"}
      </Button>
      {children}
    </div>
  );
}
