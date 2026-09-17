"use client";

import Link from "next/link";
import { Suspense } from "react";

import { EmptyState, PageHeader } from "@/components/common";
import { FilterBar } from "@/components/dashboard/filter-bar";
import { JobsTable } from "@/components/dashboard/jobs-table";
import { StatStrip } from "@/components/dashboard/stat-strip";
import { PAGE_SIZE, useFilters } from "@/components/dashboard/use-filters";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useJobs, useMeta, useProfile } from "@/lib/api/hooks";

export default function DashboardPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Dashboard />
    </Suspense>
  );
}

function Dashboard() {
  const { query, update, clear, active } = useFilters();
  const profile = useProfile();
  const meta = useMeta();
  const jobs = useJobs(query);
  const data = jobs.data;

  if (profile.isSuccess && profile.data === null) {
    return (
      <EmptyState
        title="Start with your profile"
        body="JobFit compares each posting with your resume and preferences, so add those first."
        action={
          <Button asChild>
            <Link href="/profile">Create profile</Link>
          </Button>
        }
      />
    );
  }
  if (jobs.isError) {
    return <p className="text-status-blocked">Could not load jobs. Check that the backend is running.</p>;
  }
  if (data && data.stats.total === 0) {
    return (
      <EmptyState
        title="No jobs yet"
        body="Paste a job posting to get a fit score, the reasons behind it, and any blockers."
        action={
          <Button asChild>
            <Link href="/jobs/new">Add job</Link>
          </Button>
        }
      />
    );
  }

  const offset = query.offset ?? 0;
  return (
    <div>
      <PageHeader
        title="Jobs"
        actions={
          <Button asChild size="sm">
            <Link href="/jobs/new" aria-keyshortcuts="n">
              New job <kbd className="ml-1 rounded border border-current/30 px-1 font-mono text-[10px] opacity-70">N</kbd>
            </Link>
          </Button>
        }
      />
      {data ? <StatStrip stats={data.stats} query={query} update={update} /> : <Skeleton className="mb-4 h-16" />}
      <FilterBar query={query} update={update} clear={clear} active={active} meta={meta.data} />
      {data && data.rows.length === 0 ? (
        <EmptyState
          title="No jobs match these filters"
          body="Try removing a filter or lowering the minimum score."
          action={
            <Button variant="outline" onClick={clear}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <JobsTable rows={data?.rows} meta={meta.data} query={query} onSort={(sort, order) => update({ sort, order })} />
      )}
      {data && data.total_filtered > PAGE_SIZE && (
        <div className="text-muted-foreground mt-3 flex items-center justify-end gap-3 text-xs">
          <span className="tabular">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total_filtered)} of {data.total_filtered}
          </span>
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => update({ offset: Math.max(0, offset - PAGE_SIZE) }, true)}>
            Previous
          </Button>
          <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= data.total_filtered} onClick={() => update({ offset: offset + PAGE_SIZE }, true)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
