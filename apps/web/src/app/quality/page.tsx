"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CopyCheck, FileWarning, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import type { DataQualityAssessment } from "@croplens/shared-types";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useDatasetContext } from "@/hooks/use-dataset-context";
import { WorkspaceDatasetSelect } from "@/components/ui/workspace-dataset-select";
import { PageContainer } from "@/components/layout/page-container";
import { ContextualExportAction } from "@/components/exports/contextual-export-action";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/utils";
import { CodeLensExplainability } from "@/components/ui/codelens";

export default function QualityLabPage() {
  const ctx = useDatasetContext();
  const [assessment, setAssessment] = useState<DataQualityAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasAssessment, setHasAssessment] = useState(false);
  const load = useCallback(async () => {
    if (!ctx.selectedId) return;
    setLoading(true); setError(null);
    try { setAssessment(await apiClient.getQuality(ctx.selectedId)); setHasAssessment(true); }
    catch (issue) { setAssessment(null); setHasAssessment(false); if (!(issue instanceof ApiClientError && issue.status === 404)) setError(issue instanceof Error ? issue.message : "Unable to load quality assessment."); }
    finally { setLoading(false); }
  }, [ctx.selectedId]);
  useEffect(() => { void load(); }, [load]);
  async function run() {
    if (!ctx.selectedId) return;
    setRunning(true); setError(null);
    try { setAssessment(await apiClient.assessQuality(ctx.selectedId)); setHasAssessment(true); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "Quality assessment failed."); }
    finally { setRunning(false); }
  }
  const q = assessment;
  return <PageContainer title="Data Quality" description="Review integrity, class balance, metadata consistency, and duplicate impact from the backend assessment." badge="Evidence-backed" actions={<div className="flex w-full items-center gap-2 sm:w-auto"><div className="min-w-0 flex-1 sm:w-64"><WorkspaceDatasetSelect datasets={ctx.datasets} value={ctx.selectedId} onChange={ctx.select} loading={ctx.loading}/></div><ContextualExportAction type="quality" versionId={ctx.selected?.current_version_id}/></div>}>
    {ctx.error && <ErrorState title="Dataset registry unavailable" message={ctx.error} onRetry={() => void ctx.reload()}/>}
    {error && <ErrorState title="Quality data unavailable" message={error} onRetry={() => void load()}/>}
    {loading ? <LoadingState label="Loading quality assessment…"/> : q ? <>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Quality score" value={`${q.quality_score.overall_score.toFixed(1)}`} detail={q.quality_score.quality_tier}/>
        <Metric label="Validated images" value={q.integrity.total_validated_images ?? "—"} detail={`${q.integrity.total_corrupted_images ?? "—"} corrupt`}/>
        <Metric label="Class imbalance" value={q.imbalance.imbalance_ratio == null ? "—" : `${q.imbalance.imbalance_ratio.toFixed(2)}×`} detail={q.imbalance.imbalance_severity.replaceAll("_", " ")}/>
        <Metric label="Duplicate groups" value={q.duplicate_impact.exact_duplicate_groups ?? "—"} detail={q.duplicate_impact.duplicate_impact_severity.replaceAll("_", " ")}/>
      </section>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-croplens-border bg-white px-4 py-3"><p className="text-xs text-zinc-400">Latest dataset-level assessment {q.id} · {formatDate(q.completed_at ?? q.created_at)} · methodology {q.methodology_version} · source analysis {q.source_analysis_id??"not provided"}</p><CodeLensExplainability explanationId="quality.score" resultTitle="Overall dataset quality score" provenance={[["Assessment ID",q.id],["Source analysis",q.source_analysis_id],["Quality tier",q.quality_score.quality_tier],["Completeness",String(q.quality_score.is_complete)]]}/></div>
      <div className="grid gap-5 xl:grid-cols-[1.2fr_.8fr]">
        <DashboardCard title="Findings" icon={<AlertCircle size={17}/>} badge={{text:`${q.findings.length} findings`,variant:q.findings.some((f)=>f.severity==="critical"||f.severity==="high")?"amber":"emerald"}} description={`Assessment ${q.id} · ${formatDate(q.completed_at ?? q.created_at)}`}>
          {q.findings.length ? <div className="divide-y divide-croplens-border">{q.findings.map((finding) => {const id=finding.category==="integrity"?"quality.integrity":finding.category==="imbalance"?"quality.imbalance":finding.category==="duplicates"?"quality.duplicates":finding.category==="consistency"||finding.category==="metadata"?"quality.consistency":null;return <article key={finding.id} className="py-4 first:pt-0 last:pb-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${finding.severity === "critical" || finding.severity === "high" ? "bg-red-50 text-red-700" : finding.severity === "medium" ? "bg-amber-50 text-amber-800" : "bg-gray-100 text-gray-600"}`}>{finding.severity}</span><span className="text-[11px] capitalize text-zinc-400">{finding.category.replaceAll("_", " ")}</span></div><h3 className="mt-2 text-sm font-semibold text-zinc-100">{finding.title}</h3><p className="mt-1 text-xs leading-relaxed text-zinc-400">{finding.explanation}</p><p className="mt-2 text-xs"><span className="font-medium text-zinc-100">Next step: </span><span className="text-zinc-400">{finding.recommended_action}</span></p><div className="mt-2 flex flex-wrap gap-2 text-[10px] text-zinc-400"><span>Metric: {finding.metric_name} = {String(finding.observed_value)}</span>{finding.threshold_used&&<span>Threshold: {finding.threshold_used}</span>}{id&&<CodeLensExplainability explanationId={id} resultTitle={finding.title} provenance={[["Finding ID",finding.id],["Metric",finding.metric_name],["Observed value",String(finding.observed_value)],["Methodology",finding.methodology_version]]}/>}</div></article>})}</div> : <p className="py-5 text-sm text-zinc-400">The assessment returned no findings.</p>}
        </DashboardCard>
        <div className="space-y-5">
          <DashboardCard title="Quality dimensions" icon={<ShieldCheck size={17}/>} description="Availability reflects what the backend could assess from available artifacts.">
            <Dimension label="Image integrity" status={q.integrity.status} value={q.integrity.integrity_rate == null ? null : `${q.integrity.integrity_rate.toFixed(1)}%`} notes={q.integrity.evaluation_notes}/>
            <Dimension label="Metadata consistency" status={q.metadata_consistency.is_available ? "Available" : "Unavailable"} value={q.metadata_consistency.consistency_rate == null ? null : `${q.metadata_consistency.consistency_rate.toFixed(1)}%`} notes={q.metadata_consistency.evaluation_notes}/>
            <Dimension label="Duplicate impact" status={q.duplicate_impact.is_available ? q.duplicate_impact.duplicate_impact_severity : "Unavailable"} value={q.duplicate_impact.exact_duplicate_percentage == null ? null : `${q.duplicate_impact.exact_duplicate_percentage.toFixed(2)}%`} notes={q.duplicate_impact.evaluation_notes}/>
          </DashboardCard>
          <DashboardCard title="Class distribution" icon={<CopyCheck size={17}/>}>
            {Object.entries(q.imbalance.class_distribution).length ? <div className="max-h-64 space-y-2 overflow-y-auto">{Object.entries(q.imbalance.class_distribution).sort((a,b)=>b[1]-a[1]).map(([name,count])=><div key={name} className="flex items-center justify-between gap-3 text-xs"><span className="min-w-0 truncate text-zinc-400" title={name}>{name}</span><span className="shrink-0 font-mono text-zinc-100">{count}</span></div>)}</div> : <p className="text-xs text-zinc-400">Class counts were not included in this assessment.</p>}
          </DashboardCard>
        </div>
      </div>
      {q.warnings.length > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><p className="font-semibold">Assessment notes</p><ul className="mt-2 list-disc space-y-1 pl-5">{q.warnings.map((warning,index)=><li key={`${index}-${warning}`}>{warning}</li>)}</ul></div>}
    </> : !ctx.loading && !ctx.selectedId ? <EmptyState title="No dataset selected" description="Upload or register a dataset to see quality results."/> : !ctx.loading && <EmptyState icon={<FileWarning/>} title={hasAssessment?"No assessment":"No quality assessment yet"} description="Run the backend quality engine to compute integrity, class balance, metadata, and duplicate impact from the selected dataset." action={{label:running?"Assessing…":"Run quality assessment",onClick:()=>void run()}}/>}
    {!loading && q && <button onClick={() => void run()} disabled={running} className="inline-flex h-9 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs font-medium text-zinc-100 hover:bg-gray-50 disabled:opacity-50">{running?<LoaderCircle className="animate-spin" size={14}/>:<RefreshCw size={14}/>}Refresh assessment</button>}
  </PageContainer>;
}

function Metric({label,value,detail}:{label:string;value:string|number;detail:string}){return <div className="rounded-xl border border-croplens-border bg-white p-4"><p className="text-xs text-zinc-400">{label}</p><p className="mt-2 text-2xl font-semibold text-zinc-100">{value}</p><p className="mt-1 text-[11px] capitalize text-zinc-400">{detail}</p></div>}
function Dimension({label,status,value,notes}:{label:string;status:string;value:string|null;notes:string[]}){return <div className="border-b border-croplens-border py-3 first:pt-0 last:border-0 last:pb-0"><div className="flex items-center justify-between gap-3"><span className="text-xs font-medium text-zinc-100">{label}</span><span className="text-xs font-semibold text-emerald-800">{value ?? status}</span></div>{notes[0]&&<p className="mt-1 text-[11px] leading-relaxed text-zinc-400">{notes[0]}</p>}</div>}
