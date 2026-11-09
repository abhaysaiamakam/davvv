"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Archive, CheckCircle2, Download, FileDown, FileJson, FileSpreadsheet, FileText, LoaderCircle, RefreshCw } from "lucide-react";
import type { ExportFormat, ExportJob, ExportType } from "@croplens/shared-types";
import { apiClient } from "@/lib/api-client";
import { useDatasetContext } from "@/hooks/use-dataset-context";
import { useDatasetVersion } from "@/hooks/use-dataset-version";
import { WorkspaceDatasetSelect } from "@/components/ui/workspace-dataset-select";
import { WorkspaceVersionSelect } from "@/components/ui/workspace-version-select";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { formatDate } from "@/lib/utils";

const labels: Record<ExportType, string> = {
  comprehensive: "Comprehensive analysis report", eda: "EDA report", quality: "Data quality report",
  preprocessing: "Preprocessing history", feature_engineering: "Feature engineering results",
  readiness: "Dataset readiness report", methodology: "Methodology and provenance", dataset: "Dataset archive",
};
const formats: Array<{ id: ExportFormat; label: string; icon: typeof FileText }> = [
  { id: "csv", label: "CSV", icon: FileSpreadsheet }, { id: "json", label: "JSON", icon: FileJson },
  { id: "pdf", label: "PDF", icon: FileText }, { id: "zip", label: "ZIP bundle", icon: Archive },
];

