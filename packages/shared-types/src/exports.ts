export type ExportType = "comprehensive" | "eda" | "quality" | "preprocessing" | "feature_engineering" | "readiness" | "methodology" | "dataset";
export type ExportFormat = "csv" | "json" | "pdf" | "zip";

export interface ExportCreateRequest {
  export_type: ExportType;
  format: ExportFormat;
  include_methodology?: boolean;
  include_visualizations?: boolean;
  title?: string | null;
}

export interface ExportJob {
  export_id: string;
  dataset_id: string;
  version_id: string;
  export_type: ExportType;
  format: ExportFormat;
  status: "queued" | "running" | "completed" | "failed";
  progress_pct: number;
  created_at: string;
  completed_at?: string | null;
  filename?: string | null;
  download_url?: string | null;
  error_message?: string | null;
}
