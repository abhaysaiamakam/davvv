from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DatasetSource(str, Enum):
    ICAR_RICE_MAIZE = "icar_rice_maize"
    PADDY_DOCTOR = "paddy_doctor"
    MENDELEY_RICE = "mendeley_rice"
    PLANT_VILLAGE = "plant_village"
    PLANT_DOC = "plant_doc"
    CHILLI_LEAF = "chilli_leaf"
    KAGGLE_PADDY = "kaggle_paddy"
    EVALUATOR_UPLOAD = "evaluator_upload"


class DatasetStatus(str, Enum):
    REGISTERED = "registered"
    DISCOVERING = "discovering"
    DISCOVERED = "discovered"
    VALIDATING = "validating"
    VALIDATED = "validated"
    READY = "ready"
    ANALYZING = "analyzing"
    INVALID = "invalid"
    ERROR = "error"


class ValidationStatus(str, Enum):
    VALID = "valid"
    CORRUPT = "corrupt"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class ClassDiscoveryInfo(BaseModel):
    class_name: str = Field(..., description="Normalized class identifier")
    relative_path: str = Field(..., description="Relative directory path from dataset root")
    image_count: int = Field(..., description="Number of discovered images in this class")


class DatasetDiscoveryResult(BaseModel):
    dataset_id: str = Field(..., description="Unique dataset identifier")
    dataset_name: str = Field(..., description="Dataset display name")
    dataset_source: DatasetSource = Field(..., description="Origin source")
    dataset_root_relative_path: str = Field(..., description="Sanitized relative path of dataset root")
    discovery_status: DatasetStatus = Field(..., description="Discovery outcome status")
    discovered_image_files: Optional[int] = Field(default=None, description="Total supported image files found")
    discovered_class_directories: Optional[int] = Field(default=None, description="Total class directories found")
    supported_extensions_encountered: List[str] = Field(default_factory=list, description="Extensions found")
    classes: List[ClassDiscoveryInfo] = Field(default_factory=list, description="Discovered classes breakdown")
    unreadable_or_inaccessible_count: int = Field(default=0, description="Inaccessible files or dirs")
    ingestion_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of discovery")
    warnings: List[str] = Field(default_factory=list, description="Discovery warnings and anomalies")
    validated_image_files: Optional[int] = Field(default=None, description="Validated images (null until M2.2 validation)")


class ImageValidationRecord(BaseModel):
    relative_path: str = Field(..., description="Relative path from dataset root")
    file_size_bytes: int = Field(..., description="File size in bytes")
    format: Optional[str] = Field(default=None, description="Decoded image format (e.g. JPEG, PNG)")
    width: Optional[int] = Field(default=None, description="Image pixel width")
    height: Optional[int] = Field(default=None, description="Image pixel height")
    aspect_ratio: Optional[float] = Field(default=None, description="Width / Height ratio")
    color_mode: Optional[str] = Field(default=None, description="Image color mode (e.g. RGB, L)")
    channels: Optional[int] = Field(default=None, description="Number of color channels")
    status: ValidationStatus = Field(..., description="Per-file validation outcome")
    error_message: Optional[str] = Field(default=None, description="Error reason if invalid or corrupt")


class DimensionSummary(BaseModel):
    min_width: Optional[int] = Field(default=None)
    max_width: Optional[int] = Field(default=None)
    min_height: Optional[int] = Field(default=None)
    max_height: Optional[int] = Field(default=None)
    mean_width: Optional[float] = Field(default=None)
    mean_height: Optional[float] = Field(default=None)
    min_aspect_ratio: Optional[float] = Field(default=None)
    max_aspect_ratio: Optional[float] = Field(default=None)


