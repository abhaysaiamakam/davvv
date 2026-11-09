import type {
  AnalyticalReport,
  ComparisonCreateRequest,
  DatasetComparisonListResponse,
  DatasetComparisonReport,
  DataQualityAssessment,
  DatasetInsight,
  DatasetListResponse,
  DatasetDiscoveryResult,
  DatasetMetadata,
  DatasetReadinessAssessment,
  DatasetUploadResponse,
  DatasetVersionListResponse,
  AvailableOperationsResponse,
  PreprocessingOperationConfig,
  PreprocessingPreviewResponse,
  PreprocessingApplyResponse,
  PreprocessingHistoryListResponse,
  AvailableFeaturesResponse,
  FeatureOperationConfig,
  FeaturePreviewResponse,
  FeatureApplyResponse,
  FeatureHistoryListResponse,
  EdaReport,
  HealthResponse,
  InsightCollectionResponse,
  JobListResponse,
  ProcessingJob,
  ReportListResponse,
  ReportGenerateRequest,
  ReadinessAssessRequest,
  VisualizationCollectionResponse,
  DatasetImageListResponse,
  ImagePreviewOperation,
  ImagePreprocessingPreviewResponse,
  ImageAnnotationResponse,
} from "@croplens/shared-types";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_PREFIX = `${API_BASE}/api/v1`;

