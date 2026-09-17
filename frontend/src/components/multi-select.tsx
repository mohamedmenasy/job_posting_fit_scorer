"use client";

import { Check, ChevronsUpDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cnJoin } from "@/lib/format";

export type Option = { value: string; label: string };

export function MultiSelect<T extends string>({
  id,
  options,
  value,
  onChange,
  placeholder = "Any",
  disabledValues = [],
  className,
}: {
  id?: string;
  options: Option[];
  value: T[];
  onChange: (next: T[]) => void;
  placeholder?: string;
  disabledValues?: string[];
  className?: string;
}) {
  const labels = options.filter((o) => value.includes(o.value as T)).map((o) => o.label);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button id={id} variant="outline" className={cnJoin("w-full justify-between font-normal", className)}>
          <span className={cnJoin("truncate", !labels.length && "text-muted-foreground")}>
            {labels.length ? labels.join(", ") : placeholder}
          </span>
          <ChevronsUpDown className="text-muted-foreground size-3.5 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <Command>
          {options.length > 8 && <CommandInput placeholder="Filter" />}
          <CommandList>
            <CommandEmpty>No options</CommandEmpty>
            {options.map((o) => {
              const selected = value.includes(o.value as T);
              const disabled = !selected && disabledValues.includes(o.value);
              return (
                <CommandItem
                  key={o.value}
                  value={o.label}
                  disabled={disabled}
                  onSelect={() =>
                    onChange(selected ? value.filter((v) => v !== o.value) : [...value, o.value as T])
                  }
                >
                  <Check className={cnJoin("size-3.5", selected ? "opacity-100" : "opacity-0")} />
                  {o.label}
                  {disabled && <span className="text-muted-foreground ml-auto text-xs">in other list</span>}
                </CommandItem>
              );
            })}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
