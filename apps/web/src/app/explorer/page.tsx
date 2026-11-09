"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ChevronLeft, ChevronRight, Images, LoaderCircle, Search, WandSparkles, X } from "lucide-react";
import type { DatasetImage, ImageAnnotationResponse, ImagePreviewOperation } from "@croplens/shared-types";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useDatasetContext } from "@/hooks/use-dataset-context";
import { useDatasetVersion } from "@/hooks/use-dataset-version";
import { WorkspaceDatasetSelect } from "@/components/ui/workspace-dataset-select";
import { WorkspaceVersionSelect } from "@/components/ui/workspace-version-select";
import { CodeLensExplainability } from "@/components/ui/codelens";
import { initialThumbnailState, shouldShowThumbnailFallback, thumbnailStateAfterEvent } from "@/lib/thumbnail-state.mjs";
import { ContextualExportAction } from "@/components/exports/contextual-export-action";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";

const PAGE_SIZE = 30;
type SortBy = "filename" | "file_size" | "width" | "height";
type PreviewMode = "resize_images" | "convert_format" | "convert_color_mode";

export default function VisualExplorerPage() {
  const context = useDatasetContext();
  const version = useDatasetVersion(context.selectedId, context.selected?.current_version_id);
  const [items, setItems] = useState<DatasetImage[]>([]);
  const [classes, setClasses] = useState<Array<{ class_name: string; image_count: number }>>([]);
  const [classStructure, setClassStructure] = useState<"directory" | "unclassified">("unclassified");
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [className, setClassName] = useState("");
  const [annotationClassId, setAnnotationClassId] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortBy>("filename");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DatasetImage | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("resize_images");
  const [previewValue, setPreviewValue] = useState("512");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [operationPreview, setOperationPreview] = useState<{ before: string; after: string; beforeMeta: Record<string, unknown>; afterMeta: Record<string, unknown> } | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [derivedJob, setDerivedJob] = useState<{ version: string; job: string } | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [annotationData, setAnnotationData] = useState<ImageAnnotationResponse | null>(null);
  const [annotationLoading, setAnnotationLoading] = useState(false);
  const [annotationError, setAnnotationError] = useState<string | null>(null);
  const [showAnnotations, setShowAnnotations] = useState(true);
  const listRequestId = useRef(0);
  const closeInspectorRef = useRef<HTMLButtonElement>(null);
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async () => {
    const requestId = ++listRequestId.current;
    if (!context.selectedId || !version.versionId) {
      setItems([]); setClasses([]); setTotal(0); setClassStructure("unclassified"); setLoading(false); return;
    }
    setLoading(true); setError(null);
    try {
      const result = await apiClient.getImages(context.selectedId, version.versionId, {
        page, page_size: PAGE_SIZE, class_name: className, annotation_class_id: annotationClassId, search, sort_by: sortBy,
      });
      if (requestId === listRequestId.current) { setItems(result.items); setClasses(result.classes); setTotal(result.total); setClassStructure(result.class_structure); }
    } catch (issue) {
      if (requestId === listRequestId.current) { setItems([]); setClasses([]); setTotal(0); setClassStructure("unclassified"); setError(issue instanceof Error ? issue.message : "Image listing failed."); }
    } finally { if (requestId === listRequestId.current) setLoading(false); }
  }, [context.selectedId, version.versionId, page, className, annotationClassId, search, sortBy]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setPage(1); setSelected(null); setOperationPreview(null); setDerivedJob(null); }, [context.selectedId, version.versionId, className, annotationClassId, search, sortBy]);
  useEffect(() => {
    setImageFailed(false); setOperationPreview(null); setPreviewError(null); setAnnotationData(null); setAnnotationError(null); setShowAnnotations(true);
    if (!selected || !context.selectedId || !version.versionId) return;
    let active = true;
    setAnnotationLoading(true);
    void apiClient.getImageAnnotations(context.selectedId, version.versionId, selected.image_id)
      .then(result => { if (active) setAnnotationData(result); })
      .catch(issue => { if (active) setAnnotationError(issue instanceof Error ? issue.message : "Annotations could not be loaded."); })
      .finally(() => { if (active) setAnnotationLoading(false); });
    return () => { active = false; };
  }, [selected, context.selectedId, version.versionId]);
  useEffect(() => {
    if (!selected) return;
    const previous = document.activeElement as HTMLElement | null;
    closeInspectorRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setSelected(null); return; }
      if (event.key !== "Tab") return;
      const dialog = document.querySelector<HTMLElement>('[aria-labelledby="image-inspector-title"]');
      const controls = dialog?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])');
      if (!controls?.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", keydown);
    return () => { window.removeEventListener("keydown", keydown); previous?.focus(); };
  }, [selected]);

  const previewOperation = useMemo<ImagePreviewOperation>(() => {
    if (previewMode === "resize_images") return { operation_type: previewMode, parameters: { max_dim: Math.max(16, Number(previewValue) || 512) } };
    if (previewMode === "convert_format") return { operation_type: previewMode, parameters: { target_format: previewValue || "webp" } };
    return { operation_type: previewMode, parameters: { target_mode: previewValue || "RGB" } };
  }, [previewMode, previewValue]);
  const annotationUnsafeOperation = !annotationData || annotationData.annotation_format !== "none" && previewMode !== "convert_color_mode";

  async function runPreview() {
    if (!selected || !context.selectedId || !version.versionId) return;
    setPreviewBusy(true); setPreviewError(null); setOperationPreview(null);
    try {
      const result = await apiClient.previewImagePreprocessing(context.selectedId, version.versionId, selected.image_id, previewOperation);
      setOperationPreview({ before: result.original_data_url, after: result.preview_data_url, beforeMeta: result.original_metadata, afterMeta: result.preview_metadata });
    } catch (issue) { setPreviewError(issue instanceof Error ? issue.message : "Preview could not be generated."); }
    finally { setPreviewBusy(false); }
  }

  async function createDerivedVersion() {
    if (!context.selectedId || !version.versionId) return;
    setApplyBusy(true); setPreviewError(null); setDerivedJob(null);
    try {
      const result = await apiClient.applyPreprocessing(context.selectedId, version.versionId, [{ ...previewOperation, modality: "image", target_columns: [] }], `Image ${previewMode.replaceAll("_", " ")}`);
      setDerivedJob({ version: result.derived_version_id, job: result.job_id });
      await version.reload();
    } catch (issue) { setPreviewError(issue instanceof Error ? issue.message : "Could not create a derived version."); }
    finally { setApplyBusy(false); }
  }

  return <PageContainer title="Visual Dataset Explorer" description="Inspect the real images, classes, and metadata in a specific uploaded dataset version." badge="Version scoped" actions={<div className="flex w-full flex-wrap items-center gap-2 sm:w-auto"><div className="grid min-w-0 flex-1 gap-2 sm:w-[30rem] sm:grid-cols-2"><WorkspaceDatasetSelect datasets={context.datasets} value={context.selectedId} onChange={context.select} loading={context.loading}/><WorkspaceVersionSelect versions={version.versions} value={version.versionId} onChange={version.select} loading={version.loading}/></div><ContextualExportAction type="dataset" versionId={version.versionId}/></div>}>
    {context.error && <ErrorState title="Dataset registry unavailable" message={context.error} onRetry={() => void context.reload()}/>}
    {version.error && <ErrorState title="Dataset versions unavailable" message={version.error} onRetry={() => void version.reload()}/>}
    {!context.loading && !context.selectedId && <EmptyState icon={<Images/>} title="No dataset selected" description="Upload an image dataset or select one from the dataset registry."/>}
    {context.selectedId && !version.loading && !version.versionId && <EmptyState icon={<Images/>} title="No dataset version available" description="This dataset has no stored version to explore yet."/>}
    {error && <ErrorState title="Could not load images" message={error} onRetry={() => void load()}/>}
    {loading ? <LoadingState label="Loading versioned image records…"/> : version.versionId && <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-croplens-border bg-white p-4">
        <div><p className="text-xs text-zinc-500">Images in selected view · image modality</p><p className="mt-1 text-2xl font-semibold text-zinc-900">{total.toLocaleString()}</p><p className="mt-1 text-[10px] text-zinc-500">{classStructure === "directory" ? "Classes discovered from directory structure" : "No directory class structure detected; images remain unclassified"}</p></div>
        <div className="flex flex-1 flex-wrap justify-end gap-2">
          <label className="relative min-w-48 flex-1 sm:max-w-64"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"/><input value={search} onChange={event => setSearch(event.target.value)} aria-label="Search filenames" placeholder="Search filename" className="h-10 w-full rounded-lg border border-croplens-border pl-9 pr-3 text-sm"/></label>
          <label className="flex items-center gap-2 rounded-lg border border-croplens-border px-3 text-xs text-zinc-600">Sort<select value={sortBy} onChange={event => setSortBy(event.target.value as SortBy)} className="h-10 bg-transparent font-medium text-zinc-900"><option value="filename">Filename</option><option value="file_size">File size</option><option value="width">Width</option><option value="height">Height</option></select></label>
        </div>
      </div>
      {annotationClassId && <p className="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-900">Showing images with annotation class ID {annotationClassId}. <button type="button" onClick={() => setAnnotationClassId("")} className="font-semibold underline">Clear annotation filter</button></p>}

      {classes.length > 0 && <DashboardCard title="Discovered class distribution" icon={<Images size={17}/>} headerAction={<CodeLensExplainability explanationId="images.gallery" resultTitle="Discovered image classes" datasetVersion={version.versionId} provenance={[["Images in selected view", total], ["Classes discovered", classes.length]]}/>} description={`Counts are generated from files in version ${version.versionId}. Select a class to filter the gallery.`}>
        <div className="space-y-2">{classes.map(item => {
          const width = Math.max(2, total ? (item.image_count / Math.max(...classes.map(c => c.image_count), 1)) * 100 : 2);
          return <button key={item.class_name} type="button" onClick={() => setClassName(className === item.class_name ? "" : item.class_name)} aria-pressed={className === item.class_name} className={`grid w-full grid-cols-[minmax(5rem,1fr)_3fr_3rem] items-center gap-3 rounded-md p-1 text-left text-xs ${className === item.class_name ? "bg-emerald-50" : "hover:bg-gray-50"}`}><span className="truncate font-medium text-zinc-800">{item.class_name}</span><span className="h-2 overflow-hidden rounded-full bg-gray-100"><span className="block h-full rounded-full bg-emerald-600" style={{ width: `${width}%` }}/></span><span className="text-right tabular-nums text-zinc-500">{item.image_count}</span></button>;
        })}</div>
        {className && <button type="button" onClick={() => setClassName("")} className="mt-3 text-xs font-medium text-emerald-800">Clear class filter</button>}
      </DashboardCard>}

      {!classes.length && !error && <EmptyState icon={<Images/>} title="No supported images in this version" description="This version contains no supported image files."/>}
      {items.length > 0 && <section aria-label="Image gallery" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{items.map(image => <button key={image.image_id} type="button" onClick={() => setSelected(image)} className="overflow-hidden rounded-xl border border-croplens-border bg-white text-left transition hover:border-emerald-300 hover:shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-600">
        <GalleryThumbnail src={image.status === "valid" ? apiClient.imageAssetUrl(image.thumbnail_url) : null} alt={`${image.filename}, ${image.class_name}`} status={image.status}/>
        <div className="p-2.5"><p className="truncate text-xs font-semibold text-zinc-900">{image.filename}</p><p className="mt-1 truncate text-[10px] text-zinc-500">{image.class_name}</p><p className="mt-1 text-[10px] text-zinc-400">{image.width && image.height ? `${image.width} × ${image.height} · ` : ""}{image.format ?? "Unknown format"}</p></div>
      </button>)}</section>}

      <div className="flex items-center justify-between gap-3"><p className="text-xs text-zinc-500">Page {page} of {maxPage} · {total.toLocaleString()} images</p><div className="flex gap-2"><button type="button" disabled={page <= 1 || loading} onClick={() => setPage(value => Math.max(1, value - 1))} aria-label="Previous page" className="inline-flex h-9 items-center gap-1 rounded-lg border border-croplens-border px-3 text-xs disabled:opacity-40"><ChevronLeft size={15}/>Previous</button><button type="button" disabled={page >= maxPage || loading} onClick={() => setPage(value => Math.min(maxPage, value + 1))} aria-label="Next page" className="inline-flex h-9 items-center gap-1 rounded-lg border border-croplens-border px-3 text-xs disabled:opacity-40">Next<ChevronRight size={15}/></button></div></div>
    </>}

    {selected && <div className="fixed inset-0 z-[70] flex justify-end bg-gray-950/40" onMouseDown={event => { if (event.target === event.currentTarget) setSelected(null); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="image-inspector-title" className="flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-croplens-border bg-white p-4"><div className="min-w-0"><h2 id="image-inspector-title" className="truncate text-base font-semibold text-zinc-900">{selected.filename}</h2><p className="mt-1 truncate text-xs text-zinc-500">{selected.class_name} · version {version.versionId}</p></div><button ref={closeInspectorRef} type="button" onClick={() => setSelected(null)} aria-label="Close image inspector" className="rounded-lg p-2 text-zinc-500 hover:bg-gray-100"><X size={18}/></button></header>
        <div className="space-y-5 p-4 sm:p-6"><div className="relative flex h-[55vh] min-h-60 w-full items-center justify-center overflow-hidden rounded-xl bg-gray-100">{imageFailed ? <div role="status" className="p-8 text-center text-sm text-zinc-500">This image could not be loaded. It may be missing or corrupted.</div> : <><Image src={apiClient.imageAssetUrl(selected.preview_url)} alt={selected.filename} fill sizes="(max-width: 640px) 100vw, 60vw" unoptimized className="object-contain" onError={() => setImageFailed(true)}/>{showAnnotations && annotationData?.annotation_count ? <svg aria-label={`${annotationData.annotation_count} annotations`} role="img" className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${annotationData.image_width ?? selected.width ?? 1} ${annotationData.image_height ?? selected.height ?? 1}`} preserveAspectRatio="xMidYMid meet">{annotationData.annotations.map((annotation,index)=><g key={annotation.annotation_id}><rect x={annotation.x} y={annotation.y} width={annotation.width} height={annotation.height} fill="none" stroke={overlayColor(index)} strokeWidth={Math.max(1, (annotationData.image_width ?? 640) / 320)} vectorEffect="non-scaling-stroke"/><text x={annotation.x} y={Math.max(12, annotation.y - 4)} fill={overlayColor(index)} stroke="#ffffff" strokeWidth="3" paintOrder="stroke" fontSize={Math.max(10, (annotationData.image_width ?? 640) / 36)}>{annotation.label ?? `Class ID ${annotation.class_id}`}{annotation.confidence !== null && annotation.confidence !== undefined ? ` · ${annotation.confidence.toFixed(2)}` : ""}</text></g>)}</svg> : null}</>}</div>
          <section className="rounded-lg border border-croplens-border p-3" aria-label="Image annotations"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-xs font-semibold text-zinc-900">Annotations</h3><p className="mt-1 text-[10px] text-zinc-500">{annotationLoading ? "Reading annotation source…" : annotationError ?? (annotationData ? `${annotationData.annotation_format.toUpperCase()} · ${annotationData.annotation_count} objects` : "No annotation record")}</p></div><div className="flex items-center gap-3">{annotationData?.annotation_format !== "none" && annotationData && <CodeLensExplainability explanationId="images.annotations" resultTitle="Image annotation evidence" datasetVersion={annotationData.version_id} provenance={[["Format", annotationData.annotation_format.toUpperCase()], ["Objects on this image", annotationData.annotation_count], ["Classes in version", annotationData.classes.length]]}/>}{annotationData?.annotation_count ? <label className="flex items-center gap-2 text-xs text-zinc-700"><input type="checkbox" checked={showAnnotations} onChange={event => setShowAnnotations(event.target.checked)} className="accent-emerald-700"/>Show overlays</label> : null}</div></div>
            {annotationData?.classes.length ? <div className="mt-3 flex flex-wrap gap-2">{annotationData.classes.map(item=><button key={item.class_id} type="button" onClick={() => { setAnnotationClassId(item.class_id); setClassName(""); setSelected(null); }} className="rounded-full bg-gray-100 px-2.5 py-1 text-[10px] text-zinc-700 hover:bg-emerald-50 hover:text-emerald-900">{item.label ?? `Class ID ${item.class_id}`} · {item.annotation_count} boxes / {item.image_count} images · show images</button>)}</div> : null}
            {annotationData?.annotations.length ? <details className="mt-3"><summary className="cursor-pointer text-[10px] font-semibold text-emerald-800">Inspect annotation coordinates</summary><ul className="mt-2 space-y-1">{annotationData.annotations.map(item=><li key={item.annotation_id} className="text-[10px] text-zinc-600">{item.label ?? `Class ID ${item.class_id}`} · x {item.x.toFixed(1)}, y {item.y.toFixed(1)}, w {item.width.toFixed(1)}, h {item.height.toFixed(1)} px{item.confidence !== null && item.confidence !== undefined ? ` · confidence ${item.confidence.toFixed(3)}` : ""}</li>)}</ul></details> : null}
          </section>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{[["Dimensions",selected.width && selected.height ? `${selected.width} × ${selected.height}` : "Unavailable"],["Format",selected.format ?? "Unavailable"],["Color mode",selected.color_mode ?? "Unavailable"],["File size",formatBytes(selected.file_size_bytes)]].map(([label,value])=><div key={label} className="rounded-lg bg-gray-50 p-3"><p className="text-[10px] text-zinc-500">{label}</p><p className="mt-1 text-xs font-semibold text-zinc-900">{value}</p></div>)}</div>
          <div className="rounded-xl border border-croplens-border p-4"><div className="flex items-center gap-2"><WandSparkles size={16} className="text-emerald-700"/><h3 className="text-sm font-semibold text-zinc-900">Image preprocessing preview</h3></div><p className="mt-1 text-xs text-zinc-500">The selected backend operation runs in an isolated copy. The original version remains unchanged.</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]"><label className="text-[10px] font-medium text-zinc-500">Operation<select value={previewMode} onChange={event => { const value = event.target.value as PreviewMode; setPreviewMode(value); setPreviewValue(value === "resize_images" ? "512" : value === "convert_format" ? "webp" : "RGB"); setOperationPreview(null); }} className="mt-1 h-9 w-full rounded-lg border border-croplens-border px-2 text-xs text-zinc-900"><option value="resize_images">Resize</option><option value="convert_format">Convert format</option><option value="convert_color_mode">Convert color mode</option></select></label><label className="text-[10px] font-medium text-zinc-500">{previewMode === "resize_images" ? "Maximum dimension (px)" : previewMode === "convert_format" ? "Target format" : "Target color mode"}{previewMode === "resize_images" ? <input type="number" min={16} max={4096} value={previewValue} onChange={event => setPreviewValue(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border px-2 text-xs"/> : <select value={previewValue} onChange={event => setPreviewValue(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-croplens-border px-2 text-xs text-zinc-900">{previewMode === "convert_format" ? <><option value="webp">WEBP</option><option value="jpeg">JPEG</option><option value="png">PNG</option></> : <><option value="RGB">RGB</option><option value="L">Grayscale</option><option value="RGBA">RGBA</option></>}</select>}</label><button type="button" disabled={previewBusy || annotationUnsafeOperation} onClick={() => void runPreview()} className="mt-auto inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-emerald-700 px-3 text-xs font-semibold text-white disabled:opacity-50">{previewBusy && <LoaderCircle size={14} className="animate-spin"/>}Preview</button></div>
            {annotationUnsafeOperation && <p className="mt-2 text-[11px] text-amber-800">This dataset has linked annotations. Resize and format conversion are disabled here because they would require synchronized annotation updates. Color conversion preserves image size and filename.</p>}
            {previewError && <p role="alert" className="mt-3 text-xs text-red-700">{previewError}</p>}
            {operationPreview && <><div className="mt-4 grid gap-3 sm:grid-cols-2">{[["Original",operationPreview.before,operationPreview.beforeMeta],["Operation preview",operationPreview.after,operationPreview.afterMeta]].map(([label,data,meta])=><div key={label as string}><p className="mb-1 text-xs font-semibold text-zinc-700">{label as string}</p><div className="relative h-44"><Image fill sizes="(max-width: 640px) 100vw, 50vw" unoptimized src={data as string} alt={`${label as string} result`} className="rounded-lg bg-gray-100 object-contain"/></div><p className="mt-1 text-[10px] text-zinc-500">{String((meta as Record<string,unknown>).width)} × {String((meta as Record<string,unknown>).height)} · {String((meta as Record<string,unknown>).format)}</p></div>)}</div><button type="button" disabled={applyBusy} onClick={() => void createDerivedVersion()} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg border border-emerald-700 px-3 text-xs font-semibold text-emerald-800 disabled:opacity-50">{applyBusy && <LoaderCircle size={14} className="animate-spin"/>}Create derived dataset version</button></>}
            {derivedJob && <div role="status" className="mt-3 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-900">Derived version {derivedJob.version} created. Processing job: <Link className="font-semibold underline" href={`/jobs?job=${encodeURIComponent(derivedJob.job)}`}>track job</Link>.</div>}
          </div>
        </div>
      </section>
    </div>}
  </PageContainer>;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function GalleryThumbnail({ src, alt, status }: { src: string | null; alt: string; status: string }) {
  const [state, setState] = useState<"loading" | "loaded" | "failed">(initialThumbnailState(Boolean(src)));
  useEffect(() => { setState(initialThumbnailState(Boolean(src))); }, [src]);
  return <div className="relative aspect-[4/3] bg-gray-100">
    {src && <Image src={src} alt={alt} fill sizes="(max-width: 640px) 50vw, (max-width: 1280px) 25vw, 20vw" unoptimized loading="lazy" onLoad={() => setState(thumbnailStateAfterEvent("load"))} onError={() => setState(thumbnailStateAfterEvent("error"))} className={`object-cover ${state === "failed" ? "hidden" : ""}`}/>}
    {(state === "loading" || shouldShowThumbnailFallback(state)) && <div role={shouldShowThumbnailFallback(state) ? "status" : undefined} className="absolute inset-0 flex flex-col items-center justify-center gap-1 p-2 text-center text-xs text-zinc-500">{state === "loading" ? <LoaderCircle size={18} className="animate-spin"/> : <Images size={18} />}{state === "loading" ? "Loading thumbnail…" : status === "valid" ? "Thumbnail unavailable" : status}</div>}
  </div>;
}

function overlayColor(index: number) {
  return `hsl(${(index * 137.508) % 360} 78% 38%)`;
}
