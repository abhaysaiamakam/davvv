import type { PreprocessingOperationConfig } from './preprocessing';

export interface ImageClassCount {
  class_name: string;
  image_count: number;
}

export interface DatasetImage {
  image_id: string;
  filename: string;
  class_name: string;
  width: number | null;
  height: number | null;
  file_size_bytes: number;
  format: string | null;
  color_mode: string | null;
  status: 'valid' | 'corrupt' | 'unreadable' | string;
  thumbnail_url: string;
  preview_url: string;
}

export interface DatasetImageListResponse {
  dataset_id: string;
  version_id: string;
  modality: 'image' | 'non_image';
  class_structure: 'directory' | 'unclassified';
  total: number;
  page: number;
  page_size: number;
  classes: ImageClassCount[];
  items: DatasetImage[];
}

export interface ImagePreprocessingPreviewResponse {
  dataset_id: string;
  version_id: string;
  image_id: string;
  operation_type: string;
  original_data_url: string;
  preview_data_url: string;
  original_metadata: Record<string, unknown>;
  preview_metadata: Record<string, unknown>;
  warning?: string | null;
}

export interface ImageAnnotation {
  annotation_id: string;
  class_id: string;
  label: string | null;
  x: number;
  y: number;
  width: number;
  height: number;
  coordinate_system: 'pixels';
  confidence?: number | null;
}

export interface AnnotationClassCount {
  class_id: string;
  label: string | null;
  annotation_count: number;
  image_count: number;
}

export interface ImageAnnotationResponse {
  dataset_id: string;
  version_id: string;
  image_id: string;
  annotation_format: 'coco' | 'yolo' | 'none' | string;
  image_width: number | null;
  image_height: number | null;
  annotation_count: number;
  annotations: ImageAnnotation[];
  classes: AnnotationClassCount[];
}

export type ImagePreviewOperation = Pick<PreprocessingOperationConfig, 'operation_type' | 'parameters'>;