class DatasetValidationResult(BaseModel):
    dataset_id: str = Field(..., description="Unique dataset identifier")
    dataset_name: str = Field(..., description="Dataset display name")
    dataset_source: DatasetSource = Field(..., description="Origin source")
    validation_status: DatasetStatus = Field(..., description="Overall validation status")
    total_discovered_images: int = Field(..., description="Discovered image files evaluated")
    total_validated_images: int = Field(..., description="Confirmed readable/valid images")
    total_corrupted_images: int = Field(..., description="Corrupted or malformed images")
    total_unreadable_images: int = Field(..., description="Inaccessible or permission error files")
    total_processing_errors: int = Field(..., description="Unexpected processing error count")
    total_unsupported_files: int = Field(..., description="Unsupported file formats encountered")
    validation_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of validation")
    dimension_summary: Optional[DimensionSummary] = Field(default=None, description="Aggregate dimension statistics")
    color_mode_distribution: Dict[str, int] = Field(default_factory=dict, description="Image color modes breakdown")
    format_distribution: Dict[str, int] = Field(default_factory=dict, description="Decoded formats breakdown")
    corrupted_files: List[ImageValidationRecord] = Field(default_factory=list, description="Records of failed files")
    images: Optional[List[ImageValidationRecord]] = Field(default=None, description="All validation records")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


class DuplicateImageMember(BaseModel):
    relative_path: str = Field(..., description="Relative path from dataset root")
    class_name: str = Field(..., description="Class name derived from directory hierarchy")
    file_size_bytes: int = Field(..., description="File size in bytes")
    is_representative: bool = Field(default=False, description="Whether this is the canonical member")


class ExactDuplicateGroup(BaseModel):
    group_id: str = Field(..., description="Deterministic unique identifier for this duplicate group")
    sha256_hash: str = Field(..., description="Exact SHA-256 hex digest of the file bytes")
    file_size_bytes: int = Field(..., description="Size of each image in bytes")
    image_count: int = Field(..., description="Total images in this duplicate group")
    representative: DuplicateImageMember = Field(..., description="Canonical representative of the group")
    duplicates: List[DuplicateImageMember] = Field(..., description="Non-representative duplicate instances")
    classes_involved: List[str] = Field(..., description="Unique classes appearing across group members")
    is_cross_class: bool = Field(..., description="Whether duplicate images span more than one class")


class ClassDuplicateMetric(BaseModel):
    class_name: str = Field(..., description="Class identifier")
    total_images: int = Field(..., description="Total eligible images in this class")
    duplicate_instances: int = Field(..., description="Redundant duplicate instances in this class")
    duplicate_percentage: float = Field(..., description="Percentage of images in class that are duplicates")


class DuplicateAnalysisResult(BaseModel):
    dataset_id: str = Field(..., description="Unique dataset identifier")
    dataset_name: str = Field(..., description="Dataset display name")
    analysis_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of duplicate analysis")
    total_eligible_images: int = Field(..., description="Total valid images evaluated for duplicate detection")
    successfully_hashed_images: int = Field(..., description="Count of images successfully hashed via SHA-256")
    hashing_failures: int = Field(0, description="Count of files that could not be hashed due to I/O errors")
    unique_content_groups: int = Field(..., description="Number of unique SHA-256 content hashes found")
    exact_duplicate_groups: int = Field(..., description="Number of duplicate groups with >= 2 images")
    duplicate_instances_count: int = Field(..., description="Total redundant image instances beyond representatives")
    images_in_duplicate_groups: int = Field(..., description="Total images participating in duplicate groups")
    duplicate_percentage: float = Field(..., description="Redundant instances as percentage of successfully hashed images")
    cross_class_duplicate_groups: int = Field(..., description="Duplicate groups spanning multiple classes")
    groups: List[ExactDuplicateGroup] = Field(default_factory=list, description="Detected duplicate groups")
    class_metrics: Dict[str, ClassDuplicateMetric] = Field(default_factory=dict, description="Per-class duplicate statistics")
    warnings: List[str] = Field(default_factory=list, description="Analysis warnings or notices")


class PerceptualHashAlgorithm(str, Enum):
    PHASH = "phash"
    DHASH = "dhash"
    AHASH = "ahash"


class NearDuplicateQueryConfig(BaseModel):
    algorithm: PerceptualHashAlgorithm = Field(
        default=PerceptualHashAlgorithm.PHASH,
        description="Perceptual hashing algorithm to use (phash, dhash, or ahash)",
    )
    hash_size: int = Field(
        default=8,
        ge=4,
        le=16,
        description="Hash dimension size (8 produces a 64-bit perceptual hash)",
    )
    distance_threshold: int = Field(
        default=10,
        ge=0,
        le=64,
        description="Maximum Hamming distance between perceptual hashes to consider as near-duplicates",
    )


