"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart3, LoaderCircle, RefreshCw, ScanSearch } from "lucide-react";
import type { EdaReport, VisualizationCollectionResponse } from "@croplens/shared-types";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useDatasetContext } from "@/hooks/use-dataset-context";
import { WorkspaceDatasetSelect } from "@/components/ui/workspace-dataset-select";
import { VisualizationChart } from "@/components/ui/visualization-chart";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/utils";
import { CodeLensExplainability } from "@/components/ui/codelens";
import { ContextualExportAction } from "@/components/exports/contextual-export-action";
import { useDatasetVersion } from "@/hooks/use-dataset-version";
import { WorkspaceVersionSelect } from "@/components/ui/workspace-version-select";
import { EvidenceImageGrid } from "@/components/evidence/evidence-image-grid";

export default function EDAPage() {
  const ctx = useDatasetContext();
  const version = useDatasetVersion(ctx.selectedId, ctx.selected?.current_version_id);
  const [report, setReport] = useState<EdaReport | null>(null);
  const [charts, setCharts] = useState<VisualizationCollectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!ctx.selectedId) return;
    setLoading(true); setError(null);
    const [eda, visualizations] = await Promise.allSettled([apiClient.getEda(ctx.selectedId, version.versionId || undefined), apiClient.getVisualizations(ctx.selectedId, version.versionId || undefined)]);
    if (eda.status === "fulfilled") setReport(eda.value); else setReport(null);
    if (visualizations.status === "fulfilled") setCharts(visualizations.value); else setCharts(null);
    const reasons = [eda.status === "rejected" && !(eda.reason instanceof ApiClientError && eda.reason.status === 404) ? eda.reason : null, visualizations.status === "rejected" && !(visualizations.reason instanceof ApiClientError && visualizations.reason.status === 404) ? visualizations.reason : null].filter(Boolean);
    if (reasons.length) setError(reasons[0] instanceof Error ? reasons[0].message : "EDA data unavailable.");
    setLoading(false);
  }, [ctx.selectedId, version.versionId]);
  useEffect(() => { void load(); }, [load]);
  async function run() {
    if (!ctx.selectedId) return;
    setRunning(true); setError(null);
    try {
      setReport(await apiClient.runEda(ctx.selectedId, version.versionId || undefined));
      setCharts(await apiClient.getVisualizations(ctx.selectedId, version.versionId || undefined));
    } catch (issue) { setError(issue instanceof Error ? issue.message : "EDA run failed."); }
    finally { setRunning(false); }
  }
  return <PageContainer title="EDA Studio" description="Explore backend generated distributions, dataset structure, and evidence-backed EDA findings." badge="Exploratory analysis" actions={<div className="flex w-full flex-wrap items-center gap-2 sm:w-auto"><div className="grid min-w-0 flex-1 gap-2 sm:w-[32rem] sm:grid-cols-2"><WorkspaceDatasetSelect datasets={ctx.datasets} value={ctx.selectedId} onChange={ctx.select} loading={ctx.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={version.select} loading={version.loading}/></div><ContextualExportAction type="eda" versionId={version.versionId}/></div>}>
    {ctx.error && <ErrorState title="Dataset registry unavailable" message={ctx.error} onRetry={() => void ctx.reload()}/>}
    {error && <ErrorState title="EDA data unavailable" message={error} onRetry={() => void load()}/>}
    {loading ? <LoadingState label="Loading dataset analysis and chart specifications…"/> : report ? <>
      <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-4 py-3 text-xs leading-relaxed text-blue-950"><span className="font-semibold">Artifact scope:</span> report {report.version_id ?? "version unknown"} · selected version {version.versionId ?? "none"}</div>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{(report.modality === "tabular" ? [["Rows",report.tabular_summary?.row_count ?? "—"],["Columns",report.tabular_summary?.column_count ?? "—"],["Missing cells",report.tabular_summary?.missing_cell_count ?? "—"],["Files",report.tabular_summary?.files.length ?? "—"]] : [["Valid images",report.overview.total_valid_images ?? "—"],["Classes",report.overview.class_count ?? "—"],["Files",report.overview.total_discovered_files ?? "—"],["EDA findings",report.findings.length]]).map(([label,value])=><div key={String(label)} className="rounded-xl border border-croplens-border bg-white p-4"><p className="text-xs text-zinc-400">{label}</p><p className="mt-2 text-2xl font-semibold text-zinc-100">{value}</p></div>)}</section>
      {report.modality === "tabular" && report.tabular_summary && <DashboardCard title="Tabular file summaries" icon={<BarChart3 size={17}/>} description="Counts and missing cells are calculated from the selected version's source files."><div className="space-y-4">{report.tabular_summary.files.map((file)=><section key={file.file} className="rounded-lg border border-croplens-border p-3"><h3 className="text-sm font-semibold">{file.file} · {file.row_count} rows × {file.column_count} columns</h3><div className="mt-2 flex flex-wrap gap-2">{Object.entries(file.missing_by_column).filter(([,count])=>count>0).map(([column,count])=><span key={column} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">{column}: {count} missing</span>)}</div></section>)}</div></DashboardCard>}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-400"><span>{report.dataset_name} · analysis {report.id}</span><span>Generated {formatDate(report.completed_at ?? report.created_at)} · {report.methodology_version}</span></div>
      <section className="grid gap-5 lg:grid-cols-2">{charts?.items.length ? charts.items.map((spec)=>{
        const explanationId=spec.category==="class_distribution"?"eda.class_distribution":spec.category==="image_geometry"?"eda.dimensions":spec.category==="format_and_color"?"eda.color":spec.category==="tabular_distribution"?"eda.tabular":null;
        const provenance: Array<[string,string|number|null|undefined]>=[["Visualization ID",spec.visualization_id],["Chart type",spec.chart_type],...Object.entries(spec.source_artifacts??{})];
        return <DashboardCard key={spec.visualization_id} title={spec.title} icon={<BarChart3 size={17}/>} badge={{text:spec.chart_type.replaceAll("_"," "),variant:"neutral"}} description={spec.description}><VisualizationChart spec={spec}/><div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-croplens-border pt-3 text-[10px] text-zinc-400"><div className="flex flex-wrap gap-1.5"><span>Version {spec.dataset_version}</span>{spec.source_artifacts && Object.entries(spec.source_artifacts).map(([key,value])=>value&&<span key={key} className="rounded bg-gray-100 px-2 py-1">{key}: {value}</span>)}</div>{explanationId&&<CodeLensExplainability explanationId={explanationId} resultTitle={spec.title} datasetVersion={spec.dataset_version} provenance={provenance}/>}</div></DashboardCard>
      }) : <div className="lg:col-span-2"><EmptyState icon={<ScanSearch/>} title="No chart specifications returned" description="The API has no supported chart data for this dataset yet. The EDA report below remains available."/></div>}</section>
      <DashboardCard title="EDA findings" icon={<ScanSearch size={17}/>} badge={{text:`${report.findings.length} findings`,variant:"emerald"}}>
        {report.findings.length ? <div className="divide-y divide-croplens-border">{report.findings.map((finding)=><article key={finding.id} className="py-4 first:pt-0 last:pb-0"><div className="flex flex-wrap gap-2"><span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium capitalize text-gray-600">{finding.category.replaceAll("_"," ")}</span><span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium capitalize text-amber-800">{finding.severity}</span></div><h3 className="mt-2 text-sm font-semibold text-zinc-100">{finding.title}</h3><p className="mt-1 text-xs leading-relaxed text-zinc-400">{finding.explanation}</p><p className="mt-2 text-xs text-zinc-400">Metric: {finding.metric_name} = {String(finding.observed_value)}{finding.threshold_used!=null?` · Threshold ${String(finding.threshold_used)}`:""}</p>{finding.affected_classes.length>0&&<p className="mt-1 text-[10px] text-zinc-500">Affected classes: {finding.affected_classes.join(", ")}</p>}{finding.evidence_references.length>0&&<details className="mt-2"><summary className="cursor-pointer text-[10px] font-semibold text-emerald-800">Evidence references</summary><ul className="mt-1 list-disc pl-5 text-[10px] text-zinc-500">{finding.evidence_references.map((ref,index)=><li key={`${index}-${ref}`}>{ref}</li>)}</ul></details>}{finding.affected_image_samples.length>0&&report.version_id?<EvidenceImageGrid datasetId={report.dataset_id} versionId={report.version_id} images={finding.affected_image_samples.map(path=>({relativePath:path,label:"EDA supporting image",className:finding.affected_classes.join(", ")}))}/>:finding.affected_image_samples.length>0?<p className="mt-3 rounded-lg bg-amber-50 p-3 text-[10px] text-amber-900">Image sample paths are present, but this report has no version snapshot; previews are withheld to avoid resolving evidence from another version.</p>:<p className="mt-3 text-[10px] text-zinc-500">This finding has no returned image/record samples. Chart visualizations remain aggregate data and are not tied to individual records.</p>}<p className="mt-2 text-xs text-zinc-400">Recommended action: {finding.recommended_action}</p></article>)}</div> : <p className="text-xs text-zinc-400">No EDA findings were returned.</p>}
      </DashboardCard>
      {report.warnings.length>0&&<div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><p className="font-semibold">Analysis notes</p>{report.warnings.map((item,i)=><p className="mt-1" key={`${i}-${item}`}>{item}</p>)}</div>}
    </> : !ctx.loading && ctx.selectedId ? <EmptyState icon={<ScanSearch/>} title="EDA has not been run" description="Run EDA for the selected dataset. The Python analysis engine will return real statistics and findings." action={{label:running?"Running EDA…":"Run EDA",onClick:()=>void run()}}/> : null}
    {!loading && report && <button disabled={running} onClick={() => void run()} className="inline-flex h-9 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs font-medium text-zinc-100 disabled:opacity-50">{running?<LoaderCircle size={14} className="animate-spin"/>:<RefreshCw size={14}/>}Re-run EDA</button>}
  </PageContainer>;
}