export class ApiClientError extends Error {
  constructor(message: string, readonly status: number, readonly errorCode?: string) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, init);
  } catch {
    throw new ApiClientError("Cannot reach the CropLens API. Check that the backend is running.", 0);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
      ? body.detail : `Request failed (${response.status})`;
    const code = typeof body === "object" && body !== null && "error_code" in body && typeof body.error_code === "string"
      ? body.error_code : undefined;
    throw new ApiClientError(detail, response.status, code);
  }
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const apiClient = {
  getHealth: () => request<HealthResponse>("/health"),
  getDatasets: () => request<DatasetListResponse>("/datasets"),
  getDataset: (id: string) => request<DatasetMetadata>(`/datasets/${encodeURIComponent(id)}`),
  getDatasetVersions: (id: string) => request<DatasetVersionListResponse>(`/datasets/${encodeURIComponent(id)}/versions`),
  getImages: (datasetId: string, versionId: string, options: { page?: number; page_size?: number; class_name?: string; annotation_class_id?: string; search?: string; sort_by?: "filename" | "file_size" | "width" | "height"; descending?: boolean } = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(options)) if (value !== undefined && value !== "") query.set(key, String(value));
    return request<DatasetImageListResponse>(`/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/images?${query.toString()}`);
  },
  getImage: (datasetId: string, versionId: string, imageId: string) => request<DatasetImageListResponse["items"][number]>(`/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/images/${encodeURIComponent(imageId)}`),
  getImageAnnotations: (datasetId: string, versionId: string, imageId: string) => request<ImageAnnotationResponse>(`/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/images/${encodeURIComponent(imageId)}/annotations`),
  imageAssetUrl: (path: string) => `${API_BASE}${path}`,
  previewImagePreprocessing: (datasetId: string, versionId: string, imageId: string, operation: ImagePreviewOperation) => request<ImagePreprocessingPreviewResponse>(`/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/images/${encodeURIComponent(imageId)}/preprocessing-preview`, json({ operation: { ...operation, modality: "image" } })),
  discoverDataset: (id: string) => request<DatasetDiscoveryResult>(`/datasets/${encodeURIComponent(id)}/discover`, { method: "POST" }),
  validateDataset: (id: string) => request<NonNullable<DatasetMetadata["validation"]>>(`/datasets/${encodeURIComponent(id)}/validate`, { method: "POST" }),
  detectDuplicates: (id: string) => request<NonNullable<DatasetMetadata["duplicates"]>>(`/datasets/${encodeURIComponent(id)}/duplicates/detect`, { method: "POST" }),
  uploadDataset: (file: File, name?: string, datasetId?: string, onProgress?: (percent: number) => void) => {
    const form = new FormData();
    form.set("file", file);
    if (name) form.set("name", name);
    if (datasetId) form.set("dataset_id", datasetId);
    return new Promise<DatasetUploadResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_PREFIX}/datasets/upload`);
      xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100)); };
      xhr.onerror = () => reject(new ApiClientError("Cannot reach the CropLens API. Check that the backend is running.", 0));
      xhr.onload = () => {
        let body: unknown;
        try { body = JSON.parse(xhr.responseText || "null"); } catch { reject(new ApiClientError("The API returned an invalid response.", xhr.status)); return; }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as DatasetUploadResponse);
        else {
          const data = typeof body === "object" && body !== null ? body : {};
          const detail = "detail" in data && typeof data.detail === "string" ? data.detail : `Request failed (${xhr.status})`;
          const code = "error_code" in data && typeof data.error_code === "string" ? data.error_code : undefined;
          reject(new ApiClientError(detail, xhr.status, code));
        }
      };
      xhr.send(form);
    });
  },
  listJobs: () => request<JobListResponse>("/jobs"),
  getJob: (id: string) => request<ProcessingJob>(`/jobs/${encodeURIComponent(id)}`),
  retryJob: (id: string) => request<ProcessingJob>(`/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  assessQuality: (id: string) => request<DataQualityAssessment>(`/datasets/${encodeURIComponent(id)}/quality-assessments`, { method: "POST" }),
  getQuality: (id: string) => request<DataQualityAssessment>(`/datasets/${encodeURIComponent(id)}/quality-assessment`),
  runEda: (id: string) => request<EdaReport>(`/datasets/${encodeURIComponent(id)}/eda`, { method: "POST" }),
  getEda: (id: string) => request<EdaReport>(`/datasets/${encodeURIComponent(id)}/eda`),
  getVisualizations: (id: string, version?: string) => request<VisualizationCollectionResponse>(version
    ? `/datasets/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/visualizations`
    : `/datasets/${encodeURIComponent(id)}/visualizations`),
  getInsights: (id: string, version?: string) => request<InsightCollectionResponse>(version
    ? `/datasets/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/insights`
    : `/datasets/${encodeURIComponent(id)}/insights`),
  getInsight: (id: string, insightId: string) => request<DatasetInsight>(`/datasets/${encodeURIComponent(id)}/insights/${encodeURIComponent(insightId)}`),
  getReadiness: (id: string, version?: string) => request<DatasetReadinessAssessment>(version
    ? `/datasets/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/readiness`
    : `/datasets/${encodeURIComponent(id)}/readiness`),
  assessReadiness: (id: string, body?: Omit<ReadinessAssessRequest, "dataset_id">) => request<DatasetReadinessAssessment>(`/datasets/${encodeURIComponent(id)}/readiness/assess`, json({ dataset_id: id, ...body })),
  getReports: (id: string, versionId?: string) => request<ReportListResponse>(versionId
    ? `/datasets/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/reports`
    : `/datasets/${encodeURIComponent(id)}/reports`),
  generateReport: (id: string, body?: Omit<ReportGenerateRequest, "dataset_id">) => request<AnalyticalReport>(`/datasets/${encodeURIComponent(id)}/reports/generate`, json({ dataset_id: id, ...body })),
  reportDownloadUrl: (id: string, reportId: string, format: "pdf" | "json") => `${API_PREFIX}/datasets/${encodeURIComponent(id)}/reports/${encodeURIComponent(reportId)}/download?format=${format}`,
  listComparisons: () => request<DatasetComparisonListResponse>("/comparisons"),
  compareDatasets: (body: ComparisonCreateRequest) => request<DatasetComparisonReport>("/comparisons", json(body)),
  getPreprocessingOperations: (id: string) => request<AvailableOperationsResponse>(`/datasets/${encodeURIComponent(id)}/preprocessing/operations`),
  previewPreprocessing: (id: string, versionId: string | null, operations: PreprocessingOperationConfig[]) => request<PreprocessingPreviewResponse>(`/datasets/${encodeURIComponent(id)}/preprocessing/preview`, json({ dataset_id: id, version_id: versionId, operations })),
  applyPreprocessing: (id: string, versionId: string | null, operations: PreprocessingOperationConfig[], description?: string) => request<PreprocessingApplyResponse>(`/datasets/${encodeURIComponent(id)}/preprocessing/apply`, json({ dataset_id: id, version_id: versionId, operations, description })),
  getPreprocessingHistory: (id: string) => request<PreprocessingHistoryListResponse>(`/datasets/${encodeURIComponent(id)}/preprocessing/history`),
  getAvailableFeatures: (id: string) => request<AvailableFeaturesResponse>(`/datasets/${encodeURIComponent(id)}/feature-engineering/features`),
  previewFeatures: (id: string, versionId: string | null, operations: FeatureOperationConfig[]) => request<FeaturePreviewResponse>(`/datasets/${encodeURIComponent(id)}/feature-engineering/preview`, json({ dataset_id: id, version_id: versionId, operations })),
  applyFeatures: (id: string, versionId: string | null, operations: FeatureOperationConfig[], description?: string) => request<FeatureApplyResponse>(`/datasets/${encodeURIComponent(id)}/feature-engineering/apply`, json({ dataset_id: id, version_id: versionId, operations, description })),
  getFeatureHistory: (id: string) => request<FeatureHistoryListResponse>(`/datasets/${encodeURIComponent(id)}/feature-engineering/history`),
};
