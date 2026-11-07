"""
M7 — Dataset Findings & Insights Intelligence Engine schemas.

Provides typed structures for dataset-agnostic, evidence-backed analytical findings.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InsightSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class InsightCategory(str, Enum):
    CLASS_DISTRIBUTION = "class_distribution"
    IMAGE_QUALITY = "image_quality"
    DUPLICATE_DATA = "duplicate_data"
    DATA_QUALITY = "data_quality"
    MISSING_VALUES = "missing_values"
    OUTLIERS = "outliers"
    DISTRIBUTION = "distribution"
    CORRELATION = "correlation"
    TIME_SERIES = "time_series"
    ANNOTATION_QUALITY = "annotation_quality"
    DATASET_COVERAGE = "dataset_coverage"
    DATASET_READINESS = "dataset_readiness"


class InsightConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InsightEvidence(BaseModel):
    """Traceable evidence backing a single insight."""

    metric: str = Field(..., description="Name of the computed metric")
    value: Any = Field(..., description="Observed value of the metric")
    unit: Optional[str] = Field(default=None, description="Unit of measurement (e.g. 'images', 'percent')")
    threshold: Optional[float] = Field(default=None, description="Decision threshold that triggered this finding")
    source_artifact: str = Field(
        ..., description="Name of the upstream artifact (e.g. 'eda_report', 'quality_assessment', 'analysis')"
    )
    source_path: str = Field(
        ..., description="Dot-separated attribute path within the artifact (e.g. 'class_distribution.imbalance_ratio')"
    )
    explanation: str = Field(..., description="Human-readable explanation of how this metric relates to the insight")


class DatasetInsight(BaseModel):
    """A single, evidence-backed dataset insight produced by M7."""

    insight_id: str = Field(..., description="Deterministic insight identifier (e.g. 'ins-class_imbalance-ds1-v1')")
    dataset_id: str = Field(..., description="Associated dataset identifier")
    version_id: str = Field(..., description="Associated dataset version identifier")
    category: InsightCategory = Field(..., description="Insight classification category")
    severity: InsightSeverity = Field(..., description="Severity level for prioritisation")
    confidence: InsightConfidence = Field(..., description="Analyzer confidence in this finding")
    title: str = Field(..., description="Concise, human-readable insight title")
    summary: str = Field(..., description="One-sentence finding summary")
    explanation: str = Field(..., description="Detailed explanation of the finding and its impact")
    evidence: List[InsightEvidence] = Field(default_factory=list, description="Traceable supporting evidence")
    affected_classes: List[str] = Field(default_factory=list, description="Dataset classes affected by this insight")
    affected_columns: List[str] = Field(default_factory=list, description="Tabular columns affected (empty for image datasets)")
    affected_files: List[str] = Field(default_factory=list, description="Relative paths of affected files (sample)")
    impact: str = Field(..., description="Explanation of downstream ML/training impact")
    recommended_action: str = Field(..., description="Evidence-backed, actionable recommendation")
    limitations: str = Field(
        default="",
        description="Known gaps or deferred analysis (e.g. image clarity deferred to future milestone)",
    )
    created_at: str = Field(..., description="ISO 8601 insight creation timestamp")
    analyzer_id: str = Field(..., description="Identifier of the analyzer that produced this insight")
    rule_id: str = Field(..., description="Deterministic rule identifier within the analyzer")


class InsightCollection(BaseModel):
    """Complete set of M7 insights generated for a dataset version."""

    id: str = Field(..., description="Unique insight collection identifier")
    dataset_id: str = Field(..., description="Associated dataset identifier")
    dataset_version: str = Field(..., description="Associated dataset version identifier")
    status: str = Field(..., description="Generation status: 'completed' or 'failed'")
    total: int = Field(..., description="Total number of insights generated")
    items: List[DatasetInsight] = Field(default_factory=list, description="All generated insights")
    error_message: Optional[str] = Field(default=None, description="Error description if generation failed")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp")
    source_analysis_id: Optional[str] = Field(default=None, description="Upstream M2 analysis ID")
    source_quality_id: Optional[str] = Field(default=None, description="Upstream M3 quality assessment ID")
    source_eda_id: Optional[str] = Field(default=None, description="Upstream M4 EDA report ID")


class InsightCollectionResponse(BaseModel):
    """Filtered view of an InsightCollection, returned by API endpoints."""

    dataset_id: str = Field(..., description="Associated dataset identifier")
    dataset_version: str = Field(..., description="Associated dataset version identifier")
    status: str = Field(..., description="Collection status: 'completed' or 'failed'")
    total: int = Field(..., description="Total insights after filtering")
    items: List[DatasetInsight] = Field(default_factory=list, description="Filtered insights")
    error_message: Optional[str] = Field(default=None, description="Error description if generation failed")
    filtered_category: Optional[str] = Field(default=None, description="Applied category filter")
    filtered_severity: Optional[str] = Field(default=None, description="Applied severity filter")

