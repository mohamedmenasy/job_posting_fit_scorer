"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/common";
import { CsvTab } from "@/components/import/csv-tab";
import {
  EMPTY_FORM,
  MIN_DESCRIPTION,
  type PostingForm,
  PostingFields,
  SubmitBar,
  toJobPosting,
} from "@/components/import/posting-form";
import { UrlTab } from "@/components/import/url-tab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEvaluatePosting, useMeta, useProfile } from "@/lib/api/hooks";

export default function NewJobPage() {
  const router = useRouter();
  const profile = useProfile();
  const meta = useMeta();
  const evaluate = useEvaluatePosting();
  const [form, setForm] = useState<PostingForm>(EMPTY_FORM);
  const noProfile = profile.isSuccess && profile.data === null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    evaluate.mutate(toJobPosting(form), { onSuccess: (data) => router.push(`/jobs/${data.job.id}`) });
  }

  return (
    <div className="max-w-6xl">
      <PageHeader title="New job" description="Paste a posting, fetch one from a public job board, or import a spreadsheet." />
      {noProfile && (
        <div className="bg-status-review/10 text-status-review mb-6 rounded px-3 py-2">
          Jobs are evaluated against your profile.{" "}
          <Link href="/profile" className="font-medium underline">
            Create your profile
          </Link>{" "}
          first.
        </div>
      )}
      <Tabs defaultValue="paste">
        <TabsList className="mb-6">
          <TabsTrigger value="paste">Paste</TabsTrigger>
          <TabsTrigger value="url">From URL</TabsTrigger>
          <TabsTrigger value="csv">From CSV</TabsTrigger>
        </TabsList>
        <TabsContent value="paste">
          <form onSubmit={submit}>
            <PostingFields form={form} meta={meta.data} autoFocusDescription onChange={(patch) => setForm({ ...form, ...patch })} />
            <SubmitBar
              pending={evaluate.isPending}
              disabled={evaluate.isPending || noProfile || form.description.trim().length < MIN_DESCRIPTION || !form.company || !form.title}
            />
          </form>
        </TabsContent>
        <TabsContent value="url">
          <UrlTab disabled={noProfile} />
        </TabsContent>
        <TabsContent value="csv">
          <CsvTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
