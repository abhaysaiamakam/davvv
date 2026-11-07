from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.analysis import AnalysisStatus


class QualityFindingCategory(str, Enum):
    INTEGRITY = "integrity"
    IMBALANCE = "imbalance"
    CONSISTENCY = "consistency"
    DUPLICATES = "duplicates"
    METADATA = "metadata"


class QualitySeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class QualityFinding(BaseModel):
    id: str = Field(..., description="Stable, deterministic finding identifier")
    category: QualityFindingCategory = Field(..., description="Finding category")
    severity: QualitySeverity = Field(..., description="Finding severity/priority level")
    title: str = Field(..., description="Concise human-readable finding summary")
    explanation: str = Field(..., description="Detailed explanation of the observation and its impact")
    metric_name: str = Field(..., description="Name of the computed metric backing this finding")
    observed_value: Any = Field(..., description="Empirical metric value observed in dataset")
    expected_value: Optional[Any] = Field(default=None, description="Reference baseline or expected value")
    threshold_used: Optional[str] = Field(default=None, description="Explicit rule or threshold applied")
    affected_classes: List[str] = Field(default_factory=list, description="Class identifiers affected by this finding")
    affected_image_samples: List[str] = Field(default_factory=list, description="Sample relative paths of affected files")
    recommended_action: str = Field(..., description="Evidence-backed cleaning or curation recommendation")
    evidence_references: List[str] = Field(default_factory=list, description="References to supporting M2 metrics or records")
    methodology_version: str = Field(default="v1.0", description="Assessment methodology version")


class ImageIntegrityAssessment(BaseModel):
    total_discovered_images: Optional[int] = Field(default=None, description="Total image files discovered on filesystem")
    total_validated_images: Optional[int] = Field(default=None, description="Confirmed valid decodable images")
    total_corrupted_images: Optional[int] = Field(default=None, description="Images with byte-level corruption or truncation")
    total_unreadable_images: Optional[int] = Field(default=None, description="Zero-byte or permission-error files")
    total_processing_errors: Optional[int] = Field(default=None, description="Files failing during decoding")
    total_unsupported_files: Optional[int] = Field(default=None, description="Unsupported file extensions encountered")
    integrity_rate: Optional[float] = Field(default=None, description="Percentage of discovered images that are valid (0.0 to 100.0)")
    status: str = Field(..., description="Integrity assessment summary status ('flawless', 'minor_corruption', 'severe_corruption', 'uncomputed', 'error')")
    is_available: bool = Field(default=True, description="Whether validation metrics were successfully computed")
    evaluation_notes: List[str] = Field(default_factory=list, description="Methodology explanations and boundary conditions")


class ClassImbalanceAssessment(BaseModel):
    total_classes: int = Field(..., description="Total class directories discovered")
    classes_with_images: int = Field(..., description="Classes containing at least 1 image")
    empty_classes: List[str] = Field(default_factory=list, description="Classes containing zero images")
    min_class_count: Optional[int] = Field(default=None, description="Minimum image count among non-empty classes")
    max_class_count: Optional[int] = Field(default=None, description="Maximum image count among classes")
    mean_class_count: Optional[float] = Field(default=None, description="Arithmetic mean of class counts")
    median_class_count: Optional[float] = Field(default=None, description="Median of class counts")
    std_class_count: Optional[float] = Field(default=None, description="Sample standard deviation of class counts")
    imbalance_ratio: Optional[float] = Field(default=None, description="Max class count / Min class count (null if min is 0 or undefined)")
    coefficient_of_variation: Optional[float] = Field(default=None, description="std_dev / mean (dispersion index)")
    imbalance_severity: str = Field(..., description="Categorical assessment ('balanced', 'moderately_imbalanced', 'severely_imbalanced', 'undefined')")
    underrepresented_classes: List[Dict[str, Any]] = Field(default_factory=list, description="Classes with counts significantly below average")
    overrepresented_classes: List[Dict[str, Any]] = Field(default_factory=list, description="Classes with counts significantly above average")
    class_distribution: Dict[str, int] = Field(default_factory=dict, description="Image count per discovered class")
    evaluation_notes: List[str] = Field(default_factory=list, description="Statistical rules and formula explanations")


