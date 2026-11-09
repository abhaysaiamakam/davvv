"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, Lightbulb, RefreshCw } from "lucide-react";
import type { InsightCollectionResponse } from "@croplens/shared-types";
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

export default function InsightsPage() {
  const ctx = useDatasetContext();
  const version = useDatasetVersion(ctx.selectedId,ctx.selected?.current_version_id);
  const [collection, setCollection] = useState<InsightCollectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!ctx.selectedId) return;
    setLoading(true); setError(null);
    try { setCollection(await apiClient.getInsights(ctx.selectedId, version.versionId||undefined)); }
    catch (issue) { setCollection(null); if (!(issue instanceof ApiClientError && issue.status === 404)) setError(issue instanceof Error ? issue.message : "Could not load insights."); }
    finally { setLoading(false); }
  }, [ctx.selectedId, version.versionId]);
  useEffect(() => { void load(); }, [load]);
  return <PageContainer title="Insights" description="Backend generated findings with severity, confidence, supporting evidence, and recommended actions." badge="M7 insights" actions={<div className="grid w-full gap-2 sm:w-[32rem] sm:grid-cols-2"><WorkspaceDatasetSelect datasets={ctx.datasets} value={ctx.selectedId} onChange={ctx.select} loading={ctx.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={id=>{version.select(id);setCollection(null)}} loading={version.loading}/></div>}>
    {ctx.error && <ErrorState title="Dataset registry unavailable" message={ctx.error} onRetry={() => void ctx.reload()}/>}
    {error && <ErrorState title="Insight service unavailable" message={error} onRetry={() => void load()}/>}
    {loading ? <LoadingState label="Loading version specific insights…"/> : collection ? <>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-croplens-border bg-white px-4 py-3 text-xs"><div><span className="font-medium text-zinc-100">{ctx.selected?.name}</span><span className="ml-2 text-zinc-400">Version {collection.dataset_version}</span></div><span className="text-zinc-400">{collection.total} insights · {collection.status}</span></div>
      {collection.error_message&&<div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">{collection.error_message}</div>}
      {collection.items.length ? <div className="grid gap-4 xl:grid-cols-2">{collection.items.map((insight)=><DashboardCard key={insight.insight_id} title={insight.title} icon={<Lightbulb size={17}/>} badge={{text:insight.severity,variant:insight.severity==="critical"||insight.severity==="high"?"amber":"emerald"}} description={insight.summary}>
        <div className="flex flex-wrap gap-2 text-[10px]"><span className="rounded-full bg-gray-100 px-2 py-1 capitalize text-gray-700">{insight.category.replaceAll("_"," ")}</span><span className="rounded-full bg-gray-100 px-2 py-1 capitalize text-gray-700">{insight.confidence} confidence</span><span className="rounded-full bg-gray-100 px-2 py-1 text-gray-700">{formatDate(insight.created_at)}</span></div>
        <p className="mt-3 text-xs leading-relaxed text-zinc-400">{insight.explanation}</p>
        {insight.evidence.length>0&&<div className="mt-4 rounded-lg bg-gray-50 p-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Evidence</p><div className="mt-2 space-y-2">{insight.evidence.map((item,index)=><div key={`${item.source_artifact}-${index}`} className="border-l-2 border-emerald-300 pl-2.5"><p className="text-xs font-medium text-zinc-100">{item.metric}: <span className="font-mono">{String(item.value)}{item.unit??""}</span></p><p className="mt-0.5 text-[11px] text-zinc-400">{item.explanation}</p><p className="mt-0.5 text-[10px] text-zinc-400">Source: {item.source_artifact} · {item.source_path}</p></div>)}</div></div>}
        {insight.affected_classes.length>0&&<div className="mt-3 flex flex-wrap gap-1.5">{insight.affected_classes.slice(0,8).map((name)=><span key={name} className="rounded bg-emerald-50 px-2 py-1 text-[10px] text-emerald-900">{name}</span>)}</div>}
        <div className="mt-4 rounded-lg border border-emerald-100 bg-emerald-50/60 p-3"><p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-900"><ArrowUpRight size={12}/>Recommended next action</p><p className="mt-1 text-xs leading-relaxed text-emerald-950">{insight.recommended_action}</p></div>
        {insight.limitations&&<p className="mt-3 flex gap-1.5 text-[11px] text-zinc-400"><AlertTriangle size={13} className="mt-0.5 shrink-0"/>{insight.limitations}</p>}
      </DashboardCard>)}</div> : <EmptyState icon={<Lightbulb/>} title="No insights for this version" description="The selected version has no stored M7 insight collection. Run the backend analysis pipeline first."/>}
    </> : !ctx.loading&&<EmptyState icon={<Lightbulb/>} title="No insights available" description="Select or upload a dataset to view version scoped findings."/>}
    {!loading&&collection&&<button onClick={()=>void load()} className="inline-flex h-9 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs font-medium text-zinc-100"><RefreshCw size={14}/>Refresh insights</button>}
  </PageContainer>;
}
