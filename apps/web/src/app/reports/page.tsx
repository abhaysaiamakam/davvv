"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, FileText, LoaderCircle, RefreshCw } from "lucide-react";
import type { AnalyticalReport, ReportListResponse } from "@croplens/shared-types";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useDatasetContext } from "@/hooks/use-dataset-context";
import { WorkspaceDatasetSelect } from "@/components/ui/workspace-dataset-select";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { formatDate } from "@/lib/utils";
import { useDatasetVersion } from "@/hooks/use-dataset-version";
import { WorkspaceVersionSelect } from "@/components/ui/workspace-version-select";
import { ContextualExportAction } from "@/components/exports/contextual-export-action";

export default function ReportsPage() {
  const ctx = useDatasetContext();
  const version = useDatasetVersion(ctx.selectedId,ctx.selected?.current_version_id);
  const [data, setData] = useState<ReportListResponse | null>(null);
  const [selected, setSelected] = useState<AnalyticalReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!ctx.selectedId) return;
    setLoading(true); setError(null);
    try { const result=await apiClient.getReports(ctx.selectedId,version.versionId||undefined); setData(result); setSelected(result.items[0]??null); }
    catch(issue){setData(null);setSelected(null);if(!(issue instanceof ApiClientError&&issue.status===404))setError(issue instanceof Error?issue.message:"Could not load reports.");}
    finally{setLoading(false);}
  },[ctx.selectedId,version.versionId]);
  useEffect(()=>{void load();},[load]);
  async function generate(){if(!ctx.selectedId)return;setGenerating(true);setError(null);try{const report=await apiClient.generateReport(ctx.selectedId,{version_id:version.versionId||null});setSelected(report);await load();}catch(issue){setError(issue instanceof Error?issue.message:"Report generation failed.");}finally{setGenerating(false);}}
  return <PageContainer title="Reports" description="Generate and export evidence-backed reports with methodology and provenance from the CropLens analysis pipeline." badge="Auditable exports" actions={<div className="flex w-full flex-wrap items-center gap-2 sm:w-auto"><div className="grid min-w-0 flex-1 gap-2 sm:w-[32rem] sm:grid-cols-2"><WorkspaceDatasetSelect datasets={ctx.datasets} value={ctx.selectedId} onChange={ctx.select} loading={ctx.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={id=>{version.select(id);setSelected(null)}} loading={version.loading}/></div><ContextualExportAction type="comprehensive" versionId={version.versionId}/></div>}>
    {ctx.error&&<ErrorState title="Dataset registry unavailable" message={ctx.error} onRetry={()=>void ctx.reload()}/>}{error&&<ErrorState title="Report service unavailable" message={error} onRetry={()=>void load()}/>}
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-croplens-border bg-white p-4"><div><p className="text-sm font-semibold text-zinc-100">Analytical report</p><p className="mt-1 text-xs text-zinc-400">Assembles existing evidence for the selected dataset version.</p></div><button disabled={!ctx.selectedId||generating} onClick={()=>void generate()} className="inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-700 px-3 text-xs font-semibold text-white hover:bg-emerald-800 disabled:bg-gray-300">{generating?<LoaderCircle size={14} className="animate-spin"/>:<FileText size={14}/>}Generate report</button></div>
    {loading?<LoadingState label="Loading report history…"/>:data?.items.length?<div className="grid gap-5 xl:grid-cols-[.7fr_1.3fr]"><DashboardCard title="Report history" icon={<FileText size={17}/>}><div className="space-y-2">{data.items.map(report=><button key={report.report_id} onClick={()=>setSelected(report)} className={`w-full rounded-lg border p-3 text-left transition ${selected?.report_id===report.report_id?"border-emerald-300 bg-emerald-50":"border-croplens-border hover:bg-gray-50"}`}><p className="text-xs font-semibold text-zinc-100">{report.title}</p><p className="mt-1 text-[10px] text-zinc-400">{formatDate(report.created_at)} · version {report.version_id}</p><p className="mt-1 text-[10px] capitalize text-zinc-400">Readiness: {report.readiness_section.overall_status.replaceAll("_"," ")}</p></button>)}</div></DashboardCard>{selected&&<DashboardCard title={selected.title} icon={<FileText size={17}/>} badge={{text:selected.provenance.generator_status,variant:selected.provenance.generator_status==="completed"?"emerald":"amber"}} description={`${selected.dataset_overview.dataset_name} · ${selected.dataset_overview.version_id} · generated ${formatDate(selected.created_at)}`}>
      <div className="flex flex-wrap gap-2"><a href={apiClient.reportDownloadUrl(ctx.selectedId,selected.report_id,"pdf")} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-800"><Download size={14}/>Export PDF</a><a href={apiClient.reportDownloadUrl(ctx.selectedId,selected.report_id,"json")} className="inline-flex items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 py-2 text-xs font-medium text-zinc-100 hover:bg-gray-50"><Download size={14}/>Export JSON</a></div>
      <div className="mt-5 rounded-lg bg-gray-50 p-4"><p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Executive summary</p><p className="mt-2 text-sm font-medium text-zinc-100">{selected.executive_summary.main_objective}</p><div className="mt-3 grid gap-3 sm:grid-cols-2"><SummaryList title="Key findings" items={selected.executive_summary.key_findings}/><SummaryList title="Quality concerns" items={selected.executive_summary.quality_concerns}/><SummaryList title="Recommended next steps" items={selected.executive_summary.recommended_next_steps}/></div></div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3"><Tiny label="Files" value={selected.dataset_overview.total_files}/><Tiny label="Quality score" value={selected.quality_section.quality_score??"Not available"}/><Tiny label="Readiness" value={selected.readiness_section.overall_status.replaceAll("_"," ")}/></div>
      <div className="mt-4 border-t border-croplens-border pt-4"><p className="text-xs font-semibold text-zinc-100">Methodology and provenance</p><p className="mt-1 text-xs text-zinc-400">{selected.methodology_section.workflow_summary}</p><p className="mt-2 font-mono text-[10px] text-zinc-400">Report {selected.provenance.report_id} · schema {selected.provenance.schema_version} · {selected.provenance.content_fingerprint??"fingerprint unavailable"}</p><div className="mt-3 space-y-1">{selected.methodology_section.steps.map(step=><p key={step.step_number} className="text-[11px] text-zinc-400">{step.step_number}. {step.stage_name}: {step.operation_name} · {formatDate(step.timestamp)}</p>)}</div></div>
    </DashboardCard>}</div>:<EmptyState icon={<FileText/>} title="No reports for this dataset" description="Generate a report after the analysis artifacts are available. The report will include only evidence the backend has produced."/>}
    {!loading&&data?.items.length===0&&<button onClick={()=>void load()} className="inline-flex items-center gap-2 text-xs text-zinc-400"><RefreshCw size={13}/>Refresh history</button>}
  </PageContainer>;
}
function SummaryList({title,items}:{title:string;items:string[]}){return <div><p className="text-[11px] font-semibold text-zinc-100">{title}</p>{items.length?<ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] text-zinc-400">{items.map((item,i)=><li key={`${i}-${item}`}>{item}</li>)}</ul>:<p className="mt-1 text-[11px] text-zinc-400">None reported</p>}</div>}
function Tiny({label,value}:{label:string;value:string|number}){return <div className="rounded-lg border border-croplens-border p-3"><p className="text-[10px] text-zinc-400">{label}</p><p className="mt-1 text-sm font-semibold capitalize text-zinc-100">{value}</p></div>}
