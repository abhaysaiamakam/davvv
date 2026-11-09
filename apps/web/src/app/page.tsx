"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { Activity, ArrowRight, Clock3, Database, FileCheck2, Plus, RefreshCw, FileDown } from "lucide-react";
import type { DataQualityAssessment, DatasetListResponse, InsightCollectionResponse, JobListResponse, ReportListResponse } from "@croplens/shared-types";
import { apiClient } from "@/lib/api-client";
import { PageContainer } from "@/components/layout/page-container";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function OverviewPage() {
  const [datasets, setDatasets] = useState<DatasetListResponse | null>(null);
  const [jobs, setJobs] = useState<JobListResponse | null>(null);
  const [quality, setQuality] = useState<DataQualityAssessment | null>(null);
  const [insights, setInsights] = useState<InsightCollectionResponse | null>(null);
  const [reports, setReports] = useState<ReportListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    const [ds, jobList] = await Promise.allSettled([apiClient.getDatasets(), apiClient.listJobs()]);
    if (ds.status === "fulfilled") setDatasets(ds.value); else setError(ds.reason instanceof Error ? ds.reason.message : "Dataset registry unavailable");
    if (jobList.status === "fulfilled") setJobs(jobList.value); else setJobs(null);
    setLoading(false);
  }, []);
  useEffect(() => { void load(); }, [load]);
  const firstDatasetId = datasets?.items[0]?.id;
  useEffect(() => {
    if (!firstDatasetId) return;
    let active = true;
    void Promise.allSettled([apiClient.getQuality(firstDatasetId), apiClient.getInsights(firstDatasetId), apiClient.getReports(firstDatasetId)]).then(([qualityResult, insightResult, reportResult]) => {
      if (!active) return;
      setQuality(qualityResult.status === "fulfilled" ? qualityResult.value : null);
      setInsights(insightResult.status === "fulfilled" ? insightResult.value : null);
      setReports(reportResult.status === "fulfilled" ? reportResult.value : null);
    });
    return () => { active = false; };
  }, [firstDatasetId]);
  const activeJobs = (jobs?.items ?? []).filter((job) => ["queued", "validating", "processing"].includes(job.status));
  const validated = (datasets?.items ?? []).filter((dataset) => dataset.status === "validated").length;
  return <PageContainer title="Good morning" description="A clear view of your datasets, analysis activity, and the next step in your workflow." actions={<div className="flex items-center gap-2"><Link href="/exports" className="inline-flex h-10 items-center gap-2 rounded-lg border border-croplens-border bg-white px-4 text-sm font-semibold text-emerald-800 hover:bg-emerald-50"><FileDown size={16}/>Export Center</Link><Link href="/analyze" className="inline-flex h-10 items-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-800"><Plus size={16}/>Upload dataset</Link></div>}>
    {error && <ErrorState title="Dashboard data unavailable" message={error} onRetry={() => void load()}/>}
    {loading ? <LoadingState label="Loading live workspace data…" rows={4}/> : <>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Workspace summary">
        <Metric icon={<Database size={17}/>} label="Datasets" value={datasets?.total ?? "—"} detail="Registered in this workspace"/>
        <Metric icon={<FileCheck2 size={17}/>} label="Validated" value={datasets ? validated : "—"} detail="Completed image validation"/>
        <Metric icon={<Activity size={17}/>} label="Active jobs" value={jobs ? activeJobs.length : "—"} detail={jobs ? `${jobs.total} total jobs recorded` : "Job service unavailable"}/>
        <Metric icon={<Clock3 size={17}/>} label="Registry status" value={datasets ? datasets.is_placeholder ? "Catalog" : "Live" : "—"} detail={datasets?.note ?? "Synced from CropLens API"}/>
      </section>
      <section className="grid gap-5 xl:grid-cols-[1.55fr_1fr]">
        <DashboardCard title="Your datasets" description="Current registry records from the backend." icon={<Database size={17}/>} headerAction={<Link href="/datasets" className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 hover:text-emerald-900">View all <ArrowRight size={14}/></Link>}>
          {datasets?.items.length ? <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead><tr className="border-b border-croplens-border text-[11px] uppercase tracking-wide text-zinc-400"><th className="pb-3 font-medium">Dataset</th><th className="pb-3 font-medium">Crops</th><th className="pb-3 font-medium">Images</th><th className="pb-3 font-medium">Status</th></tr></thead><tbody className="divide-y divide-croplens-border">{datasets.items.slice(0, 6).map((dataset) => <tr key={dataset.id} className="group"><td className="py-3"><Link href={`/datasets?dataset=${encodeURIComponent(dataset.id)}`} className="font-medium text-zinc-100 hover:text-emerald-800">{dataset.name}</Link><p className="mt-0.5 text-xs text-zinc-400">{dataset.id}</p></td><td className="py-3 text-xs text-zinc-400">{dataset.crops.length ? dataset.crops.join(", ") : "—"}</td><td className="py-3 tabular-nums text-zinc-400">{dataset.total_images ?? "—"}</td><td className="py-3"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium capitalize text-gray-600">{dataset.status.replaceAll("_", " ")}</span></td></tr>)}</tbody></table></div> : <Empty message="No datasets are registered yet."/>}
        </DashboardCard>
        <DashboardCard title="Background activity" description="Upload and analysis jobs reported by the API." icon={<Activity size={17}/>} headerAction={<Link href="/jobs" className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 hover:text-emerald-900">Job center <ArrowRight size={14}/></Link>}>
          {activeJobs.length ? <div className="space-y-3">{activeJobs.slice(0, 5).map((job) => <Link key={job.job_id} href={`/jobs?job=${encodeURIComponent(job.job_id)}`} className="block rounded-lg border border-croplens-border p-3 transition hover:bg-gray-50"><div className="flex items-center justify-between gap-3"><span className="truncate text-sm font-medium text-zinc-100">{job.dataset_id}</span><span className="rounded-full bg-amber-50 px-2 py-1 text-[10px] font-semibold capitalize text-amber-800">{job.status}</span></div><div className="mt-2 flex items-center justify-between text-[11px] text-zinc-400"><span className="capitalize">{job.current_stage.replaceAll("_", " ")}</span><span>{job.progress_pct}%</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-emerald-600 transition-all" style={{ width: `${Math.max(0, Math.min(100, job.progress_pct))}%` }}/></div></Link>)}</div> : <Empty message={jobs ? "No jobs are currently running." : "Job history is unavailable while the API cannot be reached."}/>}
        </DashboardCard>
      </section>
      <section className="grid gap-5 lg:grid-cols-3">
        <DashboardCard title="Latest quality result" icon={<FileCheck2 size={17}/>} description={quality ? quality.dataset_name : "Available when a quality assessment exists for the first dataset in the registry."}>
          {quality ? <><div className="flex items-baseline gap-2"><span className="text-3xl font-semibold text-zinc-100">{quality.quality_score.overall_score.toFixed(1)}</span><span className="text-xs capitalize text-emerald-800">{quality.quality_score.quality_tier}</span></div><p className="mt-2 text-xs text-zinc-400">{quality.findings.length} findings · {quality.quality_score.is_complete ? "complete assessment" : "partial evidence"}</p></> : <p className="text-xs text-zinc-400">No quality artifact returned.</p>}
        </DashboardCard>
        <DashboardCard title="Recent insights" icon={<Activity size={17}/>} description={insights ? `${insights.dataset_version} · backend collection` : "Evidence-backed results from the insight engine."}>
          {insights?.items.length ? <div className="space-y-3">{insights.items.slice(0,3).map(item=><div key={item.insight_id}><p className="text-xs font-semibold text-zinc-100">{item.title}</p><p className="mt-1 line-clamp-2 text-[11px] text-zinc-400">{item.summary}</p></div>)}</div> : <p className="text-xs text-zinc-400">No insight collection returned.</p>}
        </DashboardCard>
        <DashboardCard title="Reports" icon={<FileCheck2 size={17}/>} description="Latest report artifacts for the first dataset in the registry.">
          {reports?.items.length ? <div className="space-y-2">{reports.items.slice(0,3).map(report=><div key={report.report_id} className="rounded-lg bg-gray-50 p-2.5"><p className="text-xs font-medium text-zinc-100">{report.title}</p><p className="mt-1 text-[10px] text-zinc-400">{report.dataset_overview.version_id} · {report.readiness_section.overall_status.replaceAll("_"," ")}</p></div>)}</div> : <p className="text-xs text-zinc-400">No report history returned.</p>}
        </DashboardCard>
      </section>
      <section className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-5 sm:p-6"><div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-emerald-800">Continue your workflow</p><h2 className="mt-1 text-lg font-semibold text-zinc-100">From raw files to defensible findings</h2><p className="mt-1 max-w-2xl text-sm text-zinc-400">Upload a dataset, run the backend analysis, and explore quality, visualizations, insights, and readiness tied to the resulting version.</p></div><Link href="/analyze" className="inline-flex shrink-0 items-center gap-2 self-start rounded-lg border border-emerald-200 bg-white px-4 py-2.5 text-sm font-semibold text-emerald-800 hover:bg-emerald-50 sm:self-auto">Start with upload <ArrowRight size={15}/></Link></div></section>
    </>}
  </PageContainer>;
}

function Metric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string | number; detail: string }) {
  return <div className="rounded-xl border border-croplens-border bg-white p-4 shadow-[0_1px_2px_rgba(20,35,24,.03)]"><div className="flex items-center justify-between"><span className="text-xs font-medium text-zinc-400">{label}</span><span className="text-emerald-800">{icon}</span></div><p className="mt-3 text-2xl font-semibold tracking-tight text-zinc-100">{value}</p><p className="mt-1 truncate text-[11px] text-zinc-400" title={detail}>{detail}</p></div>;
}
function Empty({ message }: { message: string }) { return <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed border-croplens-border px-4 text-center"><RefreshCw size={18} className="mb-2 text-gray-400"/><p className="text-sm text-zinc-400">{message}</p></div>; }
