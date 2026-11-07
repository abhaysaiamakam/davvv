"""
M8 — Data Preprocessing & Cleaning Engine Schemas.

Provides typed structures for dataset cleaning, operations registry,
preview generation, transformation history, and lifecycle tracking.
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PreprocessingModality(str, enum.Enum):
    TABULAR = "tabular"
    IMAGE = "image"
    TIME_SERIES = "time_series"
    ANNOTATION = "annotation"


class PreprocessingOperationType(str, enum.Enum):
    # Tabular
    MISSING_VALUE_IMPUTATION = "missing_value_imputation"
    DROP_MISSING_ROWS = "drop_missing_rows"
    DROP_MISSING_COLUMNS = "drop_missing_columns"
    REMOVE_DUPLICATES = "remove_duplicates"
    OUTLIER_HANDLING = "outlier_handling"
    TYPE_CONVERSION = "type_conversion"
    CATEGORICAL_ENCODING = "categorical_encoding"
    NUMERIC_SCALING = "numeric_scaling"
    COLUMN_SELECTION = "column_selection"
    ROW_FILTERING = "row_filtering"
    VALUE_REPLACEMENT = "value_replacement"
    STRING_NORMALIZATION = "string_normalization"

    # Image
    RESIZE_IMAGES = "resize_images"
    CONVERT_FORMAT = "convert_format"
    CONVERT_COLOR_MODE = "convert_color_mode"
    REMOVE_EXACT_DUPLICATES = "remove_exact_duplicates"
    EXCLUDE_CORRUPT_IMAGES = "exclude_corrupt_images"
    FILTER_CLASSES = "filter_classes"

    # Time-Series
    PARSE_TIMESTAMPS = "parse_timestamps"
    SORT_TIMESTAMPS = "sort_timestamps"
    HANDLE_DUPLICATE_TIMESTAMPS = "handle_duplicate_timestamps"
    INTERPOLATE_MISSING_TIMESTAMPS = "interpolate_missing_timestamps"

    # Annotation
    FILTER_ANNOTATION_CLASSES = "filter_annotation_classes"
    VALIDATE_AND_CLIP_BOUNDING_BOXES = "validate_and_clip_bounding_boxes"
    RESCALE_ANNOTATIONS = "rescale_annotations"


class OperationStatus(str, enum.Enum):
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


class PreprocessingOperationConfig(BaseModel):
    """Specification of a single preprocessing operation to be previewed or applied."""

    operation_id: Optional[str] = Field(
        default=None, description="Optional client-assigned operation identifier"
    )
    operation_type: PreprocessingOperationType = Field(
        ..., description="Canonical operation type"
    )
    modality: Optional[PreprocessingModality] = Field(
        default=None, description="Target dataset modality (auto-inferred from operation_type if omitted)"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Operation-specific configuration parameters"
    )
    target_file: Optional[str] = Field(
        default=None,
        description="Relative path of target file (e.g. 'measurements.csv'). If omitted, applies to all compatible files.",
    )
    target_columns: List[str] = Field(
        default_factory=list,
        description="Specific column names to target (tabular/time-series).",
    )


class OperationDefinition(BaseModel):
    """Public catalog definition of an available preprocessing operation."""

    operation_type: PreprocessingOperationType = Field(
        ..., description="Canonical operation type"
    )
    display_name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of the operation")
    modality: PreprocessingModality = Field(..., description="Applicable dataset modality")
    parameters_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema of acceptable parameters"
    )
    supported_file_types: List[str] = Field(
        default_factory=list, description="Supported file extensions (e.g. ['.csv', '.tsv'])"
    )
    known_limitations: List[str] = Field(
        default_factory=list, description="Explicitly documented boundaries or restrictions"
    )


class AvailableOperationsResponse(BaseModel):
    """Response containing operations applicable to a specific dataset."""

    dataset_id: str
    detected_modalities: List[PreprocessingModality] = Field(
        default_factory=list, description="Modalities present in dataset"
    )
    operations: List[OperationDefinition] = Field(
        default_factory=list, description="Available operations"
    )


class OperationPreviewResult(BaseModel):
    """Estimated or simulated outcome of a single preprocessing operation."""

    operation_type: PreprocessingOperationType
    status: str = Field(default="valid", description="'valid' or 'invalid'")
    affected_rows: Optional[int] = Field(
        default=None, description="Count of rows added, modified, or removed"
    )
    affected_columns: List[str] = Field(
        default_factory=list, description="Columns modified, added, or removed"
    )
    affected_files: List[str] = Field(
        default_factory=list, description="Relative paths of affected files (sample)"
    )
    rows_before: Optional[int] = Field(default=None)
    rows_after: Optional[int] = Field(default=None)
    files_before: Optional[int] = Field(default=None)
    files_after: Optional[int] = Field(default=None)
    before_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Summary metrics before transformation"
    )
    after_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Summary metrics after transformation"
    )
    sample_before: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Sample rows or items prior to transformation"
    )
    sample_after: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Sample rows or items after transformation"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Safety or data loss warnings"
    )
    validation_errors: List[str] = Field(
        default_factory=list, description="Parameter or applicability errors"
    )


class PreprocessingPreviewRequest(BaseModel):
    """Request model for previewing one or more preprocessing operations."""

    dataset_id: str = Field(..., description="Target dataset identifier")
    version_id: Optional[str] = Field(
        default=None, description="Source dataset version (defaults to active/latest)"
    )
    operations: List[PreprocessingOperationConfig] = Field(
        ..., min_length=1, description="Ordered list of operations to preview"
    )


class PreprocessingPreviewResponse(BaseModel):
    """Structured response detailing the preview of requested operations."""

    dataset_id: str
    source_version_id: str
    operations: List[OperationPreviewResult]
    total_operations: int
    summary: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    can_apply: bool = Field(
        ..., description="True if all operations validated cleanly and can be applied"
    )


class PreprocessingApplyRequest(BaseModel):
    """Request model for executing preprocessing operations to create a derived version."""

    dataset_id: str = Field(..., description="Target dataset identifier")
    version_id: Optional[str] = Field(
        default=None, description="Source dataset version (defaults to active/latest)"
    )
    operations: List[PreprocessingOperationConfig] = Field(
        ..., min_length=1, description="Ordered list of operations to execute"
    )
    description: Optional[str] = Field(
        default=None, description="Optional user note explaining the cleaning intent"
    )


class PreprocessingApplyResponse(BaseModel):
    """Response returned upon dispatching derived version creation."""

    dataset_id: str
    source_version_id: str
    derived_version_id: str
    version_number: int
    job_id: str
    status: str
    message: str
    operations_applied: int
    is_duplicate_content: bool = False


class AppliedOperationRecord(BaseModel):
    """Persistent audit entry for an individual applied operation."""

    operation_id: str
    operation_type: PreprocessingOperationType
    modality: PreprocessingModality
    parameters: Dict[str, Any] = Field(default_factory=dict)
    affected_columns: List[str] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    rows_before: Optional[int] = None
    rows_after: Optional[int] = None
    files_before: Optional[int] = None
    files_after: Optional[int] = None
    status: OperationStatus
    warnings: List[str] = Field(default_factory=list)
    executed_at: str


class PreprocessingHistoryRecord(BaseModel):
    """Immutable audit trail for a derived dataset version created via preprocessing."""

    id: str = Field(..., description="Unique history identifier")
    dataset_id: str = Field(..., description="Target dataset identifier")
    source_version_id: str = Field(..., description="Base source dataset version")
    derived_version_id: str = Field(..., description="Resulting derived dataset version")
    version_number: int = Field(..., description="Sequential version number of derived version")
    job_id: Optional[str] = Field(default=None, description="Asynchronous re-analysis job ID")
    operations: List[AppliedOperationRecord] = Field(default_factory=list)
    input_fingerprint: str = Field(..., description="SHA-256 fingerprint of source version")
    output_fingerprint: str = Field(..., description="SHA-256 fingerprint of derived version")
    status: str = Field(default="completed", description="'completed' or 'failed'")
    created_at: str
    completed_at: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class PreprocessingHistoryListResponse(BaseModel):
    """List of all historical preprocessing records for a dataset."""

    total: int
    items: List[PreprocessingHistoryRecord]

