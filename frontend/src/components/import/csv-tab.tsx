"use client";

import { FileUp, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { S } from "@/lib/api/client";
import { type CsvMapping, useCsvCommit, useCsvPreview } from "@/lib/api/hooks";

import { MappingTable, missingRequired } from "./mapping-table";

export function CsvTab() {
  const preview = useCsvPreview();
  const commit = useCsvCommit();
  const fileRef = useRef<HTMLInputElement>(null);
  const [parsed, setParsed] = useState<S["CsvPreviewOut"] | null>(null);
  const [mapping, setMapping] = useState<CsvMapping>({});
  const [result, setResult] = useState<S["CsvCommitOut"] | null>(null);
  const [fileName, setFileName] = useState("");

  async function onFile(file: File | undefined) {
    if (!file) return;
    setResult(null);
    setFileName(file.name);
    const data = await preview.mutateAsync(file).catch(() => null);
    if (data) {
      setParsed(data);
      setMapping(data.suggested_mapping);
    } else {
      setParsed(null);
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  const missing = parsed ? missingRequired(mapping) : [];

  return (
    <div className="grid max-w-5xl gap-6">
      <div className="grid gap-1.5">
        <Label htmlFor="csv-file">Spreadsheet</Label>
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            id="csv-file"
            type="file"
            accept=".csv,.tsv,text/csv,text/tab-separated-values"
            className="sr-only"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          <Button type="button" variant="outline" disabled={preview.isPending} onClick={() => fileRef.current?.click()}>
            {preview.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <FileUp className="size-3.5" />}
            {preview.isPending ? "Reading" : "Choose a CSV file"}
          </Button>
          <span className="text-muted-foreground text-xs">
            {fileName || "Up to 500 rows. Any column names — you confirm what they mean next."}
          </span>
        </div>
      </div>

      {parsed && (
        <>
          <div>
            <h2 className="mb-1 font-semibold">Check the columns</h2>
            <p className="text-muted-foreground mb-3 text-xs">
              {parsed.row_count} rows, separated by “{parsed.delimiter === "\t" ? "tab" : parsed.delimiter}”. Rows without a
              description are saved as drafts you can finish later.
            </p>
            <MappingTable columns={parsed.columns} mapping={mapping} preview={parsed.preview} onChange={setMapping} />
          </div>
          <div className="flex items-center gap-3">
            <Button
              type="button"
              disabled={commit.isPending || missing.length > 0}
              onClick={() =>
                commit.mutate({ mapping, rows: parsed.rows }, { onSuccess: setResult })
              }
            >
              {commit.isPending ? "Importing" : `Import ${parsed.row_count} rows`}
            </Button>
            {missing.length > 0 && (
              <span className="text-status-review text-xs">Map a column to {missing.join(" and ")} first</span>
            )}
            <span className="text-muted-foreground text-xs">Importing does not evaluate anything.</span>
          </div>
        </>
      )}

      {result && (
        <div className="grid gap-3 border-t pt-4" role="status">
          <h2 className="font-semibold">Imported</h2>
          <dl className="flex flex-wrap gap-6">
            {[
              ["Jobs added", result.created],
              ["Drafts", result.drafts],
              ["Already in JobFit", result.duplicates],
              ["Rows skipped", result.errors.length],
            ].map(([label, value]) => (
              <div key={label as string}>
                <dd className="tabular text-2xl font-semibold">{value as number}</dd>
                <dt className="text-muted-foreground text-xs">{label as string}</dt>
              </div>
            ))}
          </dl>
          {result.errors.length > 0 && (
            <ul className="text-muted-foreground grid gap-1 text-xs">
              {result.errors.slice(0, 10).map((error) => (
                <li key={error.row}>
                  Row {error.row}: {error.reason}
                </li>
              ))}
              {result.errors.length > 10 && <li>and {result.errors.length - 10} more</li>}
            </ul>
          )}
          <div className="flex gap-2">
            <Button asChild size="sm">
              <Link href="/">Review imported jobs</Link>
            </Button>
            {result.drafts > 0 && (
              <Button asChild size="sm" variant="outline">
                <Link href="/?state=draft">Finish {result.drafts} drafts</Link>
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
