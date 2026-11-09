import { DatasetReadinessAssessment, ReadinessStatus, TaskContext } from './readiness';

export type ReportExportFormat = 'json' | 'pdf' | 'html';
export type ReportStatus = 'generating' | 'completed' | 'failed';

export interface ExecutiveSummary {
  dataset_name: string;
  dataset_modality: string;
  dataset_version: string;
  total_files: number;
  total_bytes: number;
  main_objective: string;
  key_findings: string[];
  quality_concerns: string[];
  readiness_status: ReadinessStatus;
  recommended_next_steps: string[];
}

export interface DatasetOverviewSection {
  dataset_id: string;
  dataset_name: string;
  version_id: string;
  version_number: number;
  modality: string;
  is_curated: boolean;
  is_uploaded: boolean;
  created_at: string;
  total_files: number;
  total_bytes: number;
  item_count?: number | null;
  classes: string[];
  columns: string[];
  content_fingerprint?: string | null;
}

export interface QualitySection {
  quality_score?: number | null;
  quality_tier?: string | null;
  missing_values_count: number;
  corrupted_files_count: number;
  duplicate_count: number;
  class_imbalance_ratio?: number | null;
  findings: Record<string, unknown>[];
  warnings: string[];
}

export interface EdaSection {
  distributions_summary: Record<string, unknown>;
  relationships_summary: Record<string, unknown>;
  visualization_count: number;
  visualization_refs: string[];
  eda_findings: Record<string, unknown>[];
}

export interface InsightsSection {
  total_insights: number;
  category_counts: Record<string, number>;
  insights: Record<string, unknown>[];
}

export interface PreprocessingSection {
  operations_applied_count: number;
  applied_operations: Record<string, unknown>[];
  source_version_id?: string | null;
  derived_version_id?: string | null;
  remaining_quality_concerns: string[];
}

export interface FeatureEngineeringSection {
  generated_features_count: number;
  features_generated: string[];
  selected_features: string[];
  removed_features: string[];
  pca_component_count?: number | null;
  pca_explained_variance_ratio?: number[] | null;
  feature_operations: Record<string, unknown>[];
}

export interface MethodologyStep {
  step_number: number;
  stage_name: string;
  operation_name: string;
  parameters: Record<string, unknown>;
  input_version_id?: string | null;
  output_version_id?: string | null;
  affected_count?: number | null;
  timestamp: string;
}

export interface MethodologySection {
  workflow_summary: string;
  steps: MethodologyStep[];
  execution_engine: string;
  reproducibility_notes: string[];
}

export interface ReportProvenance {
  report_id: string;
  dataset_id: string;
  version_id: string;
  content_fingerprint?: string | null;
  created_at: string;
  schema_version: string;
  artifact_refs: Record<string, string>;
  generator_status: ReportStatus;
}

export interface AnalyticalReport {
  report_id: string;
  dataset_id: string;
  version_id: string;
  title: string;
  provenance: ReportProvenance;
  executive_summary: ExecutiveSummary;
  dataset_overview: DatasetOverviewSection;
  quality_section: QualitySection;
  eda_section: EdaSection;
  insights_section: InsightsSection;
  preprocessing_section: PreprocessingSection;
  feature_engineering_section: FeatureEngineeringSection;
  readiness_section: DatasetReadinessAssessment;
  methodology_section: MethodologySection;
  conclusion_section: Record<string, unknown>;
  created_at: string;
}

export interface ReportGenerateRequest {
  dataset_id: string;
  version_id?: string | null;
  title?: string | null;
  task_context?: TaskContext | null;
  force_refresh?: boolean;
}

export interface ReportListResponse {
  total: number;
  items: AnalyticalReport[];
}
