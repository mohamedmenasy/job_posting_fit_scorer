"use client";

import { Globe, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, type S } from "@/lib/api/client";
import { useEvaluatePosting, useImportUrl, useMeta } from "@/lib/api/hooks";

import { EMPTY_FORM, type PostingForm, PostingFields, SubmitBar, MIN_DESCRIPTION, toJobPosting } from "./posting-form";

const SUPPORTED = "Greenhouse, Lever and Ashby job boards work best; other public pages are read as text.";

export function UrlTab({ disabled }: { disabled: boolean }) {
  const router = useRouter();
  const meta = useMeta();
  const fetchUrl = useImportUrl();
  const evaluate = useEvaluatePosting();
  const [url, setUrl] = useState("");
  const [form, setForm] = useState<PostingForm | null>(null);
  const [result, setResult] = useState<S["FetchedPostingOut"] | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);

  async function onFetch(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const data = await fetchUrl.mutateAsync(url);
      const posting = data.posting;
      setResult(posting);
      setForm({
        ...EMPTY_FORM,
        company: posting.company ?? "",
        title: posting.title ?? "",
        location: posting.location ?? "",
        salary_text: posting.salary_text ?? "",
        source_url: posting.source_url,
        source: posting.source,
        description: posting.description,
      });
    } catch (e) {
      setForm(null);
      setResult(null);
      setError({ status: e instanceof ApiError ? e.status : 0, message: e instanceof Error ? e.message : "Could not fetch that URL" });
    }
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    evaluate.mutate(toJobPosting(form), { onSuccess: (data) => router.push(`/jobs/${data.job.id}`) });
  }

  return (
    <div className="grid gap-6">
      <form onSubmit={onFetch} className="grid gap-1.5">
        <Label htmlFor="posting-url">Posting URL</Label>
        <div className="flex gap-2">
          <Input
            id="posting-url"
            type="url"
            required
            autoFocus
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://boards.greenhouse.io/acme/jobs/1234567"
            className="max-w-2xl"
          />
          <Button type="submit" variant="outline" disabled={fetchUrl.isPending || !url}>
            {fetchUrl.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Globe className="size-3.5" />}
            {fetchUrl.isPending ? "Fetching" : "Fetch"}
          </Button>
        </div>
        <p className="text-muted-foreground text-xs">{SUPPORTED}</p>
      </form>

      {error && (
        <div className="bg-status-review/10 text-status-review max-w-2xl rounded px-3 py-2 text-sm" role="alert">
          {error.message}
        </div>
      )}

      {form && result && (
        <form onSubmit={onSubmit}>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span
              className={
                result.confidence === "structured"
                  ? "bg-status-strong/10 text-status-strong rounded px-2 py-0.5 text-xs font-medium"
                  : "bg-status-review/10 text-status-review rounded px-2 py-0.5 text-xs font-medium"
              }
            >
              {result.confidence === "structured"
                ? `From the ${result.provider} job board API`
                : "Extracted from the page — check the fields"}
            </span>
            {result.warnings.map((warning) => (
              <span key={warning} className="text-muted-foreground text-xs">
                {warning}
              </span>
            ))}
          </div>
          <PostingFields form={form} meta={meta.data} onChange={(patch) => setForm({ ...form, ...patch })} />
          <SubmitBar
            pending={evaluate.isPending}
            disabled={evaluate.isPending || disabled || form.description.trim().length < MIN_DESCRIPTION || !form.company || !form.title}
          />
        </form>
      )}
    </div>
  );
}
