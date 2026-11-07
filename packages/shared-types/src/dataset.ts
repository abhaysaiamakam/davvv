/**
 * Shared Dataset types for CropLens
 */

export type DatasetSource =
  | 'icar_rice_maize'
  | 'paddy_doctor'
  | 'mendeley_rice'
  | 'plant_village'
  | 'plant_doc'
  | 'chilli_leaf'
  | 'kaggle_paddy'
  | 'evaluator_upload';

export type DatasetStatus =
  | 'registered'
  | 'discovering'
  | 'discovered'
  | 'validating'
  | 'validated'
  | 'invalid'
  | 'error';

export type ValidationStatus =
  | 'valid'
  | 'corrupt'
  | 'unreadable'
  | 'unsupported'
  | 'error';

export interface ClassDiscoveryInfo {
  class_name: string;
  relative_path: string;
  image_count: number;
}

export interface DatasetDiscoveryResult {
  dataset_id: string;
  dataset_name: string;
  dataset_source: DatasetSource;
  dataset_root_relative_path: string;
  discovery_status: DatasetStatus;
  discovered_image_files: number | null;
  discovered_class_directories: number | null;
  supported_extensions_encountered: string[];
  classes: ClassDiscoveryInfo[];
  unreadable_or_inaccessible_count: number;
  ingestion_timestamp: string;
  warnings: string[];
  validated_image_files: number | null;
}

export interface ImageValidationRecord {
  relative_path: string;
  file_size_bytes: number;
  format: string | null;
  width: number | null;
  height: number | null;
  aspect_ratio: number | null;
  color_mode: string | null;
  channels: number | null;
  status: ValidationStatus;
  error_message?: string | null;
}

export interface DimensionSummary {
  min_width: number | null;
  max_width: number | null;
  min_height: number | null;
  max_height: number | null;
  mean_width: number | null;
  mean_height: number | null;
  min_aspect_ratio: number | null;
  max_aspect_ratio: number | null;
}

export interface DatasetValidationResult {
  dataset_id: string;
  dataset_name: string;
  dataset_source: DatasetSource;
  validation_status: DatasetStatus;
  total_discovered_images: number;
  total_validated_images: number;
  total_corrupted_images: number;
  total_unreadable_images: number;
  total_processing_errors: number;
  total_unsupported_files: number;
  validation_timestamp: string;
  dimension_summary: DimensionSummary | null;
  color_mode_distribution: Record<string, number>;
  format_distribution: Record<string, number>;
  corrupted_files: ImageValidationRecord[];
  images?: ImageValidationRecord[];
  warnings: string[];
}

export interface DuplicateImageMember {
  relative_path: string;
  class_name: string;
  file_size_bytes: number;
  is_representative: boolean;
}

export interface ExactDuplicateGroup {
  group_id: string;
  sha256_hash: string;
  file_size_bytes: number;
  image_count: number;
  representative: DuplicateImageMember;
  duplicates: DuplicateImageMember[];
  classes_involved: string[];
  is_cross_class: boolean;
}

export interface ClassDuplicateMetric {
  class_name: string;
  total_images: number;
  duplicate_instances: number;
  duplicate_percentage: number;
}

export interface DuplicateAnalysisResult {
  dataset_id: string;
  dataset_name: string;
  analysis_timestamp: string;
  total_eligible_images: number;
  successfully_hashed_images: number;
  hashing_failures: number;
  unique_content_groups: number;
  exact_duplicate_groups: number;
  duplicate_instances_count: number;
  images_in_duplicate_groups: number;
  duplicate_percentage: number;
  cross_class_duplicate_groups: number;
  groups: ExactDuplicateGroup[];
  class_metrics: Record<string, ClassDuplicateMetric>;
  warnings: string[];
}

export type PerceptualHashAlgorithm = 'phash' | 'dhash' | 'ahash';

export interface NearDuplicateQueryConfig {
  algorithm?: PerceptualHashAlgorithm;
  hash_size?: number;
  distance_threshold?: number;
}

export interface NearDuplicateMember {
  relative_path: string;
  class_name: string;
  perceptual_hash: string;
  file_size_bytes: number;
  is_representative: boolean;
  hamming_distance_to_representative: number;
  similarity_to_representative: number;
}

export interface NearDuplicateGroup {
  group_id: string;
  algorithm: string;
  representative: NearDuplicateMember;
  near_duplicates: NearDuplicateMember[];
  image_count: number;
  classes_involved: string[];
  is_cross_class: boolean;
  max_distance_in_group: number;
  min_similarity_in_group: number;
}

export interface PerClassNearDuplicateMetric {
  class_name: string;
  total_images: number;
  near_duplicate_instances: number;
  near_duplicate_percentage: number;
}

export interface NearDuplicateAnalysisResult {
  dataset_id: string;
  dataset_name: string;
  analysis_timestamp: string;
  algorithm: string;
  hash_size: number;
  distance_threshold: number;
  similarity_threshold: number;
  total_eligible_images: number;
  successfully_hashed_images: number;
  hashing_failures: number;
  unique_perceptual_hashes: number;
  exact_duplicates_collapsed_count: number;
  unique_content_representatives_compared: number;
  pairwise_comparisons_performed: number;
  near_duplicate_groups: number;
  images_in_near_duplicate_groups: number;
  redundant_near_duplicate_instances: number;
  near_duplicate_percentage: number;
  cross_class_near_duplicate_groups: number;
  analysis_duration_ms: number;
  groups: NearDuplicateGroup[];
  class_metrics: Record<string, PerClassNearDuplicateMetric>;
  warnings: string[];
}

export interface DatasetMetadata {
  id: string;
  name: string;
  slug: string;
  description: string;
  source: DatasetSource;
  is_curated: boolean;
  is_uploaded: boolean;
  created_at: string;
  updated_at: string;
  crops: string[];
  status: DatasetStatus;
  tags: string[];
  total_images: number | null;
  total_classes: number | null;
  validated_image_files?: number | null;
  corrupted_image_files?: number | null;
  storage_relative_path?: string | null;
  discovery?: DatasetDiscoveryResult | null;
  validation?: DatasetValidationResult | null;
  duplicates?: DuplicateAnalysisResult | null;
  duplicate_groups_count?: number | null;
  near_duplicates?: NearDuplicateAnalysisResult | null;
  near_duplicate_groups_count?: number | null;
  current_version_id?: string | null;
  current_version_number?: number | null;
  total_versions?: number;
  content_fingerprint?: string | null;
}

export interface DatasetVersion {
  version_id: string;
  version_number: number;
  dataset_id: string;
  content_fingerprint: string;
  created_at: string;
  storage_relative_path: string;
  status: DatasetStatus;
  image_count: number | null;
  class_count: number | null;
  source_analysis_id: string | null;
  source_quality_id: string | null;
  source_eda_id: string | null;
  error_message: string | null;
}

export interface DatasetVersionListResponse {
  total: number;
  items: DatasetVersion[];
}

export interface DatasetRegisterRequest {
  id: string;
  name: string;
  description?: string;
  source?: DatasetSource;
  crops?: string[];
  tags?: string[];
}

export interface DatasetUploadResponse {
  dataset_id: string;
  version_id: string;
  version_number: number;
  job_id: string;
  status: DatasetStatus;
  message: string;
  is_duplicate_content?: boolean;
}

export interface DatasetListResponse {
  total: number;
  items: DatasetMetadata[];
  is_placeholder: boolean;
  note?: string;
}
