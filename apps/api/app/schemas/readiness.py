"""
M10 — Dataset Readiness Assessment Schemas.

Provides typed structures for modality-aware, evidence-backed dataset readiness criteria,
dimension evaluation, task-specific context, and readiness status derivation.
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReadinessStatus(str, enum.Enum):
    READY = "ready"
    READY_WITH_CONCERNS = "ready_with_concerns"
    NEEDS_PREPROCESSING = "needs_preprocessing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_ASSESSED = "not_assessed"


class ReadinessDimension(str, enum.Enum):
    DATASET_INTEGRITY = "dataset_integrity"
    DATA_QUALITY = "data_quality"
    ANALYTICAL_SUITABILITY = "analytical_suitability"
    PREPROCESSING_STATUS = "preprocessing_status"
    FEATURE_READINESS = "feature_readiness"


class TaskContext(BaseModel):
    """Optional user-provided task context for target-aware readiness evaluation."""

    task_type: Optional[str] = Field(
        default=None,
        description="'classification', 'regression', 'forecasting', 'object_detection', or 'exploratory'",
    )
    target_column: Optional[str] = Field(
        default=None, description="Optional primary label or target variable column name"
    )
    analytical_goal: Optional[str] = Field(
        default=None, description="Free-text analytical or model training objective"
    )


class ReadinessDimensionAssessment(BaseModel):
    """Evaluation breakdown for a single dataset readiness dimension."""

    dimension: ReadinessDimension
    status: ReadinessStatus
    score: int = Field(..., ge=0, le=100, description="Dimension readiness score (0-100)")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Supporting quantitative metrics")
    blocking_issues: List[str] = Field(default_factory=list, description="Critical defects preventing deployment")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings or concerns")
    recommendations: List[str] = Field(default_factory=list, description="Actionable recommendations")


class DatasetReadinessAssessment(BaseModel):
    """Unified, evidence-backed readiness assessment for a dataset version."""

    dataset_id: str
    version_id: str
    dataset_name: str
    overall_status: ReadinessStatus
    overall_score: int = Field(..., ge=0, le=100, description="Weighted composite readiness score (0-100)")
    task_context: Optional[TaskContext] = None
    dimensions: List[ReadinessDimensionAssessment] = Field(default_factory=list)
    key_strengths: List[str] = Field(default_factory=list)
    critical_blockers: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    evaluated_at: str


class ReadinessAssessRequest(BaseModel):
    """Request payload for evaluating dataset readiness."""

    dataset_id: str
    version_id: Optional[str] = Field(default=None, description="Target dataset version ID (defaults to active/latest)")
    task_context: Optional[TaskContext] = None
