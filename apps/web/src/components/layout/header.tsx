"use client";

import { usePathname } from "next/navigation";
import { BookOpen, ScanSearch, RefreshCw } from "lucide-react";
import { useApiHealth } from "@/hooks/use-api-health";
import { useEffect, useState } from "react";

const routeNames: Record<string, string> = { "/": "Dashboard", "/datasets": "Datasets", "/quality": "Data Quality", "/eda": "EDA Studio", "/insights": "Insights", "/comparison": "Dataset Comparison", "/reports": "Reports", "/analyze": "Dataset Upload", "/preprocessing": "Preprocessing", "/features": "Feature Engineering", "/readiness": "Readiness", "/jobs": "Job Center", "/phase1": "Phase 1 Dataset Submission" };
export function Header() {
  const pathname = usePathname();
  const { status, data, refresh } = useApiHealth();
  const [explain, setExplain] = useState(false);
  const [datasetContext,setDatasetContext]=useState<{id:string;name:string;versionId:string}>({id:"",name:"",versionId:""});
  useEffect(() => { setExplain(localStorage.getItem("croplens-codelens") === "on"); }, []);
  useEffect(()=>{
    const id=localStorage.getItem("croplens-dataset")??"";
    setDatasetContext({id,name:id,versionId:id?localStorage.getItem(`croplens-version:${id}`)??"":""});
    const onDataset=(event:Event)=>{const detail=(event as CustomEvent<{id:string;name:string;currentVersionId?:string}>).detail;if(detail?.id)setDatasetContext({id:detail.id,name:detail.name||detail.id,versionId:detail.currentVersionId??""})};
    const onVersion=(event:Event)=>{const detail=(event as CustomEvent<{datasetId:string;versionId:string}>).detail;if(detail?.datasetId===localStorage.getItem("croplens-dataset"))setDatasetContext(current=>({...current,versionId:detail.versionId}))};
    window.addEventListener("croplens:dataset",onDataset);window.addEventListener("croplens:version",onVersion);
    return()=>{window.removeEventListener("croplens:dataset",onDataset);window.removeEventListener("croplens:version",onVersion)};
  },[]);
  function toggleExplain() {
    const next = !explain;
    setExplain(next);
    localStorage.setItem("croplens-codelens", next ? "on" : "off");
    window.dispatchEvent(new CustomEvent("croplens:codelens", { detail: next }));
  }
  return <header className="sticky top-0 z-30 flex min-h-[72px] w-full items-center justify-between gap-4 border-b border-croplens-border bg-white/95 px-5 backdrop-blur sm:px-8">
    <div className="min-w-0"><p className="text-sm font-semibold text-zinc-100">{routeNames[pathname] || "CropLens"}</p><p className="mt-0.5 truncate text-[11px] text-zinc-400">{datasetContext.name?`${datasetContext.name}${datasetContext.versionId?` · ${datasetContext.versionId}`:""}`:"Agricultural dataset intelligence"}</p></div>
    <div className="flex items-center gap-2 sm:gap-3">
      <button type="button" onClick={toggleExplain} aria-pressed={explain} className={`inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-xs font-medium transition-colors ${explain ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-croplens-border bg-white text-zinc-400 hover:bg-gray-50"}`}><ScanSearch size={15}/><span className="hidden sm:inline">CodeLens</span><span className={`h-1.5 w-1.5 rounded-full ${explain ? "bg-emerald-600" : "bg-gray-300"}`}/></button>
      <button onClick={refresh} title="Refresh backend status" className="inline-flex h-9 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs text-zinc-400 hover:bg-gray-50" aria-label="Refresh API status"><span className={`h-2 w-2 rounded-full ${status === "connected" ? "bg-emerald-600" : status === "checking" ? "animate-pulse bg-amber-500" : "bg-red-500"}`}/><span className="hidden lg:inline">{status === "connected" ? `API ${data?.version ?? "online"}` : status === "checking" ? "Checking API" : "API offline"}</span><RefreshCw size={13}/></button>
      <a href={`${(process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}/api/v1/docs`} target="_blank" rel="noreferrer" className="hidden h-9 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs text-zinc-400 hover:bg-gray-50 sm:inline-flex"><BookOpen size={14}/>API Docs</a>
    </div>
  </header>;
}
