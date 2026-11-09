"use client";

import { Database } from "lucide-react";
import type { DatasetMetadata } from "@croplens/shared-types";

export function WorkspaceDatasetSelect({ datasets, value, onChange, loading }: { datasets: DatasetMetadata[]; value: string; onChange: (id: string) => void; loading: boolean }) {
  if (loading) return <div className="h-10 animate-pulse rounded-lg bg-gray-100"/>;
  if (!datasets.length) return <div className="rounded-lg border border-croplens-border bg-white px-3 py-2 text-xs text-zinc-400">No datasets available</div>;
  return <label className="flex min-w-0 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3"><Database size={15} className="shrink-0 text-emerald-800"/><span className="sr-only">Select active dataset</span><select value={value} onChange={(event) => onChange(event.target.value)} className="h-10 min-w-0 flex-1 bg-transparent text-xs font-medium text-zinc-100 outline-none"><option value="" disabled>Select dataset</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></label>;
}
