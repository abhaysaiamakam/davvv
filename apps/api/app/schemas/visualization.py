"""
Visualization schemas for CropLens dataset intelligence.

Defines strongly typed, frontend-ready visualization specifications,
chart-ready data payloads, and collection responses.
"""
from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChartType(str, Enum):
    BAR = "bar"
    HISTOGRAM = "histogram"
    BOX_PLOT = "box_plot"
    SCATTER = "scatter"
    LINE = "line"
    HEATMAP = "heatmap"
    PIE = "pie"
    IMAGE_GRID = "image_grid"


class VisualizationCategory(str, Enum):
    CLASS_DISTRIBUTION = "class_distribution"
    IMAGE_GEOMETRY = "image_geometry"
    FORMAT_AND_COLOR = "format_and_color"
    DATA_QUALITY = "data_quality"
    DUPLICATES = "duplicates"
    TABULAR_DISTRIBUTION = "tabular_distribution"
    TABULAR_CORRELATION = "tabular_correlation"
    TIME_SERIES = "time_series"
    ANNOTATIONS = "annotations"


class AxisScale(str, Enum):
    LINEAR = "linear"
    LOG = "log"
    CATEGORY = "category"
    TIME = "time"


class AxisSpec(BaseModel):
    name: str = Field(..., description="Data key representing this axis")
    label: str = Field(..., description="Human-readable axis title")
    scale: AxisScale = Field(default=AxisScale.LINEAR, description="Scale type: linear, log, category, time")
    unit: Optional[str] = Field(default=None, description="Optional unit of measurement (e.g. px, MB, %)")
    min_val: Optional[float] = Field(default=None, description="Suggested lower bound")
    max_val: Optional[float] = Field(default=None, description="Suggested upper bound")


class SeriesSpec(BaseModel):
    name: str = Field(..., description="Human-readable series name")
    data_key: str = Field(..., description="Key in chart_data objects for series values")
    color: Optional[str] = Field(default=None, description="Suggested hex color or color token")
    chart_type: Optional[ChartType] = Field(default=None, description="Chart type override if mixed")
    unit: Optional[str] = Field(default=None, description="Series unit of measurement")


class VisualizationSpecification(BaseModel):
    """
    Standard visualization specification for frontend rendering.
    Contains metadata, axis definitions, series definitions, and pre-computed chart_data.
    """

    visualization_id: str = Field(..., description="Deterministic, unique visualization identifier")
    dataset_id: str = Field(..., description="Target dataset identifier")
    dataset_version: str = Field(..., description="Target dataset version identifier")
    title: str = Field(..., description="Concise, informative chart title")
    description: str = Field(..., description="Detailed description of what the visualization illustrates")
    chart_type: ChartType = Field(..., description="Canonical chart type vocabulary")
    category: VisualizationCategory = Field(..., description="Functional analytical category")
    x_axis: Optional[AxisSpec] = Field(default=None, description="X-axis specification")
    y_axis: Optional[AxisSpec] = Field(default=None, description="Y-axis specification")
    series: List[SeriesSpec] = Field(default_factory=list, description="Series mappings")
    chart_data: List[Dict[str, Any]] = Field(default_factory=list, description="Chart-ready data rows/objects")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Domain-specific metrics, notes, and baselines")
    generated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    source_artifacts: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="References to source M2, M3, and M4 analytical artifact IDs",
    )


class VisualizationCollection(BaseModel):
    """Persisted collection of all generated visualizations for a dataset version."""

    id: str = Field(..., description="Unique collection identifier")
    dataset_id: str = Field(..., description="Target dataset identifier")
    dataset_version: str = Field(..., description="Target dataset version identifier")
    total: int = Field(default=0, description="Total visualizations in collection")
    status: str = Field(default="completed", description="Generation status: completed, partial, failed")
    items: List[VisualizationSpecification] = Field(default_factory=list, description="Visualization specifications")
    error_message: Optional[str] = Field(default=None, description="Error reason if generation failed")
    generated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class VisualizationCollectionResponse(BaseModel):
    """API response model for dataset visualization queries."""

    dataset_id: str
    dataset_version: str
    total: int
    status: str
    items: List[VisualizationSpecification]
    error_message: Optional[str] = None

