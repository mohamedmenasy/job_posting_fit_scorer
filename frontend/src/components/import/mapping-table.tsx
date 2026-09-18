"use client";

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CsvMapping } from "@/lib/api/hooks";
import { cnJoin } from "@/lib/format";

const NONE = "__none__";

export const FIELDS: { value: string; label: string; required?: boolean }[] = [
  { value: "company", label: "Company", required: true },
  { value: "title", label: "Title", required: true },
  { value: "description", label: "Description" },
  { value: "location", label: "Location" },
  { value: "source_url", label: "Posting URL" },
  { value: "salary_text", label: "Salary" },
  { value: "external_id", label: "External ID" },
];

export function missingRequired(mapping: CsvMapping): string[] {
  const used = new Set(Object.values(mapping).filter(Boolean));
  return FIELDS.filter((f) => f.required && !used.has(f.value)).map((f) => f.label);
}

export function MappingTable({
  columns,
  mapping,
  preview,
  onChange,
}: {
  columns: string[];
  mapping: CsvMapping;
  preview: Record<string, string>[];
  onChange: (mapping: CsvMapping) => void;
}) {
  const duplicates = Object.values(mapping).filter((v): v is string => !!v);
  const isDuplicate = (field: string | null) => !!field && duplicates.filter((v) => v === field).length > 1;

  return (
    <div className="grid gap-2">
      <div className="text-muted-foreground grid grid-cols-[220px_200px_minmax(0,1fr)] gap-3 text-xs">
        <span>CSV column</span>
        <span>Imports as</span>
        <span>First values</span>
      </div>
      {columns.map((column) => (
        <div key={column} className="grid grid-cols-[220px_200px_minmax(0,1fr)] items-center gap-3">
          <Label htmlFor={`map-${column}`} className="truncate font-mono text-xs">
            {column}
          </Label>
          <Select
            value={mapping[column] ?? NONE}
            onValueChange={(v) => onChange({ ...mapping, [column]: v === NONE ? null : v })}
          >
            <SelectTrigger
              id={`map-${column}`}
              size="sm"
              className={cnJoin("w-full text-xs", isDuplicate(mapping[column] ?? null) && "border-status-blocked")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Skip this column</SelectItem>
              {FIELDS.map((field) => (
                <SelectItem key={field.value} value={field.value}>
                  {field.label}
                  {field.required ? " (required)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-muted-foreground truncate text-xs">
            {preview.map((row) => row[column]).filter(Boolean).slice(0, 2).join(" · ") || "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