class NearDuplicateMember(BaseModel):
    relative_path: str = Field(..., description="Relative file path from dataset root")
    class_name: str = Field(..., description="Class name from directory structure")
    perceptual_hash: str = Field(..., description="Hex representation of perceptual hash")
    file_size_bytes: int = Field(..., description="File size in bytes")
    is_representative: bool = Field(default=False, description="Whether this is the canonical representative")
    hamming_distance_to_representative: int = Field(0, description="Hamming distance to canonical representative")
    similarity_to_representative: float = Field(1.0, description="Normalized similarity score to canonical representative (0.0 to 1.0)")


class NearDuplicateGroup(BaseModel):
    group_id: str = Field(..., description="Deterministic unique identifier for near-duplicate group")
    algorithm: str = Field(..., description="Perceptual hash algorithm used")
    representative: NearDuplicateMember = Field(..., description="Canonical representative image of the group")
    near_duplicates: List[NearDuplicateMember] = Field(..., description="Visually similar near-duplicate members")
    image_count: int = Field(..., description="Total images in this near-duplicate group")
    classes_involved: List[str] = Field(..., description="Classes represented across group members")
    is_cross_class: bool = Field(..., description="Whether group members span multiple class directories")
    max_distance_in_group: int = Field(0, description="Maximum observed Hamming distance to representative in group")
    min_similarity_in_group: float = Field(1.0, description="Minimum observed similarity score to representative in group")


class PerClassNearDuplicateMetric(BaseModel):
    class_name: str = Field(..., description="Class identifier")
    total_images: int = Field(..., description="Total eligible images in this class")
    near_duplicate_instances: int = Field(..., description="Redundant near-duplicate instances in this class")
    near_duplicate_percentage: float = Field(..., description="Percentage of images in class that are near-duplicates")


class NearDuplicateAnalysisResult(BaseModel):
    dataset_id: str = Field(..., description="Unique dataset identifier")
    dataset_name: str = Field(..., description="Dataset display name")
    analysis_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of near-duplicate analysis")
    algorithm: str = Field(..., description="Perceptual hash algorithm executed")
    hash_size: int = Field(..., description="Hash dimension size")
    distance_threshold: int = Field(..., description="Maximum Hamming distance threshold used")
    similarity_threshold: float = Field(..., description="Equivalent minimum normalized similarity threshold")
    total_eligible_images: int = Field(..., description="Total valid images evaluated")
    successfully_hashed_images: int = Field(..., description="Total images successfully perceptually hashed")
    hashing_failures: int = Field(0, description="Images that failed during perceptual hashing")
    unique_perceptual_hashes: int = Field(..., description="Distinct perceptual hash values found")
    exact_duplicates_collapsed_count: int = Field(..., description="Exact duplicate copies collapsed before comparison to prevent inflation")
    unique_content_representatives_compared: int = Field(..., description="Unique content representatives compared pairwise")
    pairwise_comparisons_performed: int = Field(..., description="Total candidate pairs compared")
    near_duplicate_groups: int = Field(..., description="Number of near-duplicate groups found")
    images_in_near_duplicate_groups: int = Field(..., description="Total images participating in near-duplicate groups")
    redundant_near_duplicate_instances: int = Field(..., description="Redundant near-duplicate instances beyond group representatives")
    near_duplicate_percentage: float = Field(..., description="Redundant instances as percentage of successfully hashed images")
    cross_class_near_duplicate_groups: int = Field(..., description="Near-duplicate groups spanning multiple classes")
    analysis_duration_ms: float = Field(..., description="Analysis duration in milliseconds")
    groups: List[NearDuplicateGroup] = Field(default_factory=list, description="Detected near-duplicate groups")
    class_metrics: Dict[str, PerClassNearDuplicateMetric] = Field(default_factory=dict, description="Per-class near-duplicate metrics")
    warnings: List[str] = Field(default_factory=list, description="Analysis warnings and notes")


