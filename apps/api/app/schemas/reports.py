"""
M10 — Unified Analytical Report & Export Schemas.

Provides typed structures for comprehensive analytical reports, executive summaries,
data quality, EDA, insights, preprocessing history, feature engineering, methodology,
provenance, and export configurations.
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.readiness import DatasetReadinessAssessment, ReadinessStatus, TaskContext


class ReportExportFormat(str, enum.Enum):
    JSON = "json"
    PDF = "pdf"
    HTML = "html"


class ReportStatus(str, enum.Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutiveSummary(BaseModel):
    """High-level synthesis for technical decision makers and evaluation panels."""

    dataset_name: str
    dataset_modality: str
    dataset_version: str
    total_files: int
    total_bytes: int
    main_objective: str
    key_findings: List[str] = Field(default_factory=list)
    quality_concerns: List[str] = Field(default_factory=list)
    readiness_status: ReadinessStatus
    recommended_next_steps: List[str] = Field(default_factory=list)


class DatasetOverviewSection(BaseModel):
    """Detailed structural catalog of dataset metadata and file structure."""

    dataset_id: str
    dataset_name: str
    version_id: str
    version_number: int
    modality: str
    is_curated: bool
    is_uploaded: bool
    created_at: str
    total_files: int
    total_bytes: int
    item_count: Optional[int] = None
    classes: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    content_fingerprint: Optional[str] = None


class QualitySection(BaseModel):
    """Integration of M3 Data Quality Lab findings."""

    quality_score: Optional[int] = None
    quality_tier: Optional[str] = None
    missing_values_count: int = 0
    corrupted_files_count: int = 0
    duplicate_count: int = 0
    class_imbalance_ratio: Optional[float] = None
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class EdaSection(BaseModel):
    """Integration of M4 Exploratory Data Analysis & Chart Specifications."""

    distributions_summary: Dict[str, Any] = Field(default_factory=dict)
    relationships_summary: Dict[str, Any] = Field(default_factory=dict)
    visualization_count: int = 0
    visualization_refs: List[str] = Field(default_factory=list)
    eda_findings: List[Dict[str, Any]] = Field(default_factory=list)


class InsightsSection(BaseModel):
    """Integration of M7 Dataset Findings & Insights."""

    total_insights: int = 0
    category_counts: Dict[str, int] = Field(default_factory=dict)
    insights: List[Dict[str, Any]] = Field(default_factory=list)


class PreprocessingSection(BaseModel):
    """Integration of M8 Preprocessing & Cleaning History."""

    operations_applied_count: int = 0
    applied_operations: List[Dict[str, Any]] = Field(default_factory=list)
    source_version_id: Optional[str] = None
    derived_version_id: Optional[str] = None
    remaining_quality_concerns: List[str] = Field(default_factory=list)


class FeatureEngineeringSection(BaseModel):
    """Integration of M9 Feature Engineering & Selection."""

    generated_features_count: int = 0
    features_generated: List[str] = Field(default_factory=list)
    selected_features: List[str] = Field(default_factory=list)
    removed_features: List[str] = Field(default_factory=list)
    pca_component_count: Optional[int] = None
    pca_explained_variance_ratio: Optional[List[float]] = None
    feature_operations: List[Dict[str, Any]] = Field(default_factory=list)


class MethodologyStep(BaseModel):
    """Single step in the reproducible methodology execution graph."""

    step_number: int
    stage_name: str
    operation_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    input_version_id: Optional[str] = None
    output_version_id: Optional[str] = None
    affected_count: Optional[int] = None
    timestamp: str


class MethodologySection(BaseModel):
    """Reproducible execution trail documenting how CropLens analyzed the dataset."""

    workflow_summary: str
    steps: List[MethodologyStep] = Field(default_factory=list)
    execution_engine: str = "CropLens Automated Intelligence Engine v0.1.0"
    reproducibility_notes: List[str] = Field(default_factory=list)


class ReportProvenance(BaseModel):
    """Immutable audit trail for report versioning, source fingerprints, and artifact binding."""

    report_id: str
    dataset_id: str
    version_id: str
    content_fingerprint: Optional[str] = None
    created_at: str
    schema_version: str = "1.0.0"
    artifact_refs: Dict[str, str] = Field(default_factory=dict)
    generator_status: ReportStatus = ReportStatus.COMPLETED


class AnalyticalReport(BaseModel):
    """Complete, unified analytical report object for CropLens dataset intelligence."""

    report_id: str
    dataset_id: str
    version_id: str
    title: str
    provenance: ReportProvenance
    executive_summary: ExecutiveSummary
    dataset_overview: DatasetOverviewSection
    quality_section: QualitySection
    eda_section: EdaSection
    insights_section: InsightsSection
    preprocessing_section: PreprocessingSection
    feature_engineering_section: FeatureEngineeringSection
    readiness_section: DatasetReadinessAssessment
    methodology_section: MethodologySection
    conclusion_section: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ReportGenerateRequest(BaseModel):
    """Request payload for generating an analytical report."""

    dataset_id: str
    version_id: Optional[str] = Field(default=None, description="Target dataset version ID (defaults to active/latest)")
    title: Optional[str] = Field(default=None, description="Custom report title")
    task_context: Optional[TaskContext] = None
    force_refresh: bool = Field(default=False, description="Recompute report even if cached report exists")


class ReportListResponse(BaseModel):
    """List of analytical reports for a dataset."""

    total: int
    items: List[AnalyticalReport]
