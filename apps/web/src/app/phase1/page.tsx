"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, BarChart3, BookOpen, Check, ChevronLeft, ChevronRight, Code2, Download, FileImage, FlaskConical, Images, LoaderCircle, Play, Presentation, RefreshCw, ShieldCheck, Upload } from "lucide-react";
import type { AvailableFeaturesResponse, AvailableOperationsResponse, DataQualityAssessment, DatasetImage, DatasetImageListResponse, DuplicateAnalysisResult, EdaReport, FeaturePreviewResponse, InsightCollectionResponse, PreprocessingOperationConfig, PreprocessingPreviewResponse, VisualizationCollectionResponse } from "@croplens/shared-types";
import { CodeLensExplainability } from "@/components/ui/codelens";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { ErrorState } from "@/components/ui/error-state";
import { EvidenceImageGrid } from "@/components/evidence/evidence-image-grid";
import { PageContainer } from "@/components/layout/page-container";
import { WorkspaceDatasetSelect } from "@/components/ui/workspace-dataset-select";
import { WorkspaceVersionSelect } from "@/components/ui/workspace-version-select";
import { VisualizationChart } from "@/components/ui/visualization-chart";
import { useDatasetContext } from "@/hooks/use-dataset-context";
import { useDatasetVersion } from "@/hooks/use-dataset-version";
import { apiClient, ApiClientError } from "@/lib/api-client";

type WorkspaceTab = "overview" | "eda" | "quality" | "gallery" | "preprocessing" | "features" | "insights" | "code";
const PAGE_SIZE = 24;
const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;
const TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "overview", label: "Overview" }, { id: "eda", label: "EDA" }, { id: "quality", label: "Quality" },
  { id: "gallery", label: "Images" }, { id: "preprocessing", label: "Preprocessing" }, { id: "features", label: "Features & PCA" },
  { id: "insights", label: "Insights" }, { id: "code", label: "Python code" },
];

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return String(value);
}

function errorText(reason: unknown): string { return reason instanceof Error ? reason.message : "The CropLens API could not return this result."; }

