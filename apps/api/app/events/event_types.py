"""
M6 — Event-Driven Architecture event types and models.

Defines decoupled lifecycle event structures for CropLens intelligence engines.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DatasetEventType:
    DATASET_UPLOADED = "dataset.uploaded"
    DATASET_VALIDATED = "dataset.validated"
    DATASET_VERSION_CREATED = "dataset.version.created"
    DATASET_ANALYSIS_QUEUED = "dataset.analysis.queued"
    DATASET_ANALYSIS_STARTED = "dataset.analysis.started"
    DATASET_ANALYSIS_COMPLETED = "dataset.analysis.completed"
    DATASET_ANALYSIS_FAILED = "dataset.analysis.failed"
    DATASET_VERSION_CHANGED = "dataset.version.changed"
    DATASET_COMPARISON_STALE = "dataset.comparison.stale"
    DATASET_VISUALIZATION_COMPLETED = "dataset.visualization.completed"
    DATASET_VISUALIZATION_FAILED = "dataset.visualization.failed"
    DATASET_INSIGHTS_COMPLETED = "dataset.insights.completed"
    DATASET_INSIGHTS_FAILED = "dataset.insights.failed"
    DATASET_PREPROCESSING_STARTED = "dataset.preprocessing.started"
    DATASET_PREPROCESSING_COMPLETED = "dataset.preprocessing.completed"
    DATASET_PREPROCESSING_FAILED = "dataset.preprocessing.failed"
    DATASET_READINESS_ASSESSED = "dataset.readiness.assessed"
    DATASET_REPORT_GENERATED = "dataset.report.generated"
    DATASET_REPORT_FAILED = "dataset.report.failed"


class DatasetLifecycleEvent(BaseModel):
    """Structured, immutable lifecycle event payload."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Event type identifier, e.g. dataset.analysis.completed")
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    dataset_id: str = Field(..., description="Target dataset identifier")
    version_id: Optional[str] = Field(default=None, description="Target dataset version identifier")
    job_id: Optional[str] = Field(default=None, description="Associated processing job identifier")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event-specific metadata without host paths")

