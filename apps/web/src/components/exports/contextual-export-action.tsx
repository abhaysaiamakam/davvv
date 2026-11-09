import Link from "next/link";
import { Download } from "lucide-react";
import type { ExportType } from "@croplens/shared-types";

export function ContextualExportAction({ type, datasetId, versionId }: { type: ExportType; datasetId?: string | null; versionId?: string | null }) {
  const query = new URLSearchParams({ type, ...(datasetId ? { dataset_id: datasetId } : {}), ...(versionId ? { version_id: versionId } : {}) });
  return <Link href={`/exports?${query.toString()}`} className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-emerald-200 bg-white px-3 text-xs font-semibold text-emerald-800 hover:bg-emerald-50"><Download size={14}/>Export</Link>;
}
