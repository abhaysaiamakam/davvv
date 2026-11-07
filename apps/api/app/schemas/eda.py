"""EDA (Exploratory Data Analysis) schemas for CropLens dataset intelligence."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class EdaStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EdaSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EdaFindingCategory(str, Enum):
    CLASS_DISTRIBUTION = "class_distribution"
    DIMENSION_CONSISTENCY = "dimension_consistency"
    FORMAT_DIVERSITY = "format_diversity"
    COLOR_SPACE = "color_space"
    ASPECT_RATIO = "aspect_ratio"
    FILE_SIZE = "file_size"
    DATASET_OVERVIEW = "dataset_overview"


class ClassDistributionEntry(BaseModel):
    class_name: str
    relative_path: str
    valid_image_count: int
    invalid_image_count: int
    percentage_of_valid: float
    percentage_of_total: float
    rank: int
    deviation_from_mean: float
    deviation_from_median: float


class ClassDistributionAnalysis(BaseModel):
    total_classes: int
    classes_with_images: int
    empty_classes: List[str]
    distribution: List[ClassDistributionEntry]
    min_count: int
    max_count: int
    mean_count: float
    median_count: float
    std_count: float
    variance: float
    coefficient_of_variation: Optional[float]
    imbalance_ratio: Optional[float]
    entropy: float
    normalized_entropy: Optional[float]
    gini_coefficient: float
    evaluation_notes: List[str]


class DimensionFrequencyEntry(BaseModel):
    width: int
    height: int
    count: int
    percentage: float


class DimensionStats(BaseModel):
    min_width: Optional[int]
    max_width: Optional[int]
    mean_width: Optional[float]
    median_width: Optional[float]
    std_width: Optional[float]
    min_height: Optional[int]
    max_height: Optional[int]
    mean_height: Optional[float]
    median_height: Optional[float]
    std_height: Optional[float]
    portrait_count: int
    landscape_count: int
    square_count: int
    portrait_pct: float
    landscape_pct: float
    square_pct: float
    unique_dimensions: int
    most_common_dimensions: List[DimensionFrequencyEntry]
    dimension_frequency: Dict[str, int]


class AspectRatioBin(BaseModel):
    label: str
    min_ar: float
    max_ar: float
    count: int
    percentage: float


class AspectRatioAnalysis(BaseModel):
    min_ar: Optional[float]
    max_ar: Optional[float]
    mean_ar: Optional[float]
    median_ar: Optional[float]
    std_ar: Optional[float]
    portrait_count: int
    landscape_count: int
    square_count: int
    extreme_low_count: int
    extreme_high_count: int
    distribution_bins: List[AspectRatioBin]


class FormatAnalysis(BaseModel):
    format_distribution: Dict[str, int]
    format_percentages: Dict[str, float]
    unique_format_count: int
    most_common_format: Optional[str]
    least_common_format: Optional[str]


class ColorAnalysis(BaseModel):
    color_mode_distribution: Dict[str, int]
    color_mode_percentages: Dict[str, float]
    grayscale_count: int
    rgb_count: int
    rgba_count: int
    rgb_mean: Optional[List[float]]
    rgb_std: Optional[List[float]]
    sampling_methodology: str
    sampling_seed: int


class FileSizeBin(BaseModel):
    label: str
    min_bytes: int
    max_bytes: int
    count: int
    percentage: float


class FileSizeStats(BaseModel):
    min_bytes: Optional[int]
    max_bytes: Optional[int]
    mean_bytes: Optional[float]
    median_bytes: Optional[float]
    std_bytes: Optional[float]
    total_bytes: int
    min_human: Optional[str]
    max_human: Optional[str]
    mean_human: Optional[str]
    total_human: str
    size_distribution_bins: List[FileSizeBin]


class ClassMetadataSummary(BaseModel):
    class_name: str
    valid_count: int
    dimension_stats: Optional[DimensionStats]
    format_distribution: Dict[str, int]
    color_mode_distribution: Dict[str, int]
    file_size_stats: Optional[FileSizeStats]
    mean_aspect_ratio: Optional[float]


class DatasetOverview(BaseModel):
    dataset_id: str
    dataset_name: str
    total_discovered_files: int
    total_valid_images: int
    total_invalid_images: int
    class_count: int
    classes_with_images: int
    empty_class_count: int
    format_count: int
    unique_dimension_count: int
    total_size_bytes: int
    total_size_human: str
    analysis_id: Optional[str]
    quality_assessment_id: Optional[str]
    eda_methodology_version: str


class EdaFinding(BaseModel):
    id: str
    category: EdaFindingCategory
    severity: EdaSeverity
    title: str
    explanation: str
    metric_name: str
    observed_value: Any
    expected_value: Optional[Any]
    threshold_used: Optional[Any]
    affected_classes: List[str]
    affected_image_samples: List[str]
    recommended_action: str
    evidence_references: List[str]
    methodology_version: str = "v1.0"


class EdaReport(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str
    source_analysis_id: Optional[str]
    source_quality_assessment_id: Optional[str]
    status: EdaStatus
    created_at: str
    completed_at: Optional[str]
    duration_ms: Optional[float]
    methodology_version: str = "v1.0"
    overview: DatasetOverview
    class_distribution: ClassDistributionAnalysis
    dimension_analysis: DimensionStats
    aspect_ratio_analysis: AspectRatioAnalysis
    format_analysis: FormatAnalysis
    color_analysis: ColorAnalysis
    file_size_analysis: FileSizeStats
    class_metadata: List[ClassMetadataSummary]
    findings: List[EdaFinding]
    warnings: List[str]


class EdaReportSummary(BaseModel):
    id: str
    dataset_id: str
    status: EdaStatus
    created_at: str
    completed_at: Optional[str]
    total_valid_images: int
    class_count: int
    findings_count: int


class EdaReportListResponse(BaseModel):
    total: int
    items: List[EdaReportSummary]
    note: Optional[str] = None


class EdaStatusResponse(BaseModel):
    eda_id: str
    dataset_id: str
    status: EdaStatus
    created_at: str
    completed_at: Optional[str]
    duration_ms: Optional[float]
    methodology_version: str
    error_message: Optional[str]

