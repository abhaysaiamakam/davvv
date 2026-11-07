/**
 * TypeScript definitions for M6 Processing Jobs.
 * Mirrors Python schemas in apps/api/app/schemas/job.py.
 */

export type JobStatus =
  | 'queued'
  | 'validating'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type JobStage =
  | 'queued'
  | 'extraction'
  | 'discovery'
  | 'validation'
  | 'exact_duplicates'
  | 'near_duplicates'
  | 'unified_analysis'
  | 'quality_lab'
  | 'eda_engine'
  | 'visualizations'
  | 'finalizing'
  | 'completed'
  | 'failed';

export interface ProcessingJob {
  job_id: string;
  dataset_id: string;
  dataset_version: string;
  job_type: string;
  status: JobStatus;
  current_stage: JobStage;
  progress_pct: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  retry_count: number;
  artifact_refs: Record<string, string | null>;
}

export interface JobStatusResponse {
  job_id: string;
  dataset_id: string;
  dataset_version: string;
  status: JobStatus;
  current_stage: JobStage;
  progress_pct: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
}

export interface JobListResponse {
  total: number;
  items: ProcessingJob[];
}

