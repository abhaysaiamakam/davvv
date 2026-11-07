/**
 * M7 — Dataset Findings & Insights Intelligence Engine TypeScript contracts.
 *
 * Mirror of app/schemas/insights.py for shared frontend/backend type safety.
 */

export enum InsightSeverity {
  CRITICAL = 'critical',
  HIGH = 'high',
  MEDIUM = 'medium',
  LOW = 'low',
  INFO = 'info',
}

export enum InsightCategory {
  CLASS_DISTRIBUTION = 'class_distribution',
  IMAGE_QUALITY = 'image_quality',
  DUPLICATE_DATA = 'duplicate_data',
  DATA_QUALITY = 'data_quality',
  MISSING_VALUES = 'missing_values',
  OUTLIERS = 'outliers',
  DISTRIBUTION = 'distribution',
  CORRELATION = 'correlation',
  TIME_SERIES = 'time_series',
  ANNOTATION_QUALITY = 'annotation_quality',
  DATASET_COVERAGE = 'dataset_coverage',
  DATASET_READINESS = 'dataset_readiness',
}

export enum InsightConfidence {
  HIGH = 'high',
  MEDIUM = 'medium',
  LOW = 'low',
}

/** Traceable evidence backing a single insight. */
export interface InsightEvidence {
  metric: string;
  value: unknown;
  unit?: string | null;
  threshold?: number | null;
  source_artifact: string;
  source_path: string;
  explanation: string;
}

/** A single, evidence-backed dataset insight produced by M7. */
export interface DatasetInsight {
  insight_id: string;
  dataset_id: string;
  version_id: string;
  category: InsightCategory;
  severity: InsightSeverity;
  confidence: InsightConfidence;
  title: string;
  summary: string;
  explanation: string;
  evidence: InsightEvidence[];
  affected_classes: string[];
  affected_columns: string[];
  affected_files: string[];
  impact: string;
  recommended_action: string;
  limitations: string;
  created_at: string;
  analyzer_id: string;
  rule_id: string;
}

/** Complete set of M7 insights generated for a dataset version. */
export interface InsightCollection {
  id: string;
  dataset_id: string;
  dataset_version: string;
  status: 'completed' | 'failed';
  total: number;
  items: DatasetInsight[];
  error_message?: string | null;
  generated_at: string;
  source_analysis_id?: string | null;
  source_quality_id?: string | null;
  source_eda_id?: string | null;
}

/** Filtered view of an InsightCollection, returned by API endpoints. */
export interface InsightCollectionResponse {
  dataset_id: string;
  dataset_version: string;
  status: 'completed' | 'failed';
  total: number;
  items: DatasetInsight[];
  error_message?: string | null;
  filtered_category?: string | null;
  filtered_severity?: string | null;
}

