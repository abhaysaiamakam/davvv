"""
M5 — Dataset Comparison Engine schemas.

All schemas follow Pydantic v2 conventions. Optional fields use None to signal
"not computed" — a computed value of 0 is never substituted for a missing value.
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ComparisonStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ComparisonFindingCategory(str, enum.Enum):
    SCALE = "scale"
    CLASS_DISTRIBUTION = "class_distribution"
    IMAGE_CHARACTERISTICS = "image_characteristics"
    DATA_QUALITY = "data_quality"
    DUPLICATE_IMPACT = "duplicate_impact"


class ComparisonSeverity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComparisonFreshness(str, enum.Enum):
    CURRENT = "current"
    STALE = "stale"
    PENDING = "pending"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Primitive building block
# ---------------------------------------------------------------------------


class MetricComparison(BaseModel):
    """Side-by-side comparison of a single numeric metric from two datasets."""

    dataset_a_value: Optional[float] = Field(
        None, description="Metric value for dataset A. Null if not computed."
    )
    dataset_b_value: Optional[float] = Field(
        None, description="Metric value for dataset B. Null if not computed."
    )
    absolute_diff: Optional[float] = Field(
        None, description="dataset_b_value - dataset_a_value. Null if either value is absent."
    )
    pct_change: Optional[float] = Field(
        None,
        description=(
            "Percentage change from A to B: ((B - A) / |A|) * 100. "
            "Null when A is 0 or either value is absent."
        ),
    )
    is_available: bool = Field(
        True, description="False when neither dataset produced this metric."
    )


# ---------------------------------------------------------------------------
# Overview comparison
# ---------------------------------------------------------------------------


class DatasetOverviewComparison(BaseModel):
    """High-level size and class structure comparison."""

    total_images: MetricComparison
    valid_images: MetricComparison
    corrupted_images: MetricComparison
    total_classes: MetricComparison
    images_per_class_mean: MetricComparison
    exact_duplicate_pct: MetricComparison
    near_duplicate_pct: MetricComparison


# ---------------------------------------------------------------------------
# Class distribution comparison
# ---------------------------------------------------------------------------


class SharedClassComparison(BaseModel):
    """Per-class image count comparison for a class present in both datasets."""

    class_name: str
    count_a: int
    count_b: int
    absolute_diff: int = Field(description="count_b - count_a")
    pct_change: Optional[float] = Field(
        None, description="((count_b - count_a) / count_a) * 100. Null when count_a == 0."
    )


class ClassAlignmentSummary(BaseModel):
    """Describes how the class namespaces of two datasets overlap."""

    total_classes_a: int
    total_classes_b: int
    shared_classes: List[str] = Field(description="Classes present in both datasets.")
    only_in_a: List[str] = Field(description="Classes present only in dataset A.")
    only_in_b: List[str] = Field(description="Classes present only in dataset B.")
    shared_class_comparisons: List[SharedClassComparison]
    class_overlap_pct: Optional[float] = Field(
        None,
        description=(
            "100 * |shared| / |union|. Null when both datasets have zero classes."
        ),
    )
    empty_classes_a: int = Field(0, description="Classes with 0 images in dataset A.")
    empty_classes_b: int = Field(0, description="Classes with 0 images in dataset B.")


class ClassDistributionComparison(BaseModel):
    """Full class distribution comparison including EDA-derived statistics."""

    alignment: ClassAlignmentSummary
    # EDA-derived distribution statistics
    entropy_a: MetricComparison
    entropy_b: MetricComparison
    gini_coefficient: MetricComparison
    imbalance_ratio: MetricComparison
    coefficient_of_variation: MetricComparison
    normalized_entropy: MetricComparison
    # Fallback info
    is_available: bool = True
    fallback_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Image characteristics comparison
# ---------------------------------------------------------------------------


class ImageCharacteristicsComparison(BaseModel):
    """Comparison of low-level image properties."""

    # Dimensions (median)
    median_width: MetricComparison
    median_height: MetricComparison
    # Aspect ratio (mean)
    mean_aspect_ratio: MetricComparison
    # File size (median bytes)
    median_file_size_bytes: MetricComparison
    mean_file_size_bytes: MetricComparison
    # Colour mode distribution (dominant mode)
    dominant_color_mode_a: Optional[str] = None
    dominant_color_mode_b: Optional[str] = None
    # Format distribution (dominant format)
    dominant_format_a: Optional[str] = None
    dominant_format_b: Optional[str] = None
    is_available: bool = True
    fallback_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Data quality comparison
# ---------------------------------------------------------------------------


class DataQualityComparison(BaseModel):
    """Comparison of data quality metrics from M2 and M3."""

    # M2-derived (always available when M2 exists)
    exact_duplicate_groups: MetricComparison
    near_duplicate_groups: MetricComparison
    total_redundant_images: MetricComparison
    clean_unique_images: MetricComparison
    # M3-derived (may be absent)
    overall_quality_score: MetricComparison
    integrity_rate: MetricComparison
    quality_tier_a: Optional[str] = None
    quality_tier_b: Optional[str] = None
    # M3 findings count (integer comparison)
    critical_findings_count: MetricComparison
    # Availability flags
    is_quality_available: bool = Field(
        False, description="True when M3 quality assessment is available for at least one dataset."
    )
    is_duplicate_available: bool = Field(
        True, description="True when M2 duplicate metrics are available."
    )
    fallback_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


class ComparisonFinding(BaseModel):
    """An evidence-backed, actionable finding produced by the comparison engine."""

    id: str = Field(description="Stable string literal identifier (not a UUID).")
    category: ComparisonFindingCategory
    severity: ComparisonSeverity
    title: str
    explanation: str
    metric_name: Optional[str] = None
    value_a: Optional[float] = None
    value_b: Optional[float] = None
    absolute_diff: Optional[float] = None
    pct_change: Optional[float] = None
    threshold_used: Optional[float] = None
    recommended_action: Optional[str] = None
    evidence_references: List[str] = Field(default_factory=list)
    methodology_version: str = "v1.0"


# ---------------------------------------------------------------------------
# Source references
# ---------------------------------------------------------------------------


class ComparisonSourceRefs(BaseModel):
    """IDs of the upstream reports consumed by this comparison."""

    analysis_a_id: Optional[str] = None
    analysis_b_id: Optional[str] = None
    quality_a_id: Optional[str] = None
    quality_b_id: Optional[str] = None
    eda_a_id: Optional[str] = None
    eda_b_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------


class DatasetComparisonReport(BaseModel):
    """Full pairwise dataset comparison report (M5 primary output)."""

    id: str
    dataset_a_id: str
    dataset_b_id: str
    dataset_a_name: str
    dataset_b_name: str
    status: ComparisonStatus
    freshness_status: ComparisonFreshness = ComparisonFreshness.CURRENT
    source_version_a: Optional[str] = None
    source_version_b: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    methodology_version: str = "v1.0"
    source_refs: ComparisonSourceRefs
    overview: Optional[DatasetOverviewComparison] = None
    class_distribution: Optional[ClassDistributionComparison] = None
    image_characteristics: Optional[ImageCharacteristicsComparison] = None
    data_quality: Optional[DataQualityComparison] = None
    findings: List[ComparisonFinding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# List / status / request helpers
# ---------------------------------------------------------------------------


class DatasetComparisonSummary(BaseModel):
    """Lightweight comparison record used in list responses."""

    id: str
    dataset_a_id: str
    dataset_b_id: str
    dataset_a_name: str
    dataset_b_name: str
    status: ComparisonStatus
    freshness_status: ComparisonFreshness = ComparisonFreshness.CURRENT
    source_version_a: Optional[str] = None
    source_version_b: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    findings_count: int = 0
    dataset_a_valid_images: Optional[int] = None
    dataset_b_valid_images: Optional[int] = None


class DatasetComparisonListResponse(BaseModel):
    total: int
    items: List[DatasetComparisonSummary]
    note: Optional[str] = None


class ComparisonStatusResponse(BaseModel):
    comparison_id: str
    dataset_a_id: str
    dataset_b_id: str
    status: ComparisonStatus
    freshness_status: ComparisonFreshness = ComparisonFreshness.CURRENT
    source_version_a: Optional[str] = None
    source_version_b: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    methodology_version: str = "v1.0"
    error_message: Optional[str] = None


class ComparisonCreateRequest(BaseModel):
    dataset_a_id: str = Field(description="ID of the first dataset.")
    dataset_b_id: str = Field(description="ID of the second dataset.")
    force_refresh: bool = Field(
        False,
        description="When true, discard any cached comparison and recompute from scratch.",
    )


class ComparisonFreshnessResponse(BaseModel):
    comparison_id: str
    dataset_a_id: str
    dataset_b_id: str
    freshness_status: ComparisonFreshness
    is_stale: bool
    source_analysis_a_id: Optional[str] = None
    current_analysis_a_id: Optional[str] = None
    source_analysis_b_id: Optional[str] = None
    current_analysis_b_id: Optional[str] = None
    reason: Optional[str] = None

