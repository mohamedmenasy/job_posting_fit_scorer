"use client";

import { X } from "lucide-react";
import { useState } from "react";

export function TagInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  function commit(text: string) {
    const items = text.split(",").map((t) => t.trim()).filter(Boolean);
    const next = [...value];
    for (const item of items) {
      if (!next.some((v) => v.toLowerCase() === item.toLowerCase())) next.push(item);
    }
    if (next.length !== value.length) onChange(next);
    setDraft("");
  }

  return (
    <div className="border-input focus-within:ring-ring/50 focus-within:border-ring flex min-h-9 flex-wrap items-center gap-1 rounded-md border px-2 py-1 focus-within:ring-[3px]">
      {value.map((tag) => (
        <span key={tag} className="bg-muted inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs">
          {tag}
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            aria-label={`Remove ${tag}`}
            onClick={() => onChange(value.filter((v) => v !== tag))}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        placeholder={value.length ? undefined : placeholder}
        className="min-w-24 flex-1 bg-transparent py-0.5 outline-none"
        onChange={(e) => (e.target.value.includes(",") ? commit(e.target.value) : setDraft(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => draft && commit(draft)}
      />
    </div>
  );
}
