/**
 * EDA (Exploratory Data Analysis) TypeScript contracts for CropLens.
 * Mirrors Python Pydantic schemas in apps/api/app/schemas/eda.py
 */

export type EdaStatus = "pending" | "running" | "completed" | "failed";
export type EdaSeverity = "info" | "low" | "medium" | "high" | "critical";
export type EdaFindingCategory =
  | "class_distribution"
  | "dimension_consistency"
  | "format_diversity"
  | "color_space"
  | "aspect_ratio"
  | "file_size"
  | "dataset_overview";

export interface ClassDistributionEntry {
  class_name: string;
  relative_path: string;
  valid_image_count: number;
  invalid_image_count: number;
  percentage_of_valid: number;
  percentage_of_total: number;
  rank: number;
  deviation_from_mean: number;
  deviation_from_median: number;
}

export interface ClassDistributionAnalysis {
  total_classes: number;
  classes_with_images: number;
  empty_classes: string[];
  distribution: ClassDistributionEntry[];
  min_count: number;
  max_count: number;
  mean_count: number;
  median_count: number;
  std_count: number;
  variance: number;
  coefficient_of_variation: number | null;
  imbalance_ratio: number | null;
  entropy: number;
  normalized_entropy: number | null;
  gini_coefficient: number;
  evaluation_notes: string[];
}

export interface DimensionFrequencyEntry {
  width: number;
  height: number;
  count: number;
  percentage: number;
}

export interface DimensionStats {
  min_width: number | null;
  max_width: number | null;
  mean_width: number | null;
  median_width: number | null;
  std_width: number | null;
  min_height: number | null;
  max_height: number | null;
  mean_height: number | null;
  median_height: number | null;
  std_height: number | null;
  portrait_count: number;
  landscape_count: number;
  square_count: number;
  portrait_pct: number;
  landscape_pct: number;
  square_pct: number;
  unique_dimensions: number;
  most_common_dimensions: DimensionFrequencyEntry[];
  dimension_frequency: Record<string, number>;
}

export interface AspectRatioBin {
  label: string;
  min_ar: number;
  max_ar: number;
  count: number;
  percentage: number;
}

export interface AspectRatioAnalysis {
  min_ar: number | null;
  max_ar: number | null;
  mean_ar: number | null;
  median_ar: number | null;
  std_ar: number | null;
  portrait_count: number;
  landscape_count: number;
  square_count: number;
  extreme_low_count: number;
  extreme_high_count: number;
  distribution_bins: AspectRatioBin[];
}

export interface FormatAnalysis {
  format_distribution: Record<string, number>;
  format_percentages: Record<string, number>;
  unique_format_count: number;
  most_common_format: string | null;
  least_common_format: string | null;
}

export interface ColorAnalysis {
  color_mode_distribution: Record<string, number>;
  color_mode_percentages: Record<string, number>;
  grayscale_count: number;
  rgb_count: number;
  rgba_count: number;
  rgb_mean: number[] | null;
  rgb_std: number[] | null;
  sampling_methodology: string;
  sampling_seed: number;
}

export interface FileSizeBin {
  label: string;
  min_bytes: number;
  max_bytes: number;
  count: number;
  percentage: number;
}

export interface FileSizeStats {
  min_bytes: number | null;
  max_bytes: number | null;
  mean_bytes: number | null;
  median_bytes: number | null;
  std_bytes: number | null;
  total_bytes: number;
  min_human: string | null;
  max_human: string | null;
  mean_human: string | null;
  total_human: string;
  size_distribution_bins: FileSizeBin[];
}

export interface ClassMetadataSummary {
  class_name: string;
  valid_count: number;
  dimension_stats: DimensionStats | null;
  format_distribution: Record<string, number>;
  color_mode_distribution: Record<string, number>;
  file_size_stats: FileSizeStats | null;
  mean_aspect_ratio: number | null;
}

export interface DatasetOverview {
  dataset_id: string;
  dataset_name: string;
  total_discovered_files: number;
  total_valid_images: number;
  total_invalid_images: number;
  class_count: number;
  classes_with_images: number;
  empty_class_count: number;
  format_count: number;
  unique_dimension_count: number;
  total_size_bytes: number;
  total_size_human: string;
  analysis_id: string | null;
  quality_assessment_id: string | null;
  eda_methodology_version: string;
}

export interface EdaFinding {
  id: string;
  category: EdaFindingCategory;
  severity: EdaSeverity;
  title: string;
  explanation: string;
  metric_name: string;
  observed_value: unknown;
  expected_value: unknown | null;
  threshold_used: unknown | null;
  affected_classes: string[];
  affected_image_samples: string[];
  recommended_action: string;
  evidence_references: string[];
  methodology_version: string;
}

export interface EdaReport {
  id: string;
  dataset_id: string;
  dataset_name: string;
  source_analysis_id: string | null;
  source_quality_assessment_id: string | null;
  status: EdaStatus;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  methodology_version: string;
  overview: DatasetOverview;
  class_distribution: ClassDistributionAnalysis;
  dimension_analysis: DimensionStats;
  aspect_ratio_analysis: AspectRatioAnalysis;
  format_analysis: FormatAnalysis;
  color_analysis: ColorAnalysis;
  file_size_analysis: FileSizeStats;
  class_metadata: ClassMetadataSummary[];
  findings: EdaFinding[];
  warnings: string[];
}

export interface EdaReportSummary {
  id: string;
  dataset_id: string;
  status: EdaStatus;
  created_at: string;
  completed_at: string | null;
  total_valid_images: number;
  class_count: number;
  findings_count: number;
}

export interface EdaReportListResponse {
  total: number;
  items: EdaReportSummary[];
  note: string | null;
}

export interface EdaStatusResponse {
  eda_id: string;
  dataset_id: string;
  status: EdaStatus;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  methodology_version: string;
  error_message: string | null;
}

