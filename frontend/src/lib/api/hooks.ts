"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError, type S, api, errorMessage, unwrap } from "./client";
import type { paths } from "./schema";

export type JobsQuery = NonNullable<paths["/api/jobs"]["get"]["parameters"]["query"]>;
export type ProfileIn = S["CandidateProfileIn"];
export type JobPostingIn = S["JobPostingIn"];

const ACTIVE = new Set(["pending", "running"]);

function onError(error: unknown) {
  toast.error(errorMessage(error));
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => unwrap(api.GET("/api/meta")), staleTime: Infinity });
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => unwrap(api.GET("/api/health")), refetchInterval: 15_000 });
}

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/profile"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
}

export function useReevaluateMany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobIds?: string[]) => unwrap(api.POST("/api/jobs/reevaluate", { body: { job_ids: jobIds ?? null } })),
    onSuccess: (data) => {
      toast.success(`Re-evaluating ${data.evaluation_ids.length} jobs`);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job"] });
    },
    onError,
  });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  const reevaluate = useReevaluateMany();
  return useMutation({
    mutationFn: (body: ProfileIn) => unwrap(api.PUT("/api/profile", { body })),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job"] });
      if (data.change_kind === "none") {
        toast("No changes to save");
        return;
      }
      const rescored = `Profile saved. Re-scored ${data.rescored} ${data.rescored === 1 ? "job" : "jobs"}.`;
      if (data.change_kind === "semantic" && data.affected_jobs > 0) {
        toast.success(rescored, {
          description: `${data.affected_jobs} evaluations use your old resume or role preferences.`,
          action: { label: `Re-evaluate ${data.affected_jobs} jobs`, onClick: () => reevaluate.mutate(undefined) },
          duration: 15_000,
        });
      } else {
        toast.success(rescored);
      }
    },
    onError,
  });
}

export function useExtractResume() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/profile/resume/extract", { method: "POST", body: form });
      const body = await response.json().catch(() => undefined);
      if (!response.ok) throw new ApiError(response.status, errorMessage(body, response.statusText));
      return body as S["ResumeTextOut"];
    },
    onError,
  });
}

export function useJobs(query: JobsQuery) {
  return useQuery({
    queryKey: ["jobs", query],
    queryFn: () => unwrap(api.GET("/api/jobs", { params: { query } })),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.rows.some((r) => ACTIVE.has(r.evaluation_status ?? "")) ? 2_000 : false),
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })),
    refetchInterval: (q) => (ACTIVE.has(q.state.data?.latest_evaluation?.status ?? "") ? 1_000 : false),
  });
}

export function useEvaluations(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ["job", jobId, "evaluations"],
    queryFn: () => unwrap(api.GET("/api/evaluations", { params: { query: { job_id: jobId } } })),
    enabled,
  });
}

export function useEvaluationDetail(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => unwrap(api.GET("/api/evaluations/{evaluation_id}", { params: { path: { evaluation_id: id! } } })),
    enabled: enabled && !!id,
  });
}

export function useEvaluatePosting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JobPostingIn) => unwrap(api.POST("/api/evaluate", { body })),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      if (data.reused) toast("This posting was already evaluated with your current profile — showing that result");
    },
    onError,
  });
}

export function useReevaluate(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/jobs/{job_id}/evaluate", { params: { path: { job_id: jobId } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError,
  });
}

export function useDeleteJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => unwrap(api.DELETE("/api/jobs/{job_id}", { params: { path: { job_id: jobId } } })),
    onSuccess: () => {
      toast.success("Job deleted");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError,
  });
}

export type CsvMapping = Record<string, string | null>;
export type CsvRow = Record<string, string>;

export function useImportUrl() {
  return useMutation({
    mutationFn: (url: string) => unwrap(api.POST("/api/import/url", { body: { url } })),
  });
}

export function useCsvPreview() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/import/csv", { method: "POST", body: form });
      const data = await response.json().catch(() => undefined);
      if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.statusText));
      return data as S["CsvPreviewOut"];
    },
    onError,
  });
}

export function useCsvCommit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ mapping, rows }: { mapping: CsvMapping; rows: CsvRow[] }) =>
      unwrap(api.POST("/api/import/csv/commit", { body: { mapping, rows } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
    onError,
  });
}

export function usePatchJob(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["JobPatch"]) =>
      unwrap(api.PATCH("/api/jobs/{job_id}", { params: { path: { job_id: jobId } }, body })),
    onSuccess: () => {
      toast.success("Job saved");
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError,
  });
}

export function useScoringSettings() {
  return useQuery({ queryKey: ["scoring"], queryFn: () => unwrap(api.GET("/api/settings/scoring")) });
}

export function useSaveScoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["ScoringConfig"]) => unwrap(api.PUT("/api/settings/scoring", { body })),
    onSuccess: (data) => {
      toast.success(`Saved scoring version ${data.version}. Re-scored ${data.rescored} jobs without API calls.`);
      qc.invalidateQueries({ queryKey: ["scoring"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job"] });
    },
    onError,
  });
}
