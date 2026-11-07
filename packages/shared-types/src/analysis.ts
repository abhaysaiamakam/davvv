import {
  DatasetDiscoveryResult,
  DatasetValidationResult,
  DuplicateAnalysisResult,
  NearDuplicateAnalysisResult,
  NearDuplicateQueryConfig,
} from './dataset';

/**
 * Shared Analysis types for CropLens
 */

export type AnalysisStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface AnalysisConfig {
  near_duplicate_config?: NearDuplicateQueryConfig | null;
  force_refresh?: boolean;
  include_near_duplicates?: boolean;
}

export interface UnifiedAnalysisMetrics {
  total_files_discovered: number | null;
  total_classes_discovered: number | null;
  total_validated_images: number | null;
  total_corrupted_images: number | null;
  total_unreadable_images: number | null;
  total_processing_errors: number | null;
  total_unsupported_files: number | null;
  exact_duplicate_groups: number | null;
  exact_duplicate_redundant_instances: number | null;
  exact_duplicate_percentage: number | null;
  cross_class_exact_duplicate_groups: number | null;
  near_duplicate_groups: number | null;
  near_duplicate_images_in_groups: number | null;
  near_duplicate_redundant_instances: number | null;
  near_duplicate_percentage: number | null;
  cross_class_near_duplicate_groups: number | null;
  total_redundant_images: number | null;
  clean_unique_images: number | null;
  quality_score: number | null;
}

export interface UnifiedAnalysisResult {
  id: string;
  dataset_id: string;
  dataset_name: string;
  status: AnalysisStatus;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  error_message?: string | null;
  config: AnalysisConfig;
  stages_completed: string[];
  stage_durations_ms: Record<string, number>;
  metrics: UnifiedAnalysisMetrics;
  discovery?: DatasetDiscoveryResult | null;
  validation?: DatasetValidationResult | null;
  exact_duplicates?: DuplicateAnalysisResult | null;
  near_duplicates?: NearDuplicateAnalysisResult | null;
  warnings: string[];
}

export interface AnalysisStatusResponse {
  analysis_id: string;
  dataset_id: string;
  status: AnalysisStatus;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  stages_completed: string[];
  current_stage?: string | null;
  error_message?: string | null;
}

export interface AnalysisCreateRequest {
  dataset_id: string;
  config?: AnalysisConfig | null;
}

export interface AnalysisSummary {
  id: string;
  dataset_id: string;
  status: AnalysisStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  // Metrics are null when not yet computed
  total_files_evaluated: number | null;
  duplicate_count: number | null;
  corrupted_count: number | null;
  quality_score: number | null;
}

export interface AnalysisListResponse {
  total: number;
  items: AnalysisSummary[];
  is_placeholder: boolean;
  note?: string;
}

