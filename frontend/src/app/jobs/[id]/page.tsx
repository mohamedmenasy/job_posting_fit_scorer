"use client";

import { ExternalLink, Loader2, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConfidenceBadge, EmptyState, ScoreLedger, StatusBadge } from "@/components/common";
import { DraftEditor } from "@/components/job/draft-editor";
import {
  Blockers,
  Classification,
  FitOverview,
  History,
  Posting,
  SignalsTable,
  Skills,
  WhyApply,
  WorkAuthorization,
} from "@/components/job/sections";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteJob, useJob, useMeta, useReevaluate } from "@/lib/api/hooks";
import { cnJoin, enumLabel, score } from "@/lib/format";

const NAV = [
  ["why", "Why apply"],
  ["fit", "Fit overview"],
  ["classification", "Classification"],
  ["skills", "Skills"],
  ["blockers", "Blockers"],
  ["authorization", "Work authorization"],
  ["signals", "Signals"],
  ["posting", "Posting"],
  ["history", "History"],
] as const;

function useActiveSection(ready: boolean) {
  const [active, setActive] = useState<string>("why");
  useEffect(() => {
    if (!ready) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );
    NAV.forEach(([id]) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [ready]);
  return active;
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const job = useJob(id);
  const meta = useMeta();
  const reevaluate = useReevaluate(id);
  const remove = useDeleteJob();
  const data = job.data;
  const fit = data?.fit_result ?? null;
  const evaluation = data?.evaluation ?? null;
  const latest = data?.latest_evaluation ?? null;
  const running = latest?.status === "pending" || latest?.status === "running";
  const isDraft = data?.job.status_kind === "draft";
  const active = useActiveSection(!!evaluation);

  if (job.isPending) return <Skeleton className="h-64 max-w-5xl" />;
  if (job.isError || !data) {
    return (
      <EmptyState
        title="Job not found"
        body="It may have been deleted."
        action={
          <Button asChild variant="outline">
            <Link href="/">Back to jobs</Link>
          </Button>
        }
      />
    );
  }
  const signals = evaluation?.signals ?? null;

  return (
    <div className="grid gap-8 lg:grid-cols-[180px_minmax(0,1fr)]">
      <nav className="hidden lg:block" aria-label="Sections">
        <ul className="sticky top-20 grid gap-0.5">
          {NAV.map(([sid, label]) => (
            <li key={sid}>
              <a
                href={`#${sid}`}
                className={cnJoin(
                  "block rounded px-2 py-1 transition-colors duration-150",
                  active === sid ? "bg-brand-soft text-brand font-medium" : "text-muted-foreground hover:text-foreground",
                  !evaluation && sid !== "history" && "pointer-events-none opacity-40",
                )}
              >
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="min-w-0 max-w-5xl">
        <header className="mb-8 grid gap-4">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight">{data.job.title}</h1>
              <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="text-foreground font-medium">{data.job.company}</span>
                {data.job.location && <span>{data.job.location}</span>}
                {data.job.salary_text && <span>{data.job.salary_text}</span>}
                <span>{enumLabel(meta.data, "JobSource", data.job.source)}</span>
                {data.job.source_url && (
                  <a href={data.job.source_url} target="_blank" rel="noreferrer" className="text-brand inline-flex items-center gap-1 hover:underline">
                    Original posting <ExternalLink className="size-3" />
                  </a>
                )}
              </div>
            </div>
            {fit && (
              <div className="flex items-center gap-5">
                <div className="text-right">
                  <div className="tabular text-5xl leading-none font-semibold tracking-tight">{score(fit.overall_score)}</div>
                  <div className="text-muted-foreground mt-1 text-xs">fit score of 100</div>
                </div>
                <div className="grid gap-1.5">
                  <StatusBadge status={fit.status} />
                  <span className="text-muted-foreground inline-flex items-baseline gap-1.5 text-xs">
                    Confidence <ConfidenceBadge value={fit.aggregate_confidence} />
                  </span>
                </div>
              </div>
            )}
          </div>

          {fit && <ScoreLedger fit={fit} />}

          <div className="flex flex-wrap items-center gap-2">
            {isDraft && (
              <span className="text-muted-foreground bg-muted rounded px-2 py-0.5 text-xs font-medium">Draft</span>
            )}
            {fit?.needs_review && (
              <span className="text-status-review bg-status-review/10 rounded px-2 py-0.5 text-xs font-medium">Review recommended</span>
            )}
            {fit?.stale_semantics && (
              <span className="text-status-review bg-status-review/10 rounded px-2 py-0.5 text-xs font-medium">
                Profile changed since evaluation
              </span>
            )}
            <div className="ml-auto flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={running || reevaluate.isPending || isDraft}
                title={isDraft ? "Add a job description before evaluating" : undefined}
                onClick={() => reevaluate.mutate()}
              >
                <RefreshCw className="size-3.5" />
                {fit ? "Re-evaluate" : "Evaluate"}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <Trash2 className="size-3.5" />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this job?</AlertDialogTitle>
                    <AlertDialogDescription>
                      The posting, all its evaluations, and all fit results will be permanently deleted.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep job</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => remove.mutate(id, { onSuccess: () => router.push("/") })}
                      className="bg-destructive text-white hover:bg-destructive/90"
                    >
                      Delete job
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>

          {running && (
            <div className="bg-muted flex items-center gap-2 rounded px-3 py-2" role="status">
              <Loader2 className="size-4 animate-spin" />
              {latest?.status === "pending" ? "Queued for evaluation" : "Evaluating with TypeSafe"}
              {fit && <span className="text-muted-foreground">. Showing the previous result until it finishes.</span>}
            </div>
          )}
          {latest?.status === "failed" && (
            <div className="bg-status-blocked/10 text-status-blocked flex flex-wrap items-center gap-3 rounded px-3 py-2" role="alert">
              <span>Evaluation failed: {latest.error ?? "unknown error"}</span>
              <Button size="sm" variant="outline" className="ml-auto" onClick={() => reevaluate.mutate()}>
                Retry
              </Button>
            </div>
          )}
        </header>

        {fit && signals && evaluation ? (
          <>
            <WhyApply fit={fit} />
            <FitOverview fit={fit} />
            <Classification signals={signals} meta={meta.data} />
            <Skills fit={fit} signals={signals} />
            <Blockers fit={fit} />
            <WorkAuthorization signals={signals} meta={meta.data} />
            <SignalsTable evaluation={evaluation} />
            <Posting signals={signals} fit={fit} />
          </>
        ) : isDraft ? (
          <DraftEditor job={data.job} />
        ) : (
          !running && latest?.status !== "failed" && (
            <p className="text-muted-foreground">This job has not been evaluated yet.</p>
          )
        )}
        <History jobId={id} />
      </div>
    </div>
  );
}
