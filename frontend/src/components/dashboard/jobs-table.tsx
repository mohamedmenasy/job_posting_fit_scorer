"use client";

import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useRouter } from "next/navigation";

import { ConfidenceBadge, EvaluationState, StatusBadge } from "@/components/common";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { S } from "@/lib/api/client";
import type { JobsQuery } from "@/lib/api/hooks";
import { cnJoin, enumLabel, score } from "@/lib/format";

import type { SortKey } from "./use-filters";

type Row = S["JobRowOut"];
type Meta = S["MetaOut"] | undefined;

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Row>();

/** Columns the API can sort by (server-side sorting). */
const SORTABLE: Record<string, SortKey> = { score: "score", company: "company", confidence: "confidence" };

function buildColumns(meta: Meta) {
  return helper.columns([
    helper.accessor("overall_score", {
      id: "score",
      header: "Score",
      cell: ({ row }) => {
        const r = row.original;
        if (r.overall_score == null) return <EvaluationState status={r.evaluation_status} error={r.evaluation_error} />;
        return (
          <div className="flex items-center gap-2">
            <span className="tabular w-7 text-right font-semibold">{score(r.overall_score)}</span>
            <div className="bg-muted h-1.5 w-14 overflow-hidden rounded-sm">
              <div className="bg-brand h-full" style={{ width: `${r.overall_score}%` }} />
            </div>
          </div>
        );
      },
    }),
    helper.accessor("company", { header: "Company", cell: (info) => <span className="font-medium">{info.getValue()}</span> }),
    helper.accessor("title", { header: "Role", cell: (info) => <span className="block max-w-72 truncate">{info.getValue()}</span> }),
    helper.accessor("seniority", { header: "Level", cell: (info) => enumLabel(meta, "Seniority", info.getValue()) }),
    helper.accessor("role_family", { header: "Platform", cell: (info) => enumLabel(meta, "RoleFamily", info.getValue()) }),
    helper.accessor("location", { header: "Location", cell: (info) => <span className="text-muted-foreground block max-w-48 truncate">{info.getValue() ?? "—"}</span> }),
    helper.accessor("work_arrangement", { header: "Work type", cell: (info) => enumLabel(meta, "WorkArrangement", info.getValue()) }),
    helper.accessor("domain", { header: "Domain", cell: (info) => enumLabel(meta, "Domain", info.getValue()) }),
    helper.accessor("aggregate_confidence", { id: "confidence", header: "Confidence", cell: (info) => <ConfidenceBadge value={info.getValue()} /> }),
    helper.accessor("status", {
      header: "Status",
      cell: ({ row }) => {
        const r = row.original;
        const busy = r.evaluation_status === "pending" || r.evaluation_status === "running" || r.evaluation_status === "failed";
        return (
          <div className="flex items-center gap-2">
            {r.status && <StatusBadge status={r.status} />}
            {busy && r.overall_score != null && <EvaluationState status={r.evaluation_status} error={r.evaluation_error} />}
          </div>
        );
      },
    }),
  ]);
}

const EMPTY: Row[] = [];

export function JobsTable({ rows, meta, query, onSort }: { rows: Row[] | undefined; meta: Meta; query: JobsQuery; onSort: (sort: SortKey, order: "asc" | "desc") => void }) {
  const router = useRouter();
  const table = useTable({ features, columns: buildColumns(meta), data: rows ?? EMPTY });

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id}>
            {group.headers.map((header) => {
              const sortKey = SORTABLE[header.column.id];
              const sorted = sortKey && query.sort === sortKey;
              return (
                <TableHead key={header.id} aria-sort={sorted ? (query.order === "asc" ? "ascending" : "descending") : undefined}>
                  {sortKey ? (
                    <button
                      type="button"
                      className={cnJoin("hover:text-foreground inline-flex items-center gap-1", sorted && "text-foreground")}
                      onClick={() => onSort(sortKey, sorted && query.order === "desc" ? "asc" : sorted ? "desc" : sortKey === "company" ? "asc" : "desc")}
                    >
                      <table.FlexRender header={header} />
                      {sorted && (query.order === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                    </button>
                  ) : (
                    <table.FlexRender header={header} />
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow
            key={row.id}
            tabIndex={0}
            className="cursor-pointer"
            onClick={() => router.push(`/jobs/${row.original.id}`)}
            onKeyDown={(e) => e.key === "Enter" && router.push(`/jobs/${row.original.id}`)}
          >
            {row.getAllCells().map((cell) => (
              <TableCell key={cell.id} className="py-2">
                <table.FlexRender cell={cell} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
