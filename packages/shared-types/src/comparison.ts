/**
 * TypeScript definitions for M5 Dataset Comparison Engine.
 * Mirrors Python schemas in apps/api/app/schemas/comparison.py.
 */

export type ComparisonStatus = 'pending' | 'running' | 'completed' | 'failed';

export type ComparisonFindingCategory =
  | 'scale'
  | 'class_distribution'
  | 'image_characteristics'
  | 'data_quality'
  | 'duplicate_impact';

export type ComparisonSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

export type ComparisonFreshness = 'current' | 'stale' | 'pending' | 'failed';

export interface MetricComparison {
  dataset_a_value: number | null;
  dataset_b_value: number | null;
  absolute_diff: number | null;
  pct_change: number | null;
  is_available: boolean;
}

export interface DatasetOverviewComparison {
  total_images: MetricComparison;
  valid_images: MetricComparison;
  corrupted_images: MetricComparison;
  total_classes: MetricComparison;
  images_per_class_mean: MetricComparison;
  exact_duplicate_pct: MetricComparison;
  near_duplicate_pct: MetricComparison;
}

export interface SharedClassComparison {
  class_name: string;
  count_a: number;
  count_b: number;
  absolute_diff: number;
  pct_change: number | null;
}

export interface ClassAlignmentSummary {
  total_classes_a: number;
  total_classes_b: number;
  shared_classes: string[];
  only_in_a: string[];
  only_in_b: string[];
  shared_class_comparisons: SharedClassComparison[];
  class_overlap_pct: number | null;
  empty_classes_a: number;
  empty_classes_b: number;
}

export interface ClassDistributionComparison {
  alignment: ClassAlignmentSummary;
  entropy_a: MetricComparison;
  entropy_b: MetricComparison;
  gini_coefficient: MetricComparison;
  imbalance_ratio: MetricComparison;
  coefficient_of_variation: MetricComparison;
  normalized_entropy: MetricComparison;
  is_available: boolean;
  fallback_note: string | null;
}

export interface ImageCharacteristicsComparison {
  median_width: MetricComparison;
  median_height: MetricComparison;
  mean_aspect_ratio: MetricComparison;
  median_file_size_bytes: MetricComparison;
  mean_file_size_bytes: MetricComparison;
  dominant_color_mode_a: string | null;
  dominant_color_mode_b: string | null;
  dominant_format_a: string | null;
  dominant_format_b: string | null;
  is_available: boolean;
  fallback_note: string | null;
}

export interface DataQualityComparison {
  exact_duplicate_groups: MetricComparison;
  near_duplicate_groups: MetricComparison;
  total_redundant_images: MetricComparison;
  clean_unique_images: MetricComparison;
  overall_quality_score: MetricComparison;
  integrity_rate: MetricComparison;
  quality_tier_a: string | null;
  quality_tier_b: string | null;
  critical_findings_count: MetricComparison;
  is_quality_available: boolean;
  is_duplicate_available: boolean;
  fallback_note: string | null;
}

export interface ComparisonFinding {
  id: string;
  category: ComparisonFindingCategory;
  severity: ComparisonSeverity;
  title: string;
  explanation: string;
  metric_name: string | null;
  value_a: number | null;
  value_b: number | null;
  absolute_diff: number | null;
  pct_change: number | null;
  threshold_used: number | null;
  recommended_action: string | null;
  evidence_references: string[];
  methodology_version: string;
}

export interface ComparisonSourceRefs {
  analysis_a_id: string | null;
  analysis_b_id: string | null;
  quality_a_id: string | null;
  quality_b_id: string | null;
  eda_a_id: string | null;
  eda_b_id: string | null;
}

export interface DatasetComparisonReport {
  id: string;
  dataset_a_id: string;
  dataset_b_id: string;
  dataset_a_name: string;
  dataset_b_name: string;
  status: ComparisonStatus;
  freshness_status: ComparisonFreshness;
  source_version_a: string | null;
  source_version_b: string | null;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  methodology_version: string;
  source_refs: ComparisonSourceRefs;
  overview: DatasetOverviewComparison | null;
  class_distribution: ClassDistributionComparison | null;
  image_characteristics: ImageCharacteristicsComparison | null;
  data_quality: DataQualityComparison | null;
  findings: ComparisonFinding[];
  warnings: string[];
  error_message: string | null;
}

export interface DatasetComparisonSummary {
  id: string;
  dataset_a_id: string;
  dataset_b_id: string;
  dataset_a_name: string;
  dataset_b_name: string;
  status: ComparisonStatus;
  freshness_status: ComparisonFreshness;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  findings_count: number;
  dataset_a_valid_images: number | null;
  dataset_b_valid_images: number | null;
}

export interface DatasetComparisonListResponse {
  total: number;
  items: DatasetComparisonSummary[];
  note: string | null;
}

export interface ComparisonStatusResponse {
  comparison_id: string;
  dataset_a_id: string;
  dataset_b_id: string;
  status: ComparisonStatus;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  methodology_version: string;
  error_message: string | null;
}

export interface ComparisonCreateRequest {
  dataset_a_id: string;
  dataset_b_id: string;
  force_refresh?: boolean;
}

export interface ComparisonFreshnessResponse {
  comparison_id: string;
  dataset_a_id: string;
  dataset_b_id: string;
  freshness_status: ComparisonFreshness;
  is_stale: boolean;
  source_analysis_a_id: string | null;
  current_analysis_a_id: string | null;
  source_analysis_b_id: string | null;
  current_analysis_b_id: string | null;
  reason: string | null;
}
