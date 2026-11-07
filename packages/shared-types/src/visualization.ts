/**
 * TypeScript definitions for CropLens Visualization Specification Engine.
 * Mirrors Python schemas in apps/api/app/schemas/visualization.py.
 */

export type ChartType =
  | 'bar'
  | 'histogram'
  | 'box_plot'
  | 'scatter'
  | 'line'
  | 'heatmap'
  | 'pie'
  | 'image_grid';

export type VisualizationCategory =
  | 'class_distribution'
  | 'image_geometry'
  | 'format_and_color'
  | 'data_quality'
  | 'duplicates'
  | 'tabular_distribution'
  | 'tabular_correlation'
  | 'time_series'
  | 'annotations';

export type AxisScale = 'linear' | 'log' | 'category' | 'time';

export interface AxisSpec {
  name: string;
  label: string;
  scale?: AxisScale;
  unit?: string | null;
  min_val?: number | null;
  max_val?: number | null;
}

export interface SeriesSpec {
  name: string;
  data_key: string;
  color?: string | null;
  chart_type?: ChartType | null;
  unit?: string | null;
}

export interface VisualizationSpecification {
  visualization_id: string;
  dataset_id: string;
  dataset_version: string;
  title: string;
  description: string;
  chart_type: ChartType;
  category: VisualizationCategory;
  x_axis?: AxisSpec | null;
  y_axis?: AxisSpec | null;
  series: SeriesSpec[];
  chart_data: Record<string, any>[];
  metadata: Record<string, any>;
  generated_at: string;
  source_artifacts?: Record<string, string | null>;
}

export interface VisualizationCollection {
  id: string;
  dataset_id: string;
  dataset_version: string;
  total: number;
  status: string;
  items: VisualizationSpecification[];
  error_message?: string | null;
  generated_at: string;
}

export interface VisualizationCollectionResponse {
  dataset_id: string;
  dataset_version: string;
  total: number;
  status: string;
  items: VisualizationSpecification[];
  error_message?: string | null;
}

