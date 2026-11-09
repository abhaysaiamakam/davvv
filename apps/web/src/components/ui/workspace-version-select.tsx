"use client";

import { Layers3 } from "lucide-react";
import type { DatasetVersion } from "@croplens/shared-types";

export function WorkspaceVersionSelect({versions,value,onChange,loading}:{versions:DatasetVersion[];value:string;onChange:(id:string)=>void;loading:boolean}){
 if(loading)return <div className="h-10 animate-pulse rounded-lg bg-gray-100"/>;
 if(!versions.length)return <div className="flex h-10 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs text-zinc-400"><Layers3 size={14}/>No versions</div>;
 return <label className="flex min-w-0 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3"><Layers3 size={14} className="shrink-0 text-emerald-800"/><span className="sr-only">Select dataset version</span><select value={value} onChange={event=>onChange(event.target.value)} className="h-10 min-w-0 flex-1 bg-transparent text-xs font-medium text-zinc-100 outline-none">{versions.map(version=><option key={version.version_id} value={version.version_id}>v{version.version_number} · {version.status}</option>)}</select></label>
}