export default function ExportsPage() {
  const context = useDatasetContext();
  const version = useDatasetVersion(context.selectedId, context.selected?.current_version_id);
  const [exportType, setExportType] = useState<ExportType>("comprehensive");
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [includeMethodology, setIncludeMethodology] = useState(true);
  const [includeVisualizations, setIncludeVisualizations] = useState(false);
  const [history, setHistory] = useState<ExportJob[]>([]);
  const [active, setActive] = useState<ExportJob | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const datasetQueryApplied = useRef(false);
  const queryApplied = useRef(false);
  const submission = useRef(false);
  const activeId = active?.export_id;
  const activeStatus = active?.status;
  const versionList = version.versions;
  const versionLoading = version.loading;
  const selectVersion = version.select;
  const datasets = context.datasets;
  const contextLoading = context.loading;
  const selectDataset = context.select;
  const allowedFormats = useMemo(() => exportType === "dataset" ? formats.filter(item => item.id === "csv" || item.id === "zip") : formats, [exportType]);

  const loadHistory = useCallback(async () => {
    if (!context.selectedId || !version.versionId) { setHistory([]); return; }
    setLoadingHistory(true);
    try { setHistory(await apiClient.listExports(context.selectedId, version.versionId)); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "Export history could not be loaded."); }
    finally { setLoadingHistory(false); }
  }, [context.selectedId, version.versionId]);

  useEffect(() => { void loadHistory(); }, [loadHistory]);
  useEffect(() => { setActive(null); setWorking(false); setError(null); submission.current = false; }, [context.selectedId, version.versionId]);
  useEffect(() => {
    if (!activeId || !activeStatus || !["queued", "running"].includes(activeStatus)) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void apiClient.getExport(activeId).then(next => {
        if (cancelled) return;
        setActive(next);
        setHistory(rows => [next, ...rows.filter(row => row.export_id !== next.export_id)]);
        if (next.status === "completed" || next.status === "failed") { setWorking(false); submission.current = false; }
      }).catch(issue => {
        if (!cancelled) { setError(issue instanceof Error ? issue.message : "Export status could not be checked."); setWorking(false); submission.current = false; }
      });
    }, 900);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeId, activeStatus]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("type") as ExportType | null;
    if (requested && requested in labels) setExportType(requested);
  }, []);
  useEffect(() => {
    if (datasetQueryApplied.current || contextLoading) return;
    datasetQueryApplied.current = true;
    const requestedDataset = new URLSearchParams(window.location.search).get("dataset_id");
    if (requestedDataset && datasets.some(item => item.id === requestedDataset)) selectDataset(requestedDataset);
  }, [contextLoading, datasets, selectDataset]);
  useEffect(() => {
    if (queryApplied.current || versionLoading || !versionList.length) return;
    queryApplied.current = true;
    const requestedVersion = new URLSearchParams(window.location.search).get("version_id");
    if (requestedVersion && versionList.some(item => item.version_id === requestedVersion)) selectVersion(requestedVersion);
  }, [versionLoading, versionList, selectVersion]);
  useEffect(() => { if (exportType === "dataset") setFormat("zip"); }, [exportType]);

  async function create() {
    if (!context.selectedId || !version.versionId || working || submission.current) return;
    submission.current = true;
    setWorking(true); setError(null); setActive(null);
    try {
      const job = await apiClient.createExport(context.selectedId, version.versionId, {
        export_type: exportType, format, include_methodology: includeMethodology,
        include_visualizations: format === "zip" && includeVisualizations,
      });
      setActive(job);
      setHistory(rows => [job, ...rows.filter(row => row.export_id !== job.export_id)]);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Export could not be started."); setWorking(false); submission.current = false; }
  }

  return <PageContainer title="Export Center" description="Generate downloads from real analysis artifacts or archive the exact selected dataset version." badge="Version-bound exports" actions={<div className="grid w-full gap-2 sm:w-[32rem] sm:grid-cols-2"><WorkspaceDatasetSelect datasets={context.datasets} value={context.selectedId} onChange={context.select} loading={context.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={id => { version.select(id); setActive(null); }} loading={version.loading}/></div>}>
    {context.error && <ErrorState title="Dataset registry unavailable" message={context.error} onRetry={() => void context.reload()}/>}
    {version.error && <ErrorState title="Dataset versions unavailable" message={version.error} onRetry={() => void version.reload()}/>}
    {!context.loading && !context.selectedId && <EmptyState icon={<FileDown/>} title="Select a dataset" description="Choose a dataset and a stored version before creating an export."/>}
    {error && <ErrorState title="Export request failed" message={error} onRetry={() => { setError(null); void loadHistory(); }}/>}
    {context.selectedId && version.versionId && <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
      <DashboardCard title="Create an export" icon={<FileDown size={17}/>} description={`Every export is bound to dataset ${context.selectedId}, version ${version.versionId}. Dataset archives contain the selected version's real files and preserve source annotation files.`}>
        <div className="space-y-4">
          <label className="block text-xs font-medium text-zinc-600">Report or data
            <select value={exportType} onChange={event => setExportType(event.target.value as ExportType)} className="mt-1 h-10 w-full rounded-lg border border-croplens-border bg-white px-3 text-sm text-zinc-900">
              {Object.entries(labels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <fieldset><legend className="mb-2 text-xs font-medium text-zinc-600">Format</legend><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{allowedFormats.map(item => { const Icon = item.icon; return <button key={item.id} type="button" onClick={() => setFormat(item.id)} aria-pressed={format === item.id} className={`flex h-16 flex-col items-center justify-center gap-1 rounded-lg border text-xs ${format === item.id ? "border-emerald-600 bg-emerald-50 text-emerald-900" : "border-croplens-border text-zinc-600 hover:bg-gray-50"}`}><Icon size={17}/>{item.label}</button>; })}</div></fieldset>
          {exportType !== "dataset" && <div className="space-y-2 rounded-lg bg-gray-50 p-3"><label className="flex items-start gap-2 text-xs text-zinc-700"><input type="checkbox" checked={includeMethodology} onChange={event => setIncludeMethodology(event.target.checked)} className="mt-0.5 accent-emerald-700"/><span>Include methodology and provenance</span></label>{format === "zip" && <label className="flex items-start gap-2 text-xs text-zinc-700"><input type="checkbox" checked={includeVisualizations} onChange={event => setIncludeVisualizations(event.target.checked)} className="mt-0.5 accent-emerald-700"/><span>Include versioned visualization specifications when available</span></label>}</div>}
          {exportType === "dataset" && <p className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs leading-relaxed text-blue-900">{format === "csv" ? "For image datasets, CSV contains real image metadata and opaque references. A single CSV/TSV table exports its actual records. Use ZIP for multiple tables or complete image datasets." : "The ZIP preserves original files for this version. Image archives also include actual image metadata; COCO/YOLO source files are included unchanged."} No image pixels are converted into CSV records.</p>}
          <button type="button" disabled={working || !context.selectedId || !version.versionId} onClick={() => void create()} className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-gray-300">{working ? <LoaderCircle size={16} className="animate-spin"/> : <Download size={16}/>}Generate {formats.find(item => item.id === format)?.label} export</button>
        </div>
      </DashboardCard>
      <DashboardCard title="Export status" icon={<RefreshCw size={17}/>} description="Large archive creation runs in the background. You can keep working while progress updates.">
        {active ? <div className="space-y-3"><div className="flex items-center gap-2 text-sm font-semibold text-zinc-900">{active.status === "completed" ? <CheckCircle2 className="text-emerald-700" size={18}/> : active.status === "failed" ? <span className="text-red-700">×</span> : <LoaderCircle className="animate-spin text-emerald-700" size={18}/>}<span>{labels[active.export_type]} · {active.status}</span></div><p className="text-xs text-zinc-500">Version {active.version_id} · {formatDate(active.created_at)}</p><div role="progressbar" aria-label="Export generation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={active.progress_pct} className="h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-emerald-600 transition-all" style={{ width: `${active.progress_pct}%` }}/></div><p className="text-right text-[10px] tabular-nums text-zinc-500">{Math.round(active.progress_pct)}%</p>{active.status === "completed" && active.download_url && <a href={apiClient.exportDownloadUrl(active.export_id)} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white"><Download size={14}/>Download {active.filename}</a>}{active.status === "failed" && <p role="alert" className="text-xs text-red-700">{active.error_message ?? "Export failed."}</p>}</div> : <EmptyState icon={<Archive/>} title="No export running" description="Choose a report or dataset archive to generate a download."/>}
      </DashboardCard>
    </div>}
    {context.selectedId && version.versionId && <DashboardCard title="Export history" icon={<FileText size={17}/>} headerAction={<button type="button" onClick={() => void loadHistory()} aria-label="Refresh export history" className="rounded-md p-2 text-zinc-500 hover:bg-gray-50"><RefreshCw size={14}/></button>}>
      {loadingHistory ? <LoadingState label="Loading exports for this version…"/> : history.length ? <div className="divide-y divide-gray-100">{history.map(row => <div key={row.export_id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="text-xs font-semibold text-zinc-800">{labels[row.export_type]} · {row.format.toUpperCase()} · {row.status}</p><p className="mt-1 text-[10px] text-zinc-500">Version {row.version_id} · {formatDate(row.created_at)}</p></div>{row.status === "completed" && <a href={apiClient.exportDownloadUrl(row.export_id)} className="inline-flex items-center gap-1 rounded-md border border-croplens-border px-2.5 py-1.5 text-[10px] font-medium text-zinc-700"><Download size={12}/>Download</a>}</div>)}</div> : <p className="text-xs text-zinc-500">No exports have been generated for this dataset version.</p>}
    </DashboardCard>}
    <p className="text-[11px] text-zinc-500">Analysis exports include only artifacts already produced for this version. Missing analyses remain absent from the output. <Link href="/reports" className="font-medium text-emerald-800 underline">Review analytical report history</Link>.</p>
  </PageContainer>;
}
