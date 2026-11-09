"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DatasetVersionListResponse } from "@croplens/shared-types";
import { apiClient } from "@/lib/api-client";

export function useDatasetVersion(datasetId: string, currentVersionId?: string | null) {
  const [data,setData]=useState<DatasetVersionListResponse|null>(null);
  const [versionId,setVersionId]=useState(currentVersionId??"");
  const [resolvedDataset,setResolvedDataset]=useState("");
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const requestId = useRef(0);
  const reload=useCallback(async()=>{
    const id = ++requestId.current;
    if(!datasetId){setData(null);setVersionId("");setResolvedDataset("");return;}
    setLoading(true);setError(null);
    try{const result=await apiClient.getDatasetVersions(datasetId);if(id!==requestId.current)return;setData(result);const saved=localStorage.getItem(`croplens-version:${datasetId}`);const chosen=result.items.find(v=>v.version_id===saved)?.version_id??result.items.find(v=>v.version_id===currentVersionId)?.version_id??result.items[0]?.version_id??currentVersionId??"";setVersionId(chosen);setResolvedDataset(datasetId);if(chosen){localStorage.setItem(`croplens-version:${datasetId}`,chosen);window.dispatchEvent(new CustomEvent("croplens:version",{detail:{datasetId,versionId:chosen}}))}}catch(issue){if(id!==requestId.current)return;setData(null);setError(issue instanceof Error?issue.message:"Dataset versions unavailable.");setVersionId(currentVersionId??"");setResolvedDataset(datasetId)}finally{if(id===requestId.current)setLoading(false)}
  },[datasetId,currentVersionId]);
  useEffect(()=>{void reload()},[reload]);
  const select=useCallback((id:string)=>{setVersionId(id);setResolvedDataset(datasetId);if(datasetId&&id){localStorage.setItem(`croplens-version:${datasetId}`,id);window.dispatchEvent(new CustomEvent("croplens:version",{detail:{datasetId,versionId:id}}))}},[datasetId]);
  return{data,versionId:resolvedDataset===datasetId?versionId:currentVersionId??"",versions:data?.items??[],loading,error,select,reload};
}
