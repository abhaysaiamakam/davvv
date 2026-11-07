"use client";

import React from "react";
import { Database, ChevronDown } from "lucide-react";
import { DatasetMetadata } from "@croplens/shared-types";
import { cn } from "@/lib/utils";

interface DatasetSelectorProps {
  datasets: DatasetMetadata[];
  selectedId: string;
  onSelect: (id: string) => void;
  className?: string;
  disabled?: boolean;
}

export function DatasetSelector({
  datasets,
  selectedId,
  onSelect,
  className,
  disabled = false,
}: DatasetSelectorProps) {
  const selected = datasets.find((d) => d.id === selectedId) || datasets[0];

  return (
    <div className={cn("relative inline-block w-full max-w-xs", className)}>
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-400">
          <Database className="h-4 w-4" />
        </div>
        <select
          value={selectedId}
          disabled={disabled}
          onChange={(e) => onSelect(e.target.value)}
          className="w-full appearance-none rounded-lg border border-croplens-border bg-croplens-sidebar py-2 pl-9 pr-9 text-xs font-medium text-zinc-100 shadow-sm transition-colors hover:border-emerald-700/60 focus:border-emerald-500 focus:outline-none disabled:opacity-50"
        >
          {datasets.map((dataset) => (
            <option
              key={dataset.id}
              value={dataset.id}
              className="bg-zinc-900 text-zinc-100 py-1"
            >
              {dataset.name} {dataset.id === "icar-rice-maize" ? "★ [Primary]" : ""}
            </option>
          ))}
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400">
          <ChevronDown className="h-3.5 w-3.5" />
        </div>
      </div>
      {selected && (
        <div className="mt-1 flex items-center justify-between text-[11px] text-zinc-400 px-1">
          <span>{selected.crops.join(", ")}</span>
          <span className="font-mono text-[10px] text-emerald-400/90">
            {selected.status.toUpperCase()}
          </span>
        </div>
      )}
    </div>
  );
}

