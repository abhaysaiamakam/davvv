"""
M9 — Feature Engineering & Feature Selection Schemas.

Provides typed structures for feature metadata, operations registry, preview simulation,
feature selection (variance threshold, correlation matrix), dimensionality reduction (PCA),
and historical audit trails.
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FeatureModality(str, enum.Enum):
    TABULAR = "tabular"
    IMAGE = "image"
    TIME_SERIES = "time_series"
    ANNOTATION = "annotation"


class FeatureOperationType(str, enum.Enum):
    # Tabular transformations
    LOGARITHMIC_TRANSFORM = "logarithmic_transform"
    SQUARE_ROOT_TRANSFORM = "square_root_transform"
    RECIPROCAL_TRANSFORM = "reciprocal_transform"
    POLYNOMIAL_FEATURES = "polynomial_features"
    INTERACTION_FEATURES = "interaction_features"
    ARITHMETIC_COMBINATION = "arithmetic_combination"
    DATETIME_EXTRACTION = "datetime_extraction"
    FREQUENCY_ENCODING = "frequency_encoding"
    TEXT_FEATURE_EXTRACTION = "text_feature_extraction"

    # Feature selection & correlation
    VARIANCE_THRESHOLD_SELECTION = "variance_threshold_selection"
    CORRELATION_REDUNDANCY_REMOVAL = "correlation_redundancy_removal"
    EXPLICIT_FEATURE_SELECTION = "explicit_feature_selection"

    # Dimensionality reduction
    PRINCIPAL_COMPONENT_ANALYSIS = "principal_component_analysis"

    # Time-Series feature engineering
    LAG_FEATURES = "lag_features"
    ROLLING_STATISTICS = "rolling_statistics"
    DIFFERENCE_FEATURES = "difference_features"

    # Image metadata engineering
    IMAGE_METADATA_EXTRACTION = "image_metadata_extraction"

    # Annotation metadata engineering
    ANNOTATION_METADATA_EXTRACTION = "annotation_metadata_extraction"


class FeatureMetadata(BaseModel):
    """Metadata describing an engineered or discovered dataset feature."""

    feature_id: str
    feature_name: str
    source_columns: List[str] = Field(default_factory=list)
    feature_type: str = Field(..., description="'numeric', 'categorical', 'datetime', 'text', 'boolean'")
    data_type: str = Field(..., description="Underlying python/pandas data type (e.g. float64, int64, object)")
    operation_id: Optional[str] = None
    operation_parameters: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    description: Optional[str] = None


class FeatureOperationConfig(BaseModel):
    """Configuration for a single feature engineering or selection operation."""

    operation_id: Optional[str] = None
    operation_type: FeatureOperationType
    modality: Optional[FeatureModality] = Field(
        default=None, description="Target dataset modality (auto-inferred if omitted)"
    )
    parameters: Dict[str, Any] = Field(default_factory=dict)
    target_file: Optional[str] = Field(default=None, description="Target file path for tabular/time-series")
    target_columns: List[str] = Field(default_factory=list, description="Target columns to transform or select")


class FeatureOperationDefinition(BaseModel):
    """Public catalog descriptor for an available feature operation."""

    operation_type: FeatureOperationType
    display_name: str
    description: str
    modality: FeatureModality
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    supported_file_types: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)


class AvailableFeaturesResponse(BaseModel):
    """Response containing available features and feature engineering operations for a dataset."""

    dataset_id: str
    detected_modalities: List[FeatureModality] = Field(default_factory=list)
    current_features: List[FeatureMetadata] = Field(default_factory=list)
    operations: List[FeatureOperationDefinition] = Field(default_factory=list)


class FeaturePreviewResult(BaseModel):
    """Simulated output of a feature engineering operation."""

    operation_type: FeatureOperationType
    status: str = Field(default="valid", description="'valid' or 'invalid'")
    source_features: List[str] = Field(default_factory=list)
    generated_features: List[str] = Field(default_factory=list)
    removed_features: List[str] = Field(default_factory=list)
    features_before_count: int = 0
    features_after_count: int = 0
    rows_before: int = 0
    rows_after: int = 0
    explained_variance_ratio: Optional[List[float]] = Field(
        default=None, description="Explained variance per component for PCA"
    )
    cumulative_explained_variance: Optional[List[float]] = Field(
        default=None, description="Cumulative explained variance for PCA"
    )
    correlation_findings: List[Dict[str, Any]] = Field(
        default_factory=list, description="Identified highly correlated feature pairs"
    )
    sample_before: Optional[List[Dict[str, Any]]] = None
    sample_after: Optional[List[Dict[str, Any]]] = None
    warnings: List[str] = Field(default_factory=list)
    validation_errors: List[str] = Field(default_factory=list)


class FeaturePreviewRequest(BaseModel):
    """Request model for previewing feature engineering operations."""

    dataset_id: str
    version_id: Optional[str] = None
    operations: List[FeatureOperationConfig] = Field(..., min_length=1)


class FeaturePreviewResponse(BaseModel):
    """Structured response detailing feature engineering previews."""

    dataset_id: str
    source_version_id: str
    operations: List[FeaturePreviewResult]
    total_operations: int
    warnings: List[str] = Field(default_factory=list)
    can_apply: bool


class FeatureApplyRequest(BaseModel):
    """Request model for applying feature engineering and creating a derived dataset version."""

    dataset_id: str
    version_id: Optional[str] = None
    operations: List[FeatureOperationConfig] = Field(..., min_length=1)
    description: Optional[str] = Field(default=None, description="Note explaining feature engineering intent")


class FeatureApplyResponse(BaseModel):
    """Response returned upon successfully creating an engineered dataset version."""

    dataset_id: str
    source_version_id: str
    derived_version_id: str
    version_number: int
    job_id: str
    status: str
    message: str
    operations_applied: int
    new_features_count: int
    is_duplicate_content: bool = False


class AppliedFeatureOperationRecord(BaseModel):
    """Persistent audit record for an applied feature operation."""

    operation_id: str
    operation_type: FeatureOperationType
    modality: FeatureModality
    parameters: Dict[str, Any] = Field(default_factory=dict)
    source_features: List[str] = Field(default_factory=list)
    generated_features: List[str] = Field(default_factory=list)
    removed_features: List[str] = Field(default_factory=list)
    status: str = Field(default="applied")
    warnings: List[str] = Field(default_factory=list)
    executed_at: str


class FeatureHistoryRecord(BaseModel):
    """Immutable audit trail for a feature-engineered dataset version."""

    id: str
    dataset_id: str
    source_version_id: str
    derived_version_id: str
    version_number: int
    job_id: Optional[str] = None
    operations: List[AppliedFeatureOperationRecord] = Field(default_factory=list)
    input_fingerprint: str
    output_fingerprint: str
    status: str = Field(default="completed")
    created_at: str
    completed_at: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class FeatureHistoryListResponse(BaseModel):
    """List of historical feature engineering records."""

    total: int
    items: List[FeatureHistoryRecord]