class MetadataConsistencyAssessment(BaseModel):
    min_width: Optional[int] = Field(default=None, description="Minimum width in pixels")
    max_width: Optional[int] = Field(default=None, description="Maximum width in pixels")
    mean_width: Optional[float] = Field(default=None, description="Mean width in pixels")
    std_width: Optional[float] = Field(default=None, description="Standard deviation of width")
    min_height: Optional[int] = Field(default=None, description="Minimum height in pixels")
    max_height: Optional[int] = Field(default=None, description="Maximum height in pixels")
    mean_height: Optional[float] = Field(default=None, description="Mean height in pixels")
    std_height: Optional[float] = Field(default=None, description="Standard deviation of height")
    min_aspect_ratio: Optional[float] = Field(default=None, description="Minimum aspect ratio (width / height)")
    max_aspect_ratio: Optional[float] = Field(default=None, description="Maximum aspect ratio (width / height)")
    mean_aspect_ratio: Optional[float] = Field(default=None, description="Mean aspect ratio")
    format_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of image formats (e.g. JPEG, PNG, MPO)")
    color_mode_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of color modes (e.g. RGB, L)")
    aspect_ratio_outliers_count: int = Field(default=0, description="Count of images with unusual aspect ratios (< 0.5 or > 2.2)")
    small_dimension_images_count: int = Field(default=0, description="Images with width or height < 224px")
    consistency_rate: Optional[float] = Field(default=None, description="Percentage of images meeting standard consistency boundaries")
    is_available: bool = Field(default=True, description="Whether metadata consistency could be evaluated")
    evaluation_notes: List[str] = Field(default_factory=list, description="Consistency rules and observations")


class DuplicateImpactAssessment(BaseModel):
    exact_duplicate_groups: Optional[int] = Field(default=None, description="Count of exact duplicate clusters (SHA-256)")
    exact_duplicate_redundant_instances: Optional[int] = Field(default=None, description="Redundant exact duplicate copies beyond representatives")
    exact_duplicate_percentage: Optional[float] = Field(default=None, description="Exact duplicate redundant copies as % of valid images")
    near_duplicate_groups: Optional[int] = Field(default=None, description="Count of perceptual near-duplicate groups")
    near_duplicate_images_in_groups: Optional[int] = Field(default=None, description="Total images participating in near-duplicate groups")
    near_duplicate_redundant_instances: Optional[int] = Field(default=None, description="Redundant near-duplicate instances beyond canonical representatives")
    near_duplicate_percentage: Optional[float] = Field(default=None, description="Near-duplicate redundant copies as % of valid images")
    cross_class_duplicate_groups: Optional[int] = Field(default=None, description="Total duplicate groups spanning multiple classes (exact + near)")
    total_redundant_images: Optional[int] = Field(default=None, description="Combined non-redundant redundant instances (exact + near, no double counting)")
    clean_unique_images: Optional[int] = Field(default=None, description="Net unique images remaining after deduplication")
    duplicate_impact_severity: str = Field(..., description="Duplicate impact classification ('none', 'low', 'moderate', 'severe', 'uncomputed')")
    classes_affected_count: int = Field(default=0, description="Number of classes with detected duplicates")
    class_duplicate_breakdown: Dict[str, int] = Field(default_factory=dict, description="Redundant instances per class")
    is_available: bool = Field(default=True, description="Whether duplicate impact could be evaluated")
    evaluation_notes: List[str] = Field(default_factory=list, description="Deduplication semantics and safety notes")


class QualityScoreComponent(BaseModel):
    name: str = Field(..., description="Component name")
    score: float = Field(..., ge=0.0, le=100.0, description="Component score on 0.0 - 100.0 scale")
    weight: float = Field(..., ge=0.0, le=1.0, description="Component weight in overall score")
    weighted_score: float = Field(..., ge=0.0, le=100.0, description="Score * weight contribution")
    explanation: str = Field(..., description="Human-readable rationale for this component score")
    metrics_used: Dict[str, Any] = Field(default_factory=dict, description="Raw metrics backing this component score")