class DatasetMetadata(BaseModel):
    id: str = Field(..., description="Unique dataset identifier")
    name: str = Field(..., description="Dataset display name")
    slug: str = Field(..., description="URL-friendly identifier")
    description: str = Field(..., description="Description of the dataset")
    source: DatasetSource = Field(..., description="Source origin")
    is_curated: bool = Field(default=True, description="Whether this is a curated platform dataset")
    is_uploaded: bool = Field(default=False, description="Whether uploaded by evaluator")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 update timestamp")
    crops: List[str] = Field(default_factory=list, description="Target crop categories")
    status: DatasetStatus = Field(default=DatasetStatus.REGISTERED, description="Ingestion/analysis readiness")
    tags: List[str] = Field(default_factory=list, description="Descriptive classification tags")
    total_images: Optional[int] = Field(default=None, description="Image count from discovery")
    total_classes: Optional[int] = Field(default=None, description="Class count from discovery")
    validated_image_files: Optional[int] = Field(default=None, description="Confirmed valid readable image count")
    corrupted_image_files: Optional[int] = Field(default=None, description="Confirmed corrupted image count")
    storage_relative_path: Optional[str] = Field(default=None, description="Sanitized relative storage path")
    discovery: Optional[DatasetDiscoveryResult] = Field(default=None, description="Detailed discovery result if executed")
    validation: Optional[DatasetValidationResult] = Field(default=None, description="Detailed validation result if executed")
    duplicates: Optional[DuplicateAnalysisResult] = Field(default=None, description="Detailed duplicate analysis if executed")
    duplicate_groups_count: Optional[int] = Field(default=None, description="Number of exact duplicate groups")
    near_duplicates: Optional[NearDuplicateAnalysisResult] = Field(default=None, description="Detailed near-duplicate analysis if executed")
    near_duplicate_groups_count: Optional[int] = Field(default=None, description="Number of near-duplicate groups")
    current_version_id: Optional[str] = Field(default=None, description="Active dataset version identifier")
    current_version_number: Optional[int] = Field(default=None, description="Active dataset version sequence number")
    total_versions: int = Field(default=1, description="Total recorded dataset content versions")
    content_fingerprint: Optional[str] = Field(default=None, description="Deterministic content digest of active version")


class DatasetVersion(BaseModel):
    """Snapshot record of a specific content version of a dataset."""

    version_id: str = Field(..., description="Unique version identifier, e.g. ver-ds1-1-abc12345")
    version_number: int = Field(..., ge=1, description="Sequential version index")
    dataset_id: str = Field(..., description="Associated dataset identifier")
    content_fingerprint: str = Field(..., description="Deterministic SHA-256 digest of dataset contents")
    created_at: str = Field(..., description="ISO 8601 version creation timestamp")
    storage_relative_path: str = Field(..., description="Relative storage path where version contents are extracted")
    status: DatasetStatus = Field(default=DatasetStatus.REGISTERED, description="Version lifecycle and readiness state")
    image_count: Optional[int] = Field(default=None, description="Discovered image count for this version")
    class_count: Optional[int] = Field(default=None, description="Discovered class count for this version")
    source_analysis_id: Optional[str] = Field(default=None, description="M2 unified analysis identifier")
    source_quality_id: Optional[str] = Field(default=None, description="M3 quality assessment identifier")
    source_eda_id: Optional[str] = Field(default=None, description="M4 EDA report identifier")
    error_message: Optional[str] = Field(default=None, description="Error reason if processing failed")


class DatasetVersionListResponse(BaseModel):
    total: int = Field(..., description="Total versions found")
    items: List[DatasetVersion] = Field(..., description="Dataset version records")


class DatasetRegisterRequest(BaseModel):
    """Request model for dynamically registering a new dataset."""

    id: str = Field(..., description="Unique dataset identifier (alphanumeric, dashes, underscores)")
    name: str = Field(..., description="Human-readable display name")
    description: str = Field(default="", description="Dataset summary and provenance")
    source: DatasetSource = Field(default=DatasetSource.EVALUATOR_UPLOAD, description="Dataset origin")
    crops: List[str] = Field(default_factory=list, description="Target crop categories")
    tags: List[str] = Field(default_factory=list, description="Descriptive classification tags")


class DatasetUploadResponse(BaseModel):
    """Response returned upon successful archive upload and job dispatch."""

    dataset_id: str
    version_id: str
    version_number: int
    job_id: str
    status: DatasetStatus
    message: str
    is_duplicate_content: bool = False


class DatasetListResponse(BaseModel):
    total: int = Field(..., description="Total datasets returned")
    items: List[DatasetMetadata] = Field(..., description="Dataset items")
    is_placeholder: bool = Field(default=True, description="Flag indicating development placeholder vs computed data")
    note: Optional[str] = Field(default=None, description="Notice or context regarding returned data")
