"use client";

import { useCallback, useEffect, useState } from "react";
import type { DatasetListResponse } from "@croplens/shared-types";
import { apiClient } from "@/lib/api-client";

export function useDatasetContext() {
  const [data, setData] = useState<DatasetListResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await apiClient.getDatasets();
      setData(result);
      const preferred = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("dataset") || localStorage.getItem("croplens-dataset") : null;
      const valid = result.items.find((item) => item.id === preferred)?.id ?? result.items[0]?.id ?? "";
      setSelectedId(valid);
      if (valid && typeof window !== "undefined") {
        localStorage.setItem("croplens-dataset", valid);
        const name = result.items.find((item) => item.id === valid)?.name ?? valid;
        const currentVersionId = result.items.find((item) => item.id === valid)?.current_version_id ?? "";
        window.dispatchEvent(new CustomEvent("croplens:dataset", { detail: { id: valid, name, currentVersionId } }));
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load datasets."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  const select = useCallback((id: string) => {
    setSelectedId(id);
    if (typeof window !== "undefined") {
      localStorage.setItem("croplens-dataset", id);
      const selected = data?.items.find((item) => item.id === id);
      const currentVersionId = selected?.current_version_id ?? "";
      window.dispatchEvent(new CustomEvent("croplens:dataset", { detail: { id, name: selected?.name ?? id, currentVersionId } }));
      const url = new URL(window.location.href);
      url.searchParams.set("dataset", id);
      window.history.replaceState(null, "", url);
    }
  }, [data]);
  const selected = data?.items.find((item) => item.id === selectedId);
  return { data, datasets: data?.items ?? [], selected, selectedId, select, loading, error, reload };
}
