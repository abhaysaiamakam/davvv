"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { apiClient } from "@/lib/api-client";

export interface EvidenceImage {
  relativePath: string;
  label: string;
  className?: string;
  fileSizeBytes?: number;
  detail?: string;
}

/** Resolves repository-relative image paths to the existing version-scoped image API. */
export function EvidenceImageGrid({ datasetId, versionId, images }: {
  datasetId: string;
  versionId: string;
  images: EvidenceImage[];
}) {
  const [ids, setIds] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const pathKey = images.map(item => item.relativePath).join("\u0000");
  useEffect(() => {
    let active = true;
    async function resolve() {
      const paths = pathKey ? pathKey.split("\u0000") : [];
      const pairs = await Promise.all(paths.map(async path => {
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(path));
        const id = Array.from(new Uint8Array(digest)).map(value => value.toString(16).padStart(2, "0")).join("").slice(0, 32);
        return [path, id] as const;
      }));
      if (active) setIds(Object.fromEntries(pairs));
    }
    void resolve();
    return () => { active = false; };
  }, [pathKey]);

  if (!images.length) return <p className="mt-3 rounded-lg bg-gray-50 p-3 text-xs text-zinc-500">No image samples were returned for this result.</p>;
  return <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
    {images.map(item => {
      const id = ids[item.relativePath];
      const src = id ? apiClient.imageAssetUrl(`/api/v1/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/images/${id}/thumbnail`) : "";
      return <figure key={item.relativePath} className="overflow-hidden rounded-lg border border-croplens-border bg-white">
        {src && !failed[item.relativePath] ? <div className="relative aspect-[4/3] bg-gray-100"><Image src={src} alt={`${item.label}: ${item.relativePath}`} fill sizes="(max-width: 640px) 100vw, (max-width: 1280px) 50vw, 33vw" unoptimized loading="lazy" onError={() => setFailed(previous => ({...previous, [item.relativePath]: true}))} className="object-contain"/></div> : failed[item.relativePath] ? <div role="status" className="flex aspect-[4/3] items-center justify-center bg-gray-100 p-4 text-center text-xs text-zinc-500">Preview unavailable for this file in the bound version.</div> : <div className="aspect-[4/3] animate-pulse bg-gray-100" aria-label="Resolving image"/>}
        <figcaption className="space-y-1 p-2.5 text-[10px]">
          <p className="font-semibold text-zinc-800">{item.label}{item.className ? ` · ${item.className}` : ""}</p>
          <p className="break-all font-mono text-zinc-500">{item.relativePath}</p>
          {item.fileSizeBytes !== undefined && <p className="text-zinc-500">{(item.fileSizeBytes / 1024).toFixed(1)} KB</p>}
          {item.detail && <p className="text-zinc-600">{item.detail}</p>}
        </figcaption>
      </figure>;
    })}
  </div>;
}
