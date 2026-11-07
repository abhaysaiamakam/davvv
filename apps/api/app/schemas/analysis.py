from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.dataset import (
    DatasetDiscoveryResult,
    DatasetValidationResult,
    DuplicateAnalysisResult,
    NearDuplicateAnalysisResult,
    NearDuplicateQueryConfig,
)


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisConfig(BaseModel):
    near_duplicate_config: Optional[NearDuplicateQueryConfig] = Field(
        default=None,
        description="Configuration for perceptual near-duplicate detection",
    )
    force_refresh: bool = Field(
        default=False,
        description="Whether to recompute stages even if existing cached/persisted results exist",
    )
    include_near_duplicates: bool = Field(
        default=True,
        description="Whether to execute perceptual near-duplicate detection stage",
    )


class UnifiedAnalysisMetrics(BaseModel):
    # Discovery metrics (null if discovery not run)
    total_files_discovered: Optional[int] = Field(
        default=None,
        description="Total image files discovered in dataset root",
    )
    total_classes_discovered: Optional[int] = Field(
        default=None,
        description="Total class directories discovered",
    )

    # Validation metrics (null if validation not run)
    total_validated_images: Optional[int] = Field(
        default=None,
        description="Total decodable valid images (canonical denominator for duplicate ratios)",
    )
    total_corrupted_images: Optional[int] = Field(
        default=None,
        description="Total corrupted/truncated image files",
    )
    total_unreadable_images: Optional[int] = Field(
        default=None,
        description="Total unreadable/zero-byte image files",
    )
    total_processing_errors: Optional[int] = Field(
        default=None,
        description="Total images with processing/decoding errors",
    )
    total_unsupported_files: Optional[int] = Field(
        default=None,
        description="Total files with unsupported extensions",
    )

    # Exact duplicate metrics (null if exact dups not run)
    exact_duplicate_groups: Optional[int] = Field(
        default=None,
        description="Count of exact duplicate clusters (SHA-256 byte-identical)",
    )
    exact_duplicate_redundant_instances: Optional[int] = Field(
        default=None,
        description="Count of redundant exact copies beyond group representatives",
    )
    exact_duplicate_percentage: Optional[float] = Field(
        default=None,
        description="Exact redundant copies as % of valid images (denominator: total_validated_images)",
    )
    cross_class_exact_duplicate_groups: Optional[int] = Field(
        default=None,
        description="Exact duplicate groups that cross disease/crop class boundaries",
    )

    # Near duplicate metrics (null if near dups not run)
    near_duplicate_groups: Optional[int] = Field(
        default=None,
        description="Count of perceptual near-duplicate groups",
    )
    near_duplicate_images_in_groups: Optional[int] = Field(
        default=None,
        description="Total images participating in near-duplicate groups",
    )
    near_duplicate_redundant_instances: Optional[int] = Field(
        default=None,
        description="Redundant near-duplicate instances beyond group representatives",
    )
    near_duplicate_percentage: Optional[float] = Field(
        default=None,
        description="Redundant near-duplicate instances as % of valid images (denominator: total_validated_images)",
    )
    cross_class_near_duplicate_groups: Optional[int] = Field(
        default=None,
        description="Near-duplicate groups that cross disease/crop class boundaries",
    )

    # Consolidated integrity metrics (avoiding double-counting)
    # Exact copies are collapsed before near-duplicate candidate comparison,
    # ensuring exact redundant instances and near-duplicate redundant instances are disjoint sets.
    total_redundant_images: Optional[int] = Field(
        default=None,
        description="Combined redundant images across exact and near duplicates (exact_redundant + near_redundant)",
    )
    clean_unique_images: Optional[int] = Field(
        default=None,
        description="Net clean, unique images available for training (total_validated_images - total_redundant_images)",
    )
    quality_score: Optional[float] = Field(
        default=None,
        description="Composite dataset quality score [0.0 - 100.0] combining integrity and uniqueness ratios, or null if not evaluated",
    )


