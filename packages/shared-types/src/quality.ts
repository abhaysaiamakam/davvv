import { AnalysisStatus } from './analysis';

export type QualityFindingCategory =
  | 'integrity'
  | 'imbalance'
  | 'consistency'
  | 'duplicates'
  | 'metadata';

export type QualitySeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface QualityFinding {
  id: string;
  category: QualityFindingCategory;
  severity: QualitySeverity;
  title: string;
  explanation: string;
  metric_name: string;
  observed_value: any;
  expected_value?: any;
  threshold_used?: string | null;
  affected_classes: string[];
  affected_image_samples: string[];
  recommended_action: string;
  evidence_references: string[];
  methodology_version: string;
}

export interface ImageIntegrityAssessment {
  total_discovered_images: number | null;
  total_validated_images: number | null;
  total_corrupted_images: number | null;
  total_unreadable_images: number | null;
  total_processing_errors: number | null;
  total_unsupported_files: number | null;
  integrity_rate: number | null;
  status: string;
  is_available: boolean;
  evaluation_notes: string[];
}

export interface ClassImbalanceAssessment {
  total_classes: number;
  classes_with_images: number;
  empty_classes: string[];
  min_class_count: number | null;
  max_class_count: number | null;
  mean_class_count: number | null;
  median_class_count: number | null;
  std_class_count: number | null;
  imbalance_ratio: number | null;
  coefficient_of_variation: number | null;
  imbalance_severity: string;
  underrepresented_classes: Array<Record<string, any>>;
  overrepresented_classes: Array<Record<string, any>>;
  class_distribution: Record<string, number>;
  evaluation_notes: string[];
}

export interface MetadataConsistencyAssessment {
  min_width: number | null;
  max_width: number | null;
  mean_width: number | null;
  std_width: number | null;
  min_height: number | null;
  max_height: number | null;
  mean_height: number | null;
  std_height: number | null;
  min_aspect_ratio: number | null;
  max_aspect_ratio: number | null;
  mean_aspect_ratio: number | null;
  format_distribution: Record<string, number>;
  color_mode_distribution: Record<string, number>;
  aspect_ratio_outliers_count: number;
  small_dimension_images_count: number;
  consistency_rate: number | null;
  is_available: boolean;
  evaluation_notes: string[];
}

export interface DuplicateImpactAssessment {
  exact_duplicate_groups: number | null;
  exact_duplicate_redundant_instances: number | null;
  exact_duplicate_percentage: number | null;
  near_duplicate_groups: number | null;
  near_duplicate_images_in_groups: number | null;
  near_duplicate_redundant_instances: number | null;
  near_duplicate_percentage: number | null;
  cross_class_duplicate_groups: number | null;
  total_redundant_images: number | null;
  clean_unique_images: number | null;
  duplicate_impact_severity: string;
  classes_affected_count: number;
  class_duplicate_breakdown: Record<string, number>;
  is_available: boolean;
  evaluation_notes: string[];
}

export interface QualityScoreComponent {
  name: string;
  score: number;
  weight: number;
  weighted_score: number;
  explanation: string;
  metrics_used: Record<string, any>;
}

export interface TransparentQualityScore {
  overall_score: number;
  quality_tier: string;
  methodology_version: string;
  components: Record<string, QualityScoreComponent>;
  weight_configuration: Record<string, number>;
  explanation: string;
  is_complete: boolean;
}

export interface DataQualityAssessment {
  id: string;
  dataset_id: string;
  dataset_name: string;
  source_analysis_id?: string | null;
  status: AnalysisStatus;
  created_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  methodology_version: string;
  integrity: ImageIntegrityAssessment;
  imbalance: ClassImbalanceAssessment;
  metadata_consistency: MetadataConsistencyAssessment;
  duplicate_impact: DuplicateImpactAssessment;
  quality_score: TransparentQualityScore;
  findings: QualityFinding[];
  summary: string;
  warnings: string[];
}

export interface QualityAssessmentSummary {
  id: string;
  dataset_id: string;
  status: AnalysisStatus;
  created_at: string;
  completed_at?: string | null;
  overall_score: number;
  quality_tier: string;
  findings_count: number;
  critical_findings_count: number;
  high_findings_count: number;
}

export interface QualityAssessmentListResponse {
  total: number;
  items: QualityAssessmentSummary[];
  note?: string;
}

export interface QualityAssessmentStatusResponse {
  assessment_id: string;
  dataset_id: string;
  status: AnalysisStatus;
  created_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  methodology_version: string;
  error_message?: string | null;
}

