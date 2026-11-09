export type ReadinessStatus =
  | 'ready'
  | 'ready_with_concerns'
  | 'needs_preprocessing'
  | 'insufficient_evidence'
  | 'not_assessed';

export type ReadinessDimension =
  | 'dataset_integrity'
  | 'data_quality'
  | 'analytical_suitability'
  | 'preprocessing_status'
  | 'feature_readiness';

export interface TaskContext {
  task_type?: 'classification' | 'regression' | 'forecasting' | 'object_detection' | 'exploratory' | string;
  target_column?: string;
  analytical_goal?: string;
}

export interface ReadinessDimensionAssessment {
  dimension: ReadinessDimension;
  status: ReadinessStatus;
  score: number;
  metrics: Record<string, unknown>;
  blocking_issues: string[];
  warnings: string[];
  recommendations: string[];
}

export interface DatasetReadinessAssessment {
  dataset_id: string;
  version_id: string;
  dataset_name: string;
  overall_status: ReadinessStatus;
  overall_score: number;
  task_context?: TaskContext | null;
  dimensions: ReadinessDimensionAssessment[];
  key_strengths: string[];
  critical_blockers: string[];
  recommendations: string[];
  missing_evidence: string[];
  evaluated_at: string;
}

export interface ReadinessAssessRequest {
  dataset_id: string;
  version_id?: string | null;
  task_context?: TaskContext | null;
}