export default function Phase1SubmissionPage() {
  const context = useDatasetContext();
  const version = useDatasetVersion(context.selectedId, context.selected?.current_version_id);
  const fileInput = useRef<HTMLInputElement>(null);
  const loadRequestId = useRef(0);
  const [tab, setTab] = useState<WorkspaceTab>("overview");
  const [presentation, setPresentation] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [codeView, setCodeView] = useState<"raw" | "commented" | "explanation">("commented");
  const [pythonCode, setPythonCode] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("ICAR Rice and Maize Disease Dataset");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [artifactErrors, setArtifactErrors] = useState<string[]>([]);
  const [refreshCounter, setRefreshCounter] = useState(0);
  const [images, setImages] = useState<DatasetImageListResponse | null>(null);
  const [quality, setQuality] = useState<DataQualityAssessment | null>(null);
  const [eda, setEda] = useState<EdaReport | null>(null);
  const [charts, setCharts] = useState<VisualizationCollectionResponse | null>(null);
  const [insights, setInsights] = useState<InsightCollectionResponse | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateAnalysisResult | null>(null);
  const [preprocessing, setPreprocessing] = useState<AvailableOperationsResponse | null>(null);
  const [features, setFeatures] = useState<AvailableFeaturesResponse | null>(null);
  const [galleryPage, setGalleryPage] = useState(1);
  const [cropFilter, setCropFilter] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [imageSearch, setImageSearch] = useState("");
  const [operationType, setOperationType] = useState("");
  const [operationParameters, setOperationParameters] = useState("{}");
  const [targetColumns, setTargetColumns] = useState("");
  const [preview, setPreview] = useState<PreprocessingPreviewResponse | FeaturePreviewResponse | null>(null);
  const [lastDerived, setLastDerived] = useState<{ version: string; job: string } | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/phase1-image-analysis.py").then(response => response.ok ? response.text() : "").then(text => { if (active) setPythonCode(text); }).catch(() => { if (active) setPythonCode(""); });
    return () => { active = false; };
  }, []);

  const load = useCallback(async () => {
    const requestId = ++loadRequestId.current;
    if (!context.selectedId || !version.versionId) {
      setImages(null); setQuality(null); setEda(null); setCharts(null); setInsights(null); setDuplicates(null); setPreprocessing(null); setFeatures(null); setArtifactErrors([]); return;
    }
    const datasetId = context.selectedId;
    const versionId = version.versionId;
    const [gallery, qualityResult, edaResult, chartResult, insightResult, duplicateResult, preprocessingResult, featureResult] = await Promise.allSettled([
      apiClient.getImages(datasetId, versionId, { page: galleryPage, page_size: PAGE_SIZE, crop: cropFilter, class_name: classFilter, search: imageSearch }),
      apiClient.getQuality(datasetId, versionId), apiClient.getEda(datasetId, versionId), apiClient.getVisualizations(datasetId, versionId),
      apiClient.getInsights(datasetId, versionId), apiClient.getDuplicates(datasetId, versionId),
      apiClient.getPreprocessingOperations(datasetId), apiClient.getAvailableFeatures(datasetId),
    ]);
    if (requestId !== loadRequestId.current) return;
    const results = [gallery, qualityResult, edaResult, chartResult, insightResult, duplicateResult, preprocessingResult, featureResult];
    const labels = ["Image gallery", "Quality", "EDA", "visualizations", "insights", "duplicate detection", "preprocessing registry", "feature registry"];
    setArtifactErrors(results.flatMap((result, index) => result.status === "rejected" && !(result.reason instanceof ApiClientError && result.reason.status === 404) ? [`${labels[index]}: ${errorText(result.reason)}`] : []));
    setImages(gallery.status === "fulfilled" ? gallery.value : null);
    setQuality(qualityResult.status === "fulfilled" && qualityResult.value.version_id === versionId ? qualityResult.value : null);
    setEda(edaResult.status === "fulfilled" && edaResult.value.version_id === versionId ? edaResult.value : null);
    setCharts(chartResult.status === "fulfilled" && chartResult.value.dataset_version === versionId ? chartResult.value : null);
    setInsights(insightResult.status === "fulfilled" && insightResult.value.dataset_version === versionId ? insightResult.value : null);
    setDuplicates(duplicateResult.status === "fulfilled" && duplicateResult.value.version_id === versionId ? duplicateResult.value : null);
    setPreprocessing(preprocessingResult.status === "fulfilled" ? preprocessingResult.value : null);
    setFeatures(featureResult.status === "fulfilled" ? featureResult.value : null);
  }, [context.selectedId, version.versionId, galleryPage, cropFilter, classFilter, imageSearch]);

  useEffect(() => { void load(); }, [load, refreshCounter]);
  useEffect(() => { setGalleryPage(1); setClassFilter(""); setPreview(null); setLastDerived(null); }, [context.selectedId, version.versionId, cropFilter, imageSearch]);

  const cropNames = useMemo(() => Array.from(new Set((images?.classes ?? []).map(item => item.class_name.split("/")[0]).filter(Boolean))).sort((a, b) => a.localeCompare(b)), [images?.classes]);
  const visibleClasses = useMemo(() => (images?.classes ?? []).filter(item => !cropFilter || item.class_name.toLocaleLowerCase().startsWith(`${cropFilter.toLocaleLowerCase()}/`)), [images?.classes, cropFilter]);
  const imageOperations = (preprocessing?.operations ?? []).filter(operation => operation.modality === "image");
  const featureOperations = (features?.operations ?? []).filter(operation => operation.modality === "image");
  const selectedOperation = [...imageOperations, ...featureOperations].find(operation => operation.operation_type === operationType);
  const isFeatureOperation = featureOperations.some(operation => operation.operation_type === operationType);
  const selectedName = `${context.selected?.id ?? ""} ${context.selected?.name ?? ""}`.toLocaleLowerCase();
  const selectedPhase1Dataset = selectedName.includes("rice") && selectedName.includes("maize");
  const validVersion = Boolean(context.selectedId && version.versionId && selectedPhase1Dataset);
  const activeVersion = version.versions.find(item => item.version_id === version.versionId);
  const imageCharts = (charts?.items ?? []).filter(item => ["class_distribution", "image_geometry", "format_and_color", "duplicates", "annotations"].includes(item.category));

  async function chooseArchive(file: File | undefined) {
    if (!file) return;
    setUploadError(null);
    if (!/\.(zip|tar|tar\.gz|tgz)$/i.test(file.name)) { setUploadFile(null); setUploadError("Choose a .zip, .tar, .tar.gz, or .tgz dataset archive."); return; }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadFile(file);
      setUploadError(`This archive is ${(file.size / (1024 * 1024)).toFixed(1)} MiB. The current documented CropLens API upload limit is 500 MiB; no supported large-upload mechanism is configured in this repository.`);
      return;
    }
    setUploadFile(file);
  }

  async function uploadArchive() {
    if (!uploadFile || uploadFile.size > MAX_UPLOAD_BYTES) return;
    setUploading(true); setUploadError(null); setUploadProgress(0);
    try {
      const response = await apiClient.uploadDataset(uploadFile, uploadName || undefined, undefined, setUploadProgress);
      const url = new URL(window.location.href); url.searchParams.set("dataset", response.dataset_id); window.history.replaceState(null, "", url);
      await context.reload();
      setActionError(`Upload registered as ${response.dataset_id}, version ${response.version_id}. Track job ${response.job_id} before relying on analysis results.`);
      setUploadFile(null);
    } catch (reason) { setUploadError(errorText(reason)); }
    finally { setUploading(false); }
  }

  async function runAnalysis() {
    if (!validVersion || busy) return;
    setBusy(true); setActionError(null);
    const failures: string[] = [];
    try { await apiClient.detectDuplicates(context.selectedId, version.versionId); }
    catch (reason) { failures.push(`Exact duplicate detection: ${errorText(reason)}`); }
    const [qualityResult, edaResult] = await Promise.allSettled([
      apiClient.assessQuality(context.selectedId, version.versionId),
      apiClient.runEda(context.selectedId, version.versionId),
    ]);
    if (qualityResult.status === "rejected") failures.push(`Quality: ${errorText(qualityResult.reason)}`);
    if (edaResult.status === "rejected") failures.push(`EDA: ${errorText(edaResult.reason)}`);
    try { await apiClient.regenerateInsights(context.selectedId, version.versionId); }
    catch (reason) { failures.push(`Insights: ${errorText(reason)}`); }
    setActionError(failures.length ? failures.join(" · ") : "Version-scoped Quality, EDA, exact duplicate detection, and Insights finished.");
    setRefreshCounter(value => value + 1);
    setBusy(false);
  }

  function makeOperation(): PreprocessingOperationConfig | null {
    if (!operationType || !selectedOperation) return null;
    let parameters: Record<string, unknown>;
    try { parameters = JSON.parse(operationParameters) as Record<string, unknown>; }
    catch { setActionError("Parameters must be valid JSON."); return null; }
    return { operation_type: operationType, modality: selectedOperation.modality, parameters, target_columns: targetColumns.split(",").map(value => value.trim()).filter(Boolean) };
  }

  async function runPreview() {
    const operation = makeOperation();
    if (!operation || !validVersion) return;
    setBusy(true); setActionError(null); setPreview(null);
    try {
      const result = isFeatureOperation
        ? await apiClient.previewFeatures(context.selectedId, version.versionId, [operation])
        : await apiClient.previewPreprocessing(context.selectedId, version.versionId, [operation]);
      setPreview(result);
    } catch (reason) { setActionError(errorText(reason)); }
    finally { setBusy(false); }
  }

  async function applyOperation() {
    const operation = makeOperation();
    if (!operation || !validVersion || busy) return;
    setBusy(true); setActionError(null);
    try {
      const result = isFeatureOperation
        ? await apiClient.applyFeatures(context.selectedId, version.versionId, [operation], `Phase 1: ${selectedOperation?.display_name}`)
        : await apiClient.applyPreprocessing(context.selectedId, version.versionId, [operation], `Phase 1: ${selectedOperation?.display_name}`);
      setLastDerived({ version: result.derived_version_id, job: result.job_id });
      await version.reload();
      version.select(result.derived_version_id);
      setRefreshCounter(value => value + 1);
    } catch (reason) { setActionError(errorText(reason)); }
    finally { setBusy(false); }
  }

  const rawPythonCode = useMemo(() => pythonCode.split("\n").filter(line => !/^\s*#/.test(line)).join("\n"), [pythonCode]);
  const metricTiles = eda ? [
    ["Valid images", eda.overview.total_valid_images], ["Classes", eda.overview.class_count], ["Formats", eda.overview.format_count], ["Image findings", eda.findings.length],
  ] : [];

  return <PageContainer title="ICAR Rice and Maize Disease Dataset" description="Phase 1 submission workspace · Complete analysis, evidence, versioned transformations, and presentation preparation." badge="Phase 2 presentation" actions={<div className="flex flex-wrap items-center gap-2"><button type="button" onClick={() => setShowUpload(value => !value)} aria-expanded={showUpload} className="inline-flex h-10 items-center gap-2 rounded-lg border border-croplens-border bg-white px-3 text-xs font-semibold text-zinc-700"><Upload size={15}/>Submit archive</button><button type="button" aria-pressed={presentation} onClick={() => { setPresentation(value => !value); if (!presentation && tab === "code") setTab("overview"); }} className={`inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-xs font-semibold ${presentation ? "border-emerald-700 bg-emerald-700 text-white" : "border-croplens-border bg-white text-zinc-700"}`}><Presentation size={15}/>{presentation ? "Exit presentation" : "Presentation mode"}</button><button type="button" onClick={() => void runAnalysis()} disabled={!validVersion || busy} className="inline-flex h-10 items-center gap-2 rounded-lg bg-emerald-700 px-3 text-xs font-semibold text-white disabled:opacity-50">{busy ? <LoaderCircle size={15} className="animate-spin"/> : <Play size={15}/>}Run version analysis</button></div>}>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-5">
        {context.error && <ErrorState title="Dataset registry unavailable" message={context.error} onRetry={() => void context.reload()}/>}
        {version.error && <ErrorState title="Version registry unavailable" message={version.error} onRetry={() => void version.reload()}/>}
        {actionError && <div role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-950">{actionError}</div>}
        {artifactErrors.length > 0 && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900"><p className="font-semibold">Some selected-version artifacts could not be loaded</p>{artifactErrors.map((error, index) => <p key={`${index}-${error}`} className="mt-1">{error}</p>)}</div>}
        {!presentation && <nav className="flex gap-1 overflow-x-auto rounded-xl border border-croplens-border bg-white p-1" aria-label="Phase 1 workspace sections">{TABS.map(item => <button key={item.id} type="button" onClick={() => setTab(item.id)} aria-current={tab === item.id ? "page" : undefined} className={`shrink-0 rounded-lg px-3 py-2 text-xs font-medium ${tab === item.id ? "bg-emerald-700 text-white" : "text-zinc-600 hover:bg-gray-100"}`}>{item.label}</button>)}</nav>}
        {presentation && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-950"><strong>Presentation sequence:</strong> Overview → EDA → Quality → Preprocessing → Feature engineering/PCA → Insights → Conclusions. Evidence and values below are read from the selected version’s CropLens artifacts.</div>}
        {(!validVersion || showUpload) && !context.loading && <DashboardCard title="Select or submit the Phase 1 dataset" icon={<Upload size={17}/>} description="Choose an existing dataset and exact version, or submit an archive within the documented CropLens limit.">
          {context.selected && !selectedPhase1Dataset && <p className="mb-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-950">The selected registry record is not identified as the Rice and Maize submission. Choose the Phase 1 dataset record or upload its archive before showing analysis here.</p>}
          <div className="grid gap-2 sm:grid-cols-2"><WorkspaceDatasetSelect datasets={context.datasets} value={context.selectedId} onChange={context.select} loading={context.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={version.select} loading={version.loading}/></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]"><label className="text-xs font-medium text-zinc-600">Archive<input ref={fileInput} type="file" accept=".zip,.tar,.gz,.tgz" className="mt-1 block w-full text-xs" onChange={event => void chooseArchive(event.target.files?.[0])}/></label><button onClick={() => void uploadArchive()} disabled={!uploadFile || uploading || uploadFile.size > MAX_UPLOAD_BYTES} className="self-end rounded-lg bg-emerald-700 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">{uploading ? `Uploading ${uploadProgress ?? 0}%` : "Upload archive"}</button></div>
          <label className="mt-2 block text-xs text-zinc-600">Dataset name<input value={uploadName} onChange={event => setUploadName(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border px-3"/></label>
          {uploadError && <p role="alert" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">{uploadError}</p>}
          <p className="mt-3 text-[11px] leading-relaxed text-zinc-500">Maximum upload size: 500 MiB. CropLens has no resumable or large-archive upload endpoint configured here; oversized archives are blocked before transfer. Original archives are not split or modified.</p>
        </DashboardCard>}

        {validVersion && (presentation || tab === "overview") && <section id="overview" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-croplens-border bg-white p-4"><div><p className="text-sm font-semibold text-zinc-900">{context.selected?.name ?? context.selectedId}</p><p className="mt-1 font-mono text-[11px] text-zinc-500">Dataset {context.selectedId} · Version {version.versionId}</p></div><div className="flex items-center gap-2"><WorkspaceDatasetSelect datasets={context.datasets} value={context.selectedId} onChange={context.select} loading={context.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={version.select} loading={version.loading}/><button aria-label="Refresh selected version artifacts" onClick={() => setRefreshCounter(value => value + 1)} className="rounded-lg border border-croplens-border p-2"><RefreshCw size={15}/></button></div></div>
          {eda?.version_id === version.versionId ? <><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metricTiles.map(([label, value]) => <div key={String(label)} className="rounded-xl border border-croplens-border bg-white p-4"><p className="text-xs text-zinc-500">{label}</p><p className="mt-2 text-2xl font-semibold text-zinc-900">{show(value)}</p></div>)}</div><p className="text-[11px] text-zinc-500">Values are from EDA report {eda.id}; method {eda.methodology_version}. Dataset version {eda.version_id}.</p></> : <div className="rounded-xl border border-dashed border-croplens-border bg-white p-6 text-sm text-zinc-500">No EDA report exists for this exact version yet. Run version analysis after the dataset job finishes.</div>}
          {eda?.class_distribution && <DashboardCard title="Observed directory classes" icon={<BarChart3 size={17}/>} description="Counts and shares are computed from the selected version. Directory labels reflect the archive structure; they do not estimate field prevalence."><div className="space-y-2">{eda.class_distribution.distribution.map(item => <div key={item.class_name} className="grid grid-cols-[minmax(0,1fr)_minmax(100px,2fr)_70px] items-center gap-2 text-xs"><span className="truncate" title={item.class_name}>{item.class_name}</span><div className="h-2 overflow-hidden rounded bg-gray-100"><div className="h-full bg-emerald-600" style={{ width: `${Math.max(0, Math.min(100, item.percentage_of_valid))}%` }}/></div><span className="text-right tabular-nums">{show(item.valid_image_count)} · {show(item.percentage_of_valid)}%</span></div>)}</div></DashboardCard>}
          {imageCharts.length > 0 && <div className="grid gap-4 lg:grid-cols-2">{imageCharts.slice(0, 4).map(spec => <DashboardCard key={spec.visualization_id} title={spec.title} icon={<BarChart3 size={17}/>} description={spec.description}><VisualizationChart spec={spec}/><p className="mt-3 border-t border-croplens-border pt-2 text-[10px] text-zinc-500">Bound to version {spec.dataset_version}</p></DashboardCard>)}</div>}
          <DashboardCard title="What can be concluded" icon={<BookOpen size={17}/>}><p className="text-xs leading-relaxed text-zinc-600">The class chart describes this submitted collection only. It does not establish disease prevalence in agriculture. For claims, use findings below with their source artifact, metric, affected files, and stated limitations.</p></DashboardCard>
        </section>}

          {validVersion && (presentation || tab === "eda") && <section id="eda" className="space-y-4"><DashboardCard title="Exploratory data analysis" icon={<BarChart3 size={17}/>} description="Charts and summary metrics are displayed only when returned for the selected immutable version.">{eda?.version_id === version.versionId ? <><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[["Discovered", eda.overview.total_discovered_files], ["Valid images", eda.overview.total_valid_images], ["Classes", eda.overview.class_count], ["Unique dimensions", eda.overview.unique_dimension_count]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-gray-50 p-3"><p className="text-[11px] text-zinc-500">{label}</p><p className="mt-1 text-lg font-semibold text-zinc-900">{show(value)}</p></div>)}</div><div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-gray-50 p-3"><p className="text-xs font-semibold">Image dimensions</p><p className="mt-1 text-xs">{show(eda.dimension_analysis?.min_width)}–{show(eda.dimension_analysis?.max_width)} px wide · {show(eda.dimension_analysis?.min_height)}–{show(eda.dimension_analysis?.max_height)} px high</p></div><div className="rounded-lg bg-gray-50 p-3"><p className="text-xs font-semibold">Image file size</p><p className="mt-1 text-xs">Mean {show(eda.file_size_analysis?.mean_human)} · Median {show(eda.file_size_analysis?.median_bytes)} bytes · Total {show(eda.file_size_analysis?.total_human)}</p></div></div><p className="mt-3 text-xs text-zinc-500">Formats: {Object.entries(eda.format_analysis?.format_distribution ?? {}).map(([format, count]) => `${format} ${show(count)}`).join(" · ") || "Not available"}. Dimensions shown from validated image metadata.</p></> : <p className="text-xs text-zinc-500">No selected-version EDA report is available. Run analysis to compute it.</p>}</DashboardCard>
          {imageCharts.map(spec => <DashboardCard key={spec.visualization_id} title={spec.title} icon={<BarChart3 size={17}/>} description={spec.description}><VisualizationChart spec={spec}/></DashboardCard>)}
          {eda?.findings.map(finding => <DashboardCard key={finding.id} title={finding.title} badge={{ text: finding.severity, variant: finding.severity === "high" || finding.severity === "critical" ? "amber" : "neutral" }}><p className="text-xs leading-relaxed">{finding.explanation}</p><p className="mt-2 text-xs">{finding.metric_name}: <strong>{show(finding.observed_value)}</strong> {finding.expected_value !== null ? `· expected ${show(finding.expected_value)}` : ""}</p>{finding.affected_image_samples.length > 0 && <EvidenceImageGrid datasetId={context.selectedId} versionId={version.versionId} images={finding.affected_image_samples.map(path => ({ relativePath: path, label: finding.title, className: finding.affected_classes.join(", ") }))}/>}</DashboardCard>)}</section>}

        {validVersion && (presentation || tab === "quality") && <section id="quality" className="space-y-4"><DashboardCard title="Image quality assessment" icon={<ShieldCheck size={17}/>} description="Integrity, metadata and duplicate metrics are version-specific; unavailable evidence is not treated as a clean result.">{quality?.version_id === version.versionId ? <><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[["Integrity", quality.integrity.integrity_rate], ["Unreadable", quality.integrity.total_unreadable_images], ["Exact duplicate groups", quality.duplicate_impact.exact_duplicate_groups], ["Quality score", quality.quality_score.overall_score]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-gray-50 p-3"><p className="text-[11px] text-zinc-500">{label}</p><p className="mt-1 text-lg font-semibold text-zinc-900">{value == null ? "Not applicable / unavailable" : show(label === "Integrity" ? `${value}%` : value)}</p></div>)}</div><p className="mt-3 text-xs leading-relaxed text-zinc-600">{quality.summary}</p><p className="mt-1 text-[10px] text-zinc-500">Assessment {quality.id} · version {quality.version_id} · {quality.quality_score.quality_tier}{quality.quality_score.is_complete ? " · complete inputs" : " · incomplete inputs"}</p></> : <p className="text-xs text-zinc-500">No Quality assessment for this version. Run version analysis.</p>}</DashboardCard>
          {duplicates?.version_id === version.versionId && <DashboardCard title="Exact duplicate evidence" icon={<FileImage size={17}/>} description="SHA-256 byte-identical image groups, not visually similar images."><p className="text-xs">{show(duplicates.successfully_hashed_images)} / {show(duplicates.total_eligible_images)} images hashed · {show(duplicates.hashing_failures)} failures · {show(duplicates.exact_duplicate_groups)} duplicate groups.</p>{duplicates.hashing_failures > 0 && <p role="alert" className="mt-2 flex items-center gap-2 text-xs text-amber-800"><AlertTriangle size={14}/>This is a partial scan and cannot support a zero-duplicates conclusion.</p>}{duplicates.warnings.map((warning, index) => <p key={index} className="mt-2 text-[11px] text-amber-800">{warning}</p>)}{duplicates.groups.map(group => <div key={group.group_id} className="mt-3 rounded-lg border border-croplens-border p-3"><p className="text-xs font-semibold">Group {group.group_id} · {group.image_count} members{group.is_cross_class ? " · cross-class" : ""}</p><p className="mt-1 text-[11px] text-zinc-500">{group.classes_involved.join(" · ")}</p><ul className="mt-2 list-inside list-disc break-all text-[10px] text-zinc-600">{[group.representative, ...group.duplicates].map(member => <li key={member.relative_path}>{member.relative_path}{member.is_representative ? " (representative)" : ""}</li>)}</ul><EvidenceImageGrid datasetId={context.selectedId} versionId={version.versionId} images={[group.representative, ...group.duplicates].map(member => ({ relativePath: member.relative_path, label: member.is_representative ? "Exact duplicate representative" : "Exact duplicate", className: member.class_name, fileSizeBytes: member.file_size_bytes }))}/></div>)}</DashboardCard>}
          {(quality?.findings ?? []).map(finding => <DashboardCard key={finding.id} title={finding.title} badge={{ text: finding.severity, variant: finding.severity === "high" || finding.severity === "critical" ? "amber" : "neutral" }}><p className="text-xs leading-relaxed">{finding.explanation}</p><p className="mt-2 text-xs">{finding.metric_name}: <strong>{show(finding.observed_value)}</strong></p>{finding.affected_image_samples.length > 0 && <EvidenceImageGrid datasetId={context.selectedId} versionId={version.versionId} images={finding.affected_image_samples.map(path => ({ relativePath: path, label: finding.title, className: finding.affected_classes.join(", ") }))}/>}</DashboardCard>)}</section>}

        {validVersion && (presentation || tab === "gallery") && <section id="gallery" className="space-y-4"><DashboardCard title="Image gallery" icon={<Images size={17}/>} description="Paginated from the selected version. Thumbnails load on demand; source files are not all sent to the browser."><div className="grid gap-2 sm:grid-cols-3"><label className="text-[11px] text-zinc-600">Crop hierarchy<select value={cropFilter} onChange={event => setCropFilter(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border bg-white px-2"><option value="">All crops</option>{cropNames.map(name => <option key={name}>{name}</option>)}</select></label><label className="text-[11px] text-zinc-600">Disease / class<select value={classFilter} onChange={event => setClassFilter(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border bg-white px-2"><option value="">All classes</option>{visibleClasses.map(item => <option key={item.class_name} value={item.class_name}>{item.class_name} ({item.image_count})</option>)}</select></label><label className="text-[11px] text-zinc-600">Search file<input value={imageSearch} onChange={event => setImageSearch(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border px-2" placeholder="Filename contains…"/></label></div>
          {images ? <><p className="mt-3 text-[11px] text-zinc-500">{show(images.total)} matching images · page {images.page} · class mapping {images.class_structure}</p><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{images.items.map(item => <ImageCard key={item.image_id} image={item} datasetId={context.selectedId} versionId={version.versionId}/>)}</div><div className="mt-4 flex items-center justify-between"><button onClick={() => setGalleryPage(page => Math.max(1, page - 1))} disabled={galleryPage <= 1} className="inline-flex items-center gap-1 rounded-lg border border-croplens-border px-3 py-2 text-xs disabled:opacity-40"><ChevronLeft size={14}/>Previous</button><span className="text-xs text-zinc-500">{galleryPage} / {Math.max(1, Math.ceil(images.total / PAGE_SIZE))}</span><button onClick={() => setGalleryPage(page => Math.min(Math.max(1, Math.ceil(images.total / PAGE_SIZE)), page + 1))} disabled={galleryPage >= Math.ceil(images.total / PAGE_SIZE)} className="inline-flex items-center gap-1 rounded-lg border border-croplens-border px-3 py-2 text-xs disabled:opacity-40">Next<ChevronRight size={14}/></button></div></> : <p className="mt-4 text-xs text-zinc-500">No image listing was returned for this version. The selected version may not contain supported images.</p>}</DashboardCard></section>}

        {validVersion && (presentation || tab === "preprocessing") && <section id="preprocessing" className="space-y-4"><DashboardCard title="Versioned preprocessing" icon={<FlaskConical size={17}/>} description="Preview changes against the selected source version. Applying creates a derived version and leaves the source version intact."><OperationForm operations={imageOperations} operationType={operationType} setOperationType={setOperationType} parameters={operationParameters} setParameters={setOperationParameters} targetColumns={targetColumns} setTargetColumns={setTargetColumns}/><div className="mt-3 flex flex-wrap gap-2"><button onClick={() => void runPreview()} disabled={!operationType || busy} className="rounded-lg border border-croplens-border px-3 py-2 text-xs font-semibold disabled:opacity-40">Preview against source</button><button onClick={() => void applyOperation()} disabled={!operationType || busy || !preview || !("can_apply" in preview ? preview.can_apply : false)} className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">Create derived version</button></div>
          {preview && <pre className="mt-3 max-h-72 overflow-auto rounded-lg bg-zinc-950 p-3 text-[10px] text-emerald-100">{JSON.stringify(preview, null, 2)}</pre>}{imageOperations.length === 0 && <p className="mt-3 text-xs text-zinc-500">The API did not report image preprocessing operations for this dataset version.</p>}{lastDerived && <p className="mt-3 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-950">Derived version {lastDerived.version} created; analysis job {lastDerived.job}. Source remains {version.versionId} until you select the derived version after reload.</p>}</DashboardCard><div className="flex flex-wrap gap-2 text-xs"><Link className="rounded-lg border border-croplens-border px-3 py-2" href="/preprocessing">Open full preprocessing workspace</Link><CodeLensExplainability explanationId="preprocess.duplicates" resultTitle="Preprocessing API behavior" datasetVersion={version.versionId}/></div></section>}

        {validVersion && (presentation || tab === "features") && <section id="features" className="space-y-4"><DashboardCard title="Feature engineering, selection and PCA" icon={<Activity size={17}/>} description="Only operations that the backend registry declares for image data are shown. PCA is meaningful only when an applicable numeric feature matrix exists."><OperationForm operations={featureOperations} operationType={operationType} setOperationType={setOperationType} parameters={operationParameters} setParameters={setOperationParameters} targetColumns={targetColumns} setTargetColumns={setTargetColumns}/><div className="mt-3 flex flex-wrap gap-2"><button onClick={() => void runPreview()} disabled={!operationType || !isFeatureOperation || busy} className="rounded-lg border border-croplens-border px-3 py-2 text-xs font-semibold disabled:opacity-40">Preview feature operation</button><button onClick={() => void applyOperation()} disabled={!operationType || !isFeatureOperation || busy || !(preview && "can_apply" in preview && preview.can_apply)} className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">Create feature version</button></div>
          {preview && "operations" in preview && preview.operations.map((result, index) => <div key={index} className="mt-3 rounded-lg border border-croplens-border p-3"><p className="text-xs font-semibold">{result.operation_type} · {result.status}</p><p className="mt-1 text-xs">Generated: {"generated_features" in result ? result.generated_features.join(", ") || "none" : "—"}</p>{"explained_variance_ratio" in result && result.explained_variance_ratio && <><p className="mt-1 text-xs">Explained variance: {result.explained_variance_ratio.map(value => `${(value * 100).toFixed(2)}%`).join(" · ")}</p><p className="mt-1 text-xs">Cumulative: {result.cumulative_explained_variance?.map(value => `${(value * 100).toFixed(2)}%`).join(" · ")}</p></>}</div>)}
          {featureOperations.length === 0 && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-950">No image-modality feature engineering or PCA operation is available in CropLens’s current feature registry for this dataset. The local Python script below computes a separate color-histogram PCA; it is explicitly not a production CropLens artifact or a disease classifier.</p>}{features?.current_features.map(feature => <p key={feature.feature_id} className="mt-2 text-xs text-zinc-600">{feature.feature_name} · {feature.feature_type} · {feature.description}</p>)}</DashboardCard><CodeLensExplainability explanationId="feature.pca" resultTitle="Production PCA operation" datasetVersion={version.versionId}/></section>}

        {validVersion && (presentation || tab === "insights") && <section id="insights" className="space-y-4"><DashboardCard title="Evidence-backed insights" icon={<Activity size={17}/>} description="Finding statements are tied to selected-version artifacts and source metrics.">{insights?.dataset_version === version.versionId ? insights.items.length ? insights.items.map(item => <article key={item.insight_id} className="border-b border-croplens-border py-4 last:border-0"><div className="flex flex-wrap gap-2 text-[10px]"><span className="rounded-full bg-gray-100 px-2 py-1">{item.category}</span><span className="rounded-full bg-amber-50 px-2 py-1">{item.severity} · {item.confidence} confidence</span></div><h3 className="mt-2 text-sm font-semibold text-zinc-900">{item.title}</h3><p className="mt-1 text-xs leading-relaxed text-zinc-600">{item.explanation}</p>{item.evidence.map((evidence, index) => <p key={index} className="mt-2 rounded bg-gray-50 p-2 text-[11px]">{evidence.metric}: <strong>{show(evidence.value)}{evidence.unit ? ` ${evidence.unit}` : ""}</strong> · {evidence.explanation}<span className="block text-[10px] text-zinc-500">Source {evidence.source_artifact} · {evidence.source_path}</span></p>)}<p className="mt-2 text-xs"><strong>Why it matters:</strong> {item.impact}</p><p className="mt-1 text-xs"><strong>Potential implication:</strong> {item.recommended_action}</p><p className="mt-1 text-[11px] text-zinc-500">Limitations: {item.limitations}</p>{item.affected_files.length > 0 && <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold">Supporting files ({item.affected_files.length})</summary><EvidenceImageGrid datasetId={context.selectedId} versionId={version.versionId} images={item.affected_files.slice(0, 12).map(path => ({ relativePath: path, label: item.title, className: item.affected_classes.join(", ") }))}/><ul className="mt-2 max-h-32 overflow-auto break-all text-[10px] text-zinc-500">{item.affected_files.map(path => <li key={path}>{path}</li>)}</ul></details>}</article>) : <p className="text-xs text-zinc-500">The selected-version insight service returned no findings.</p> : <p className="text-xs text-zinc-500">No insight collection is available for this version yet. Run version analysis to regenerate insights.</p>}</DashboardCard>
          <DashboardCard title="Presentation conclusion" icon={<BookOpen size={17}/>}><p className="text-xs leading-relaxed text-zinc-600">Use conclusions supported by the selected-version findings above. Do not interpret curated dataset class counts as real-world crop disease prevalence. State any incomplete scans, absent splits, or unsupported operations with the displayed evidence.</p></DashboardCard></section>}

        {!presentation && tab === "code" && <section id="code" className="space-y-4"><DashboardCard title="Python Analysis & Code Walkthrough" icon={<Code2 size={17}/>} description="This downloadable, executable local script independently inspects an original dataset ZIP. It is distinct from the CropLens backend services that power the artifacts above."><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex gap-1 rounded-lg bg-gray-100 p-1"><button onClick={() => setCodeView("raw")} aria-pressed={codeView === "raw"} className={`rounded-md px-3 py-1.5 text-xs ${codeView === "raw" ? "bg-white shadow" : ""}`}>Raw Python</button><button onClick={() => setCodeView("commented")} aria-pressed={codeView === "commented"} className={`rounded-md px-3 py-1.5 text-xs ${codeView === "commented" ? "bg-white shadow" : ""}`}>Commented Python</button><button onClick={() => setCodeView("explanation")} aria-pressed={codeView === "explanation"} className={`rounded-md px-3 py-1.5 text-xs ${codeView === "explanation" ? "bg-white shadow" : ""}`}>Code explanation</button></div><a href="/phase1-image-analysis.py" download="phase1-image-analysis.py" className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white"><Download size={14}/>Download .py</a></div><pre hidden={codeView === "explanation"} className="mt-3 max-h-[560px] overflow-auto rounded-lg bg-zinc-950 p-4 text-[11px] leading-relaxed text-emerald-100"><code>{codeView === "commented" ? pythonCode || "Loading executable analysis script…" : rawPythonCode}</code></pre><div className="mt-3 rounded-lg bg-gray-50 p-3 text-xs leading-relaxed text-zinc-600"><p className="font-semibold text-zinc-800">Walkthrough and expected artifacts</p><p className="mt-1">The script inventories archive entries, decodes supported images, records observed folder labels, split folders, dimensions, formats, modes, and file sizes; streams SHA-256 exact-duplicate detection; and computes two-component PCA over normalized RGB histograms. It writes dataset_inventory.json, image_inventory.csv, class_distribution.csv, exact_duplicates.csv, and color_histogram_pca.csv, plus scalable class_distribution.svg and color_histogram_pca.svg charts. The histogram PCA is coarse color evidence only. It does not claim classification improvement or disease separation.</p><p className="mt-2 font-mono">python phase1-image-analysis.py Rice_and_Maize_Dataset.zip --output analysis-output</p><p className="mt-2">Dependencies: Pillow and NumPy. SVG charts use only the Python standard library. The script preserves the archive and writes outputs to a separate directory. CropLens&apos;s production processing is described by CodeLens below.</p></div><div className="flex flex-wrap gap-2"><CodeLensExplainability explanationId="images.gallery" resultTitle="CropLens production image inventory" datasetVersion={version.versionId}/><CodeLensExplainability explanationId="quality.duplicates" resultTitle="CropLens production duplicate detection" datasetVersion={version.versionId}/><CodeLensExplainability explanationId="eda.class_distribution" resultTitle="CropLens production EDA" datasetVersion={version.versionId}/></div></DashboardCard></section>}
      </div>

      {!presentation && <aside className="space-y-4">
        <DashboardCard title="Dataset context" icon={<FileImage size={17}/>}><WorkspaceDatasetSelect datasets={context.datasets} value={context.selectedId} onChange={context.select} loading={context.loading}/><div className="mt-2"><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={version.select} loading={version.loading}/></div>{activeVersion && <p className="mt-2 text-[10px] text-zinc-500">Status {activeVersion.status} · {show(activeVersion.image_count)} images · {show(activeVersion.class_count)} classes</p>}</DashboardCard>
        <DashboardCard title="Analysis controls" icon={<Activity size={17}/>}><button onClick={() => void runAnalysis()} disabled={!validVersion || busy} className="w-full rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busy ? "Running…" : "Run analysis for this version"}</button><p className="mt-2 text-[10px] text-zinc-500">Runs Quality, EDA, exact duplicate detection, and Insights through existing version-aware APIs.</p></DashboardCard>
        <DashboardCard title="Presentation sequence" icon={<Presentation size={17}/>}><ol className="list-inside list-decimal space-y-2 text-xs text-zinc-600">{["Dataset overview", "Exploratory analysis", "Data quality", "Preprocessing", "Feature engineering and PCA", "Evidence-backed insights", "Conclusions"].map((label, index) => <li key={label}><button onClick={() => { setPresentation(true); document.getElementById(["overview", "eda", "quality", "preprocessing", "features", "insights", "insights"][index])?.scrollIntoView({ behavior: "smooth", block: "start" }); }} className="text-left hover:text-emerald-800">{label}</button></li>)}</ol></DashboardCard>
        <DashboardCard title="Source code roles" icon={<Code2 size={17}/>}><p className="text-xs leading-relaxed text-zinc-600"><strong>Python Analysis</strong> is a runnable local archive analysis script. <strong>CodeLens</strong> points to the production API algorithm and frontend rendering path. These are not represented as the same implementation.</p><div className="mt-3 flex flex-wrap gap-2 text-[10px]"><Link href="/quality" className="rounded border border-croplens-border px-2 py-1">Quality</Link><Link href="/eda" className="rounded border border-croplens-border px-2 py-1">EDA</Link><Link href="/preprocessing" className="rounded border border-croplens-border px-2 py-1">Preprocessing</Link><Link href="/features" className="rounded border border-croplens-border px-2 py-1">Features</Link></div></DashboardCard>
      </aside>}
    </div>
  </PageContainer>;
}

function ImageCard({ image, datasetId, versionId }: { image: DatasetImage; datasetId: string; versionId: string }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  return <figure className="overflow-hidden rounded-lg border border-croplens-border bg-white"><div className="relative aspect-[4/3] bg-zinc-100">{!failed ? <><Image src={apiClient.imageAssetUrl(image.thumbnail_url)} alt={`${image.class_name}: ${image.filename}`} fill sizes="(max-width: 640px) 100vw, 33vw" unoptimized loading="lazy" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} className={`object-contain transition-opacity ${loaded ? "opacity-100" : "opacity-0"}`}/>{!loaded && <div className="absolute inset-0 flex items-center justify-center text-xs text-zinc-500" role="status">Loading thumbnail…</div>}</> : <div className="flex h-full items-center justify-center p-5 text-xs text-zinc-500">Thumbnail unavailable for this version.</div>}</div><figcaption className="space-y-1 p-2.5 text-[10px]"><p className="font-semibold">{image.class_name}</p><p className="break-all text-zinc-500">{image.filename}</p><p>{image.width ?? "?"} × {image.height ?? "?"} · {image.format ?? "unknown format"} · {(image.file_size_bytes / 1024).toFixed(1)} KB · {image.color_mode ?? "mode unavailable"}</p><p className="text-zinc-500">{image.status} · {datasetId} / {versionId}</p></figcaption></figure>;
}

function OperationForm({ operations, operationType, setOperationType, parameters, setParameters, targetColumns, setTargetColumns }: { operations: Array<{ operation_type: string; display_name: string; description: string; known_limitations: string[]; parameters_schema: Record<string, unknown> }>; operationType: string; setOperationType: (value: string) => void; parameters: string; setParameters: (value: string) => void; targetColumns: string; setTargetColumns: (value: string) => void }) {
  return <div className="space-y-3"><label className="block text-xs font-medium text-zinc-700">Backend-supported operation<select value={operationType} onChange={event => { setOperationType(event.target.value); setParameters("{}"); }} className="mt-1 h-10 w-full rounded-lg border border-croplens-border bg-white px-3"> <option value="">Select an operation</option>{operations.map(operation => <option key={operation.operation_type} value={operation.operation_type}>{operation.display_name}</option>)}</select></label>{operations.find(item => item.operation_type === operationType) && <><p className="text-xs text-zinc-600">{operations.find(item => item.operation_type === operationType)?.description}</p><p className="text-[10px] text-amber-800">Limitations: {operations.find(item => item.operation_type === operationType)?.known_limitations.join(" · ") || "No limitations reported by the registry."}</p><label className="block text-xs text-zinc-600">Operation parameters (JSON)<textarea value={parameters} onChange={event => setParameters(event.target.value)} rows={4} spellCheck={false} className="mt-1 w-full rounded-lg border border-croplens-border p-2 font-mono text-[11px]"/></label><label className="block text-xs text-zinc-600">Target columns, if required<input value={targetColumns} onChange={event => setTargetColumns(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border px-2" placeholder="Comma-separated; leave empty if operation requires none"/></label></>}</div>;
}
