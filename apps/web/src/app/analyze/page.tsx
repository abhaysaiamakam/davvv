"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, Archive, ArrowRight, CheckCircle2, FileUp, HardDrive, LoaderCircle, ShieldCheck, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import type { DatasetUploadResponse } from "@croplens/shared-types";
import { PageContainer } from "@/components/layout/page-container";

const formats = [".zip", ".tar", ".tar.gz", ".tgz"];
export default function AnalyzeUploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<DatasetUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const choose = (candidate?: File) => {
    if (!candidate) return;
    const valid = formats.some((format) => candidate.name.toLowerCase().endsWith(format));
    if (!valid) { setError("Choose a .zip, .tar, .tar.gz, or .tgz archive."); return; }
    setFile(candidate); setError(null); setResult(null);
    setName((previous) => previous || candidate.name.replace(/\.(tar\.gz|tgz|zip|tar)$/i, "").replaceAll("_", " "));
  };
  async function upload() {
    if (!file) return;
    setBusy(true); setError(null); setProgress(0);
    try {
      const uploaded = await apiClient.uploadDataset(file, name || undefined, undefined, setProgress);
      setResult(uploaded);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Upload failed."); }
    finally { setBusy(false); }
  }
  return <PageContainer title="Add a dataset" description="Upload a dataset archive to create a version and start the backend analysis pipeline." badge="Secure ingestion">
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,.8fr)]">
      <section className="rounded-xl border border-croplens-border bg-white p-5 sm:p-7">
        <div className="mb-5"><h2 className="text-sm font-semibold text-zinc-100">Dataset archive</h2><p className="mt-1 text-xs text-zinc-400">Accepted: {formats.join(", ")}. The backend validates and safely extracts archive contents.</p></div>
        {result ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5"><div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 text-emerald-700"/><div className="min-w-0 flex-1"><h3 className="text-sm font-semibold text-emerald-950">Upload accepted</h3><p className="mt-1 text-xs text-emerald-900">{result.message}</p><div className="mt-3 grid gap-1 text-xs text-emerald-900 sm:grid-cols-2"><span>Dataset: <code>{result.dataset_id}</code></span><span>Version: {result.version_number}</span><span>Job: <code>{result.job_id}</code></span><span>Status: {result.status.replaceAll("_", " ")}</span></div><div className="mt-4 flex flex-wrap gap-2"><Link href={`/datasets?dataset=${encodeURIComponent(result.dataset_id)}`} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-800">Open dataset <ArrowRight size={14}/></Link><Link href={`/jobs?job=${encodeURIComponent(result.job_id)}`} className="rounded-lg border border-emerald-200 bg-white px-3 py-2 text-xs font-medium text-emerald-900">Track analysis job</Link></div></div><button aria-label="Dismiss upload result" onClick={() => setResult(null)} className="text-emerald-800"><X size={16}/></button></div></div> : <>
          <button type="button" onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files[0]); }} className={`flex min-h-56 w-full flex-col items-center justify-center rounded-xl border-2 border-dashed px-5 py-8 text-center transition-colors ${dragging ? "border-emerald-500 bg-emerald-50" : "border-gray-300 bg-gray-50 hover:border-emerald-400 hover:bg-emerald-50/50"}`} aria-label="Select or drop dataset archive">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-white text-emerald-800 shadow-sm"><FileUp size={22}/></span><span className="mt-3 text-sm font-semibold text-zinc-100">Drop your archive here or browse files</span><span className="mt-1 text-xs text-zinc-400">Dataset files stay on your configured CropLens backend.</span>
          </button>
          <input ref={inputRef} type="file" accept=".zip,.tar,.gz,.tgz" className="sr-only" onChange={(event) => choose(event.target.files?.[0])}/>
          {file && <div className="mt-4 flex items-center gap-3 rounded-lg border border-croplens-border p-3"><Archive size={18} className="shrink-0 text-emerald-800"/><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-zinc-100">{file.name}</p><p className="text-[11px] text-zinc-400">{(file.size / (1024 * 1024)).toFixed(1)} MB</p></div><button disabled={busy} onClick={() => setFile(null)} aria-label="Remove selected archive" className="rounded p-1 text-zinc-400 hover:bg-gray-100"><X size={15}/></button></div>}
          <label className="mt-5 block text-xs font-medium text-zinc-400">Display name <span className="font-normal">(optional)</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={160} className="mt-1.5 h-10 w-full rounded-lg border border-croplens-border bg-white px-3 text-sm text-zinc-100 placeholder:text-gray-400" placeholder="e.g. Rice field samples"/></label>
          {busy && <div className="mt-5" aria-live="polite"><div className="mb-1.5 flex justify-between text-xs text-zinc-400"><span>Uploading archive</span><span>{progress ?? 0}%</span></div><div className="h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-emerald-600 transition-[width] duration-200" style={{ width: `${progress ?? 0}%` }}/></div></div>}
          {error && <div role="alert" className="mt-4 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800"><AlertCircle size={15} className="shrink-0"/>{error}</div>}
          <button onClick={upload} disabled={!file || busy} className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-gray-300">{busy ? <><LoaderCircle size={16} className="animate-spin"/>Uploading…</> : <><FileUp size={16}/>Upload & analyze</>}</button>
        </>}</section>
      <aside className="space-y-4"><div className="rounded-xl border border-croplens-border bg-white p-5"><div className="flex items-center gap-2 text-sm font-semibold text-zinc-100"><ShieldCheck size={17} className="text-emerald-800"/>Archive validation</div><ul className="mt-4 space-y-3 text-xs leading-relaxed text-zinc-400"><li className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-600"/>Supported archives: {formats.join(", ")}.</li><li className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-600"/>Archive paths and extraction limits are enforced by the API.</li><li className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-600"/>For image datasets, organize samples into class folders.</li><li className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-600"/>Actual size and file-count limits are configured on the backend.</li></ul></div><div className="rounded-xl border border-croplens-border bg-gray-50 p-5"><div className="flex items-center gap-2 text-sm font-semibold text-zinc-100"><HardDrive size={16} className="text-gray-500"/>After upload</div><p className="mt-2 text-xs leading-relaxed text-zinc-400">CropLens registers a dataset version and returns the processing job identifier. Follow the job center to see stages, failures, and completion from the backend.</p></div></aside>
    </div>
  </PageContainer>;
}