class UnifiedAnalysisResult(BaseModel):
    id: str = Field(..., description="Unique analysis job ID")
    dataset_id: str = Field(..., description="Associated dataset ID")
    dataset_name: str = Field(..., description="Dataset display name")
    status: AnalysisStatus = Field(..., description="Job execution status")
    created_at: str = Field(..., description="ISO 8601 job creation timestamp")
    started_at: Optional[str] = Field(default=None, description="ISO 8601 start timestamp")
    completed_at: Optional[str] = Field(default=None, description="ISO 8601 completion timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Total analysis duration in ms")
    error_message: Optional[str] = Field(default=None, description="Failure description if status is failed")

    config: AnalysisConfig = Field(default_factory=AnalysisConfig, description="Analysis configuration used")
    stages_completed: List[str] = Field(default_factory=list, description="Stages completed successfully")
    stage_durations_ms: Dict[str, float] = Field(default_factory=dict, description="Execution duration per stage in ms")

    metrics: UnifiedAnalysisMetrics = Field(default_factory=UnifiedAnalysisMetrics, description="Consolidated metrics")

    discovery: Optional[DatasetDiscoveryResult] = Field(default=None, description="M2.1 discovery result if completed")
    validation: Optional[DatasetValidationResult] = Field(default=None, description="M2.2 validation result if completed")
    exact_duplicates: Optional[DuplicateAnalysisResult] = Field(default=None, description="M2.3 duplicate result if completed")
    near_duplicates: Optional[NearDuplicateAnalysisResult] = Field(default=None, description="M2.4 near-duplicate result if completed")

    warnings: List[str] = Field(default_factory=list, description="Consolidated warnings across all pipeline stages")

    def to_summary(self) -> "AnalysisSummary":
        """Convert into standard AnalysisSummary for list endpoints."""
        return AnalysisSummary(
            id=self.id,
            dataset_id=self.dataset_id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error_message=self.error_message,
            total_files_evaluated=self.metrics.total_validated_images,
            duplicate_count=self.metrics.total_redundant_images,
            corrupted_count=self.metrics.total_corrupted_images,
            quality_score=self.metrics.quality_score,
        )


class AnalysisStatusResponse(BaseModel):
    analysis_id: str = Field(..., description="Unique analysis job ID")
    dataset_id: str = Field(..., description="Associated dataset ID")
    status: AnalysisStatus = Field(..., description="Job execution status")
    created_at: str = Field(..., description="ISO 8601 job creation timestamp")
    started_at: Optional[str] = Field(default=None, description="ISO 8601 start timestamp")
    completed_at: Optional[str] = Field(default=None, description="ISO 8601 completion timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Total execution duration in ms")
    stages_completed: List[str] = Field(default_factory=list, description="Stages completed so far")
    current_stage: Optional[str] = Field(default=None, description="Stage currently being executed, or None")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")


class AnalysisCreateRequest(BaseModel):
    dataset_id: str = Field(..., description="Target dataset identifier to analyze")
    config: Optional[AnalysisConfig] = Field(default=None, description="Optional analysis execution configuration")


class AnalysisSummary(BaseModel):
    id: str = Field(..., description="Unique analysis job ID")
    dataset_id: str = Field(..., description="Associated dataset ID")
    status: AnalysisStatus = Field(..., description="Job execution status")
    created_at: str = Field(..., description="ISO 8601 job creation timestamp")
    started_at: Optional[str] = Field(default=None, description="ISO 8601 start timestamp")
    completed_at: Optional[str] = Field(default=None, description="ISO 8601 completion timestamp")
    error_message: Optional[str] = Field(default=None, description="Failure description if status is failed")
    total_files_evaluated: Optional[int] = Field(default=None, description="Evaluated file count")
    duplicate_count: Optional[int] = Field(default=None, description="Identified duplicates")
    corrupted_count: Optional[int] = Field(default=None, description="Corrupted files")
    quality_score: Optional[float] = Field(default=None, description="Computed quality score [0.0 - 100.0]")


class AnalysisListResponse(BaseModel):
    total: int = Field(..., description="Total analyses count")
    items: List[AnalysisSummary] = Field(..., description="List of analysis summaries")
    is_placeholder: bool = Field(default=False, description="Flag indicating development placeholder")
    note: Optional[str] = Field(default=None, description="Development notice")


UnifiedAnalysisResult.model_rebuild()


