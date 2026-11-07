"""
M6 — Processing Job schemas.

Provides lifecycle tracking and progress reporting for asynchronous dataset processing.
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(str, enum.Enum):
    QUEUED = "queued"
    EXTRACTION = "extraction"
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    EXACT_DUPLICATES = "exact_duplicates"
    NEAR_DUPLICATES = "near_duplicates"
    UNIFIED_ANALYSIS = "unified_analysis"
    QUALITY_LAB = "quality_lab"
    EDA_ENGINE = "eda_engine"
    VISUALIZATIONS = "visualizations"
    INSIGHTS = "insights"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingJob(BaseModel):
    """Full lifecycle tracking record for an asynchronous dataset analysis job."""

    job_id: str = Field(..., description="Unique job identifier")
    dataset_id: str = Field(..., description="Target dataset identifier")
    dataset_version: str = Field(..., description="Target dataset version identifier")
    job_type: str = Field(default="analysis_pipeline", description="Type of job executed")
    status: JobStatus = Field(default=JobStatus.QUEUED, description="Current execution status")
    current_stage: JobStage = Field(default=JobStage.QUEUED, description="Active processing stage")
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Estimated completion percentage")
    created_at: str = Field(..., description="ISO 8601 job submission timestamp")
    started_at: Optional[str] = Field(default=None, description="ISO 8601 job start timestamp")
    completed_at: Optional[str] = Field(default=None, description="ISO 8601 job completion timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Total execution duration in milliseconds")
    error_code: Optional[str] = Field(default=None, description="Error code if job failed")
    error_message: Optional[str] = Field(default=None, description="Sanitized error description")
    retry_count: int = Field(default=0, ge=0, description="Number of execution attempts")
    artifact_refs: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="References to produced M2, M3, and M4 analytical artifacts",
    )


class JobStatusResponse(BaseModel):
    """Lightweight job execution status response."""

    job_id: str
    dataset_id: str
    dataset_version: str
    status: JobStatus
    current_stage: JobStage
    progress_pct: float
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None


class JobListResponse(BaseModel):
    """Paginated or complete list of processing jobs."""

    total: int
    items: List[ProcessingJob]