class TransparentQualityScore(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Weighted composite dataset quality score [0.0 - 100.0]")
    quality_tier: str = Field(..., description="Overall quality classification ('excellent', 'good', 'fair', 'poor', 'critical')")
    methodology_version: str = Field(default="v1.0", description="Quality scoring methodology version")
    components: Dict[str, QualityScoreComponent] = Field(..., description="Breakdown of individual score components")
    weight_configuration: Dict[str, float] = Field(..., description="Weights applied across components (sums to 1.0)")
    explanation: str = Field(..., description="Detailed explanation of the overall score and primary quality drivers")
    is_complete: bool = Field(default=True, description="Whether all 4 quality components were available for scoring")


class DataQualityAssessment(BaseModel):
    id: str = Field(..., description="Unique assessment identifier (e.g. qa-icar-rice-maize-uuid)")
    dataset_id: str = Field(..., description="Associated dataset identifier")
    dataset_name: str = Field(..., description="Human-readable dataset display name")
    source_analysis_id: Optional[str] = Field(default=None, description="Analysis job ID from M2.5 that provided the base data")
    status: AnalysisStatus = Field(default=AnalysisStatus.COMPLETED, description="Assessment execution status")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    completed_at: Optional[str] = Field(default=None, description="ISO 8601 completion timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Assessment execution duration in ms")
    methodology_version: str = Field(default="v1.0", description="Quality assessment methodology version")

    # Four Core Quality Dimensions
    integrity: ImageIntegrityAssessment = Field(..., description="Image decodability and corruption evaluation")
    imbalance: ClassImbalanceAssessment = Field(..., description="Class distribution and imbalance evaluation")
    metadata_consistency: MetadataConsistencyAssessment = Field(..., description="Dimensional and format consistency evaluation")
    duplicate_impact: DuplicateImpactAssessment = Field(..., description="Exact and near duplicate impact evaluation")

    # Transparent Quality Scoring
    quality_score: TransparentQualityScore = Field(..., description="Explainable, reproducible quality scoring")

    # Evidence-Backed Quality Findings & Recommendations
    findings: List[QualityFinding] = Field(default_factory=list, description="Structured quality findings and actionable recommendations")

    summary: str = Field(..., description="Executive narrative summary of dataset health")
    warnings: List[str] = Field(default_factory=list, description="Notices, data gaps, or boundary conditions")


class QualityAssessmentSummary(BaseModel):
    id: str = Field(..., description="Unique assessment identifier")
    dataset_id: str = Field(..., description="Associated dataset identifier")
    status: AnalysisStatus = Field(..., description="Assessment execution status")
    created_at: str = Field(..., description="Creation timestamp")
    completed_at: Optional[str] = Field(default=None, description="Completion timestamp")
    overall_score: float = Field(..., description="Composite quality score [0.0 - 100.0]")
    quality_tier: str = Field(..., description="Quality tier classification")
    findings_count: int = Field(..., description="Total quality findings identified")
    critical_findings_count: int = Field(default=0, description="Critical severity findings count")
    high_findings_count: int = Field(default=0, description="High severity findings count")


class QualityAssessmentListResponse(BaseModel):
    total: int = Field(..., description="Total assessments count")
    items: List[QualityAssessmentSummary] = Field(..., description="List of quality assessment summaries")
    note: Optional[str] = Field(default=None, description="Context regarding listed assessments")


class QualityAssessmentStatusResponse(BaseModel):
    assessment_id: str = Field(..., description="Assessment identifier")
    dataset_id: str = Field(..., description="Dataset identifier")
    status: AnalysisStatus = Field(..., description="Assessment status")
    created_at: str = Field(..., description="Creation timestamp")
    completed_at: Optional[str] = Field(default=None, description="Completion timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Duration in ms")
    methodology_version: str = Field(default="v1.0")
    error_message: Optional[str] = Field(default=None)

