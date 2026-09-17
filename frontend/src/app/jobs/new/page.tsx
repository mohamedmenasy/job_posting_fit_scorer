"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { type JobPostingIn, useEvaluatePosting, useMeta, useProfile } from "@/lib/api/hooks";
import { enumOptions } from "@/lib/format";

const MIN_DESCRIPTION = 50;

export default function NewJobPage() {
  const router = useRouter();
  const profile = useProfile();
  const meta = useMeta();
  const evaluate = useEvaluatePosting();
  const [form, setForm] = useState({ company: "", title: "", location: "", source_url: "", salary_text: "", source: "manual", description: "" });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const noProfile = profile.isSuccess && profile.data === null;
  const length = form.description.trim().length;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const body: JobPostingIn = {
      company: form.company,
      title: form.title,
      description: form.description,
      location: form.location || null,
      source_url: form.source_url || null,
      salary_text: form.salary_text || null,
      source: form.source as JobPostingIn["source"],
    };
    evaluate.mutate(body, { onSuccess: (data) => router.push(`/jobs/${data.job.id}`) });
  }

  return (
    <form onSubmit={submit} className="max-w-6xl">
      <PageHeader title="New job" description="Paste a posting. It is saved as written and evaluated against your current profile." />
      {noProfile && (
        <div className="bg-status-review/10 text-status-review mb-6 rounded px-3 py-2">
          Jobs are evaluated against your profile.{" "}
          <Link href="/profile" className="font-medium underline">
            Create your profile
          </Link>{" "}
          first.
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="grid gap-1.5">
          <Label htmlFor="description">Job description</Label>
          <Textarea
            id="description"
            autoFocus
            required
            minLength={MIN_DESCRIPTION}
            value={form.description}
            onChange={set("description")}
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
              <Input id={key} required={required} type={key === "source_url" ? "url" : "text"} maxLength={200} value={form[key]} onChange={set(key)} />
            </div>
          ))}
          <div className="grid gap-1.5">
            <Label htmlFor="source">Source</Label>
            <Select value={form.source} onValueChange={(v) => setForm((f) => ({ ...f, source: v }))}>
              <SelectTrigger id="source" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {enumOptions(meta.data, "JobSource").map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" className="mt-2" disabled={evaluate.isPending || noProfile || length < MIN_DESCRIPTION}>
            {evaluate.isPending ? "Saving" : "Save and evaluate"}
          </Button>
        </div>
      </div>
    </form>
  );
}
