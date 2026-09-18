"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import type { JobsQuery } from "@/lib/api/hooks";

export const PAGE_SIZE = 100;
export const MULTI_KEYS = [
  "status", "role_family", "seniority", "domain", "work_arrangement", "kmp_requirement", "work_authorization_signal", "source",
] as const;
export type MultiKey = (typeof MULTI_KEYS)[number];
export type SortKey = NonNullable<JobsQuery["sort"]>;

/** Dashboard filters live in the URL so views can be bookmarked, shared, and survive reloads. */
export function useFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const query = useMemo<JobsQuery>(() => {
    const num = (key: string) => (params.get(key) ? Number(params.get(key)) : undefined);
    const q: JobsQuery = {
      q: params.get("q") || undefined,
      company: params.get("company") || undefined,
      min_score: num("min_score"),
      min_android_relevance: num("min_android_relevance"),
      clearance: (params.get("clearance") as JobsQuery["clearance"]) || undefined,
      needs_review: params.get("needs_review") === "true" ? true : undefined,
      state: params.getAll("state").length ? params.getAll("state") : undefined,
      sort: (params.get("sort") as SortKey) || "score",
      order: (params.get("order") as JobsQuery["order"]) || "desc",
      limit: PAGE_SIZE,
      offset: num("offset") ?? 0,
    };
    for (const key of MULTI_KEYS) {
      const values = params.getAll(key);
      if (values.length) q[key] = values;
    }
    return q;
  }, [params]);

  const update = useCallback(
    (patch: Record<string, string | string[] | number | boolean | null | undefined>, keepOffset = false) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(patch)) {
        next.delete(key);
        if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
        else if (value !== null && value !== undefined && value !== "" && value !== false) next.set(key, String(value));
      }
      if (!keepOffset) next.delete("offset");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const clear = useCallback(() => router.replace(pathname, { scroll: false }), [pathname, router]);
  const active = [...params.keys()].some((k) => !["sort", "order", "offset"].includes(k));
  return { query, update, clear, active };
}
