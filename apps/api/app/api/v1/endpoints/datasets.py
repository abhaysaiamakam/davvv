import re
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.core.config import settings
from app.core.errors import (
    DatasetAnalysisNotFoundError,
    DatasetEdaNotFoundError,
    DatasetInsightsNotFoundError,
    DatasetNotFoundError,
    DatasetQualityAssessmentNotFoundError,
    DatasetVisualizationsNotFoundError,
    InsightNotFoundError,
    PayloadTooLargeError,
    VersionNotFoundError,
    VisualizationNotFoundError,
)
from app.schemas.analysis import (
    AnalysisConfig,
    AnalysisStatusResponse,
    UnifiedAnalysisResult,
)
from app.schemas.quality import (
    DataQualityAssessment,
    QualityAssessmentStatusResponse,
    QualityFinding,
)
from app.schemas.eda import (
    EdaFinding,
    EdaReport,
    EdaStatusResponse,
)
from app.schemas.job import ProcessingJob
from app.schemas.dataset import (
    DatasetDiscoveryResult,
    DatasetListResponse,
    DatasetMetadata,
    DatasetRegisterRequest,
    DatasetUploadResponse,
    DatasetValidationResult,
    DatasetVersion,
    DatasetVersionListResponse,
    DuplicateAnalysisResult,
    NearDuplicateAnalysisResult,
    NearDuplicateQueryConfig,
)
from app.schemas.visualization import (
    ChartType,
    VisualizationCategory,
    VisualizationCollectionResponse,
    VisualizationSpecification,
)
from app.schemas.insights import (
    DatasetInsight,
    InsightCategory,
    InsightCollection,
    InsightCollectionResponse,
    InsightSeverity,
)
from app.services.dataset_service import dataset_service
from app.services.upload_service import upload_service
from app.services.visualizations import visualization_service
from app.services.insights import insights_service

router = APIRouter()


@router.get("", response_model=DatasetListResponse, summary="List Registered Datasets")
async def list_datasets() -> DatasetListResponse:
    """
    Returns registered agricultural datasets.
    Includes real discovered and validated counts once pipelines have executed.
    """
    return dataset_service.list_datasets()


@router.post(
    "",
    response_model=DatasetMetadata,
    status_code=status.HTTP_201_CREATED,
    summary="Register Dataset Metadata",
    description="Registers a new dynamic evaluator dataset entry ahead of archive upload.",
)
async def register_dataset(request: DatasetRegisterRequest) -> DatasetMetadata:
    """Register a new dynamic evaluator dataset."""
    return dataset_service.register_dataset(request)


@router.post(
    "/upload",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Dataset Archive",
    description="Uploads a dataset archive (.zip, .tar, .tar.gz, .tgz), safely extracts it, registers or increments versioning, and enqueues automatic background analysis.",
)
async def upload_dataset_archive(
    file: UploadFile = File(..., description="Dataset archive file"),
    dataset_id: Optional[str] = Form(None, description="Optional target dataset ID. Derived from archive name if omitted."),
    name: Optional[str] = Form(None, description="Optional display name"),
    description: Optional[str] = Form(None, description="Optional dataset description"),
) -> DatasetUploadResponse:
    """Upload an archive and enqueue background analysis."""
    filename = file.filename or "uploaded_dataset.zip"
    upload_service.validate_filename(filename)

    if not dataset_id:
        base_stem = filename
        for ext in [".tar.gz", ".tgz", ".zip", ".tar"]:
            if base_stem.lower().endswith(ext):
                base_stem = base_stem[: -len(ext)]
                break
        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", base_stem).strip("_").lower()
        target_dataset_id = clean_id or f"dataset_{uuid.uuid4().hex[:8]}"
    else:
        target_dataset_id = dataset_id

    # Stream file to a temporary file while enforcing upload size limit
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).name)
    temp_path = Path(temp_file.name)
    total_bytes = 0
    try:
        with temp_file:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                    raise PayloadTooLargeError(
                        f"Uploaded archive exceeds maximum permitted size of {settings.MAX_UPLOAD_SIZE_BYTES} bytes."
                    )
                temp_file.write(chunk)

        return dataset_service.handle_archive_upload(
            dataset_id=target_dataset_id,
            archive_path=temp_path,
            filename=filename,
            dataset_name=name,
            description=description,
        )
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


@router.get("/{dataset_id}", response_model=DatasetMetadata, summary="Get Dataset Metadata")
async def get_dataset(dataset_id: str) -> DatasetMetadata:
    """Retrieve metadata definition for a specific registered dataset."""
    dataset = dataset_service.get_dataset(dataset_id)
    if not dataset:
        raise DatasetNotFoundError(dataset_id)
    return dataset


@router.post(
    "/{dataset_id}/upload",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload New Dataset Version",
    description="Uploads an archive as a new version of an existing dataset and triggers automatic background analysis.",
)
async def upload_dataset_version_archive(
    dataset_id: str,
    file: UploadFile = File(..., description="Dataset archive file"),
) -> DatasetUploadResponse:
    """Upload a new archive version for an existing dataset."""
    filename = file.filename or "uploaded_dataset.zip"
    upload_service.validate_filename(filename)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).name)
    temp_path = Path(temp_file.name)
    total_bytes = 0
    try:
        with temp_file:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                    raise PayloadTooLargeError(
                        f"Uploaded archive exceeds maximum permitted size of {settings.MAX_UPLOAD_SIZE_BYTES} bytes."
                    )
                temp_file.write(chunk)

        return dataset_service.handle_archive_upload(
            dataset_id=dataset_id,
            archive_path=temp_path,
            filename=filename,
        )
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


@router.get(
    "/{dataset_id}/versions",
    response_model=DatasetVersionListResponse,
    summary="List Dataset Versions",
    description="Retrieve chronological history of all versions created for this dataset.",
)
async def list_dataset_versions(dataset_id: str) -> DatasetVersionListResponse:
    """List all versions for a dataset."""
    dataset = dataset_service.get_dataset(dataset_id)
    if not dataset:
        raise DatasetNotFoundError(dataset_id)
    versions = dataset_service.list_versions(dataset_id)
    return DatasetVersionListResponse(total=len(versions), items=versions)


@router.get(
    "/{dataset_id}/versions/latest",
    response_model=DatasetVersion,
    summary="Get Latest Dataset Version",
    description="Retrieve the latest version record for a dataset.",
)
async def get_latest_dataset_version(dataset_id: str) -> DatasetVersion:
    """Get the most recent version of a dataset."""
    dataset = dataset_service.get_dataset(dataset_id)
    if not dataset:
        raise DatasetNotFoundError(dataset_id)
    version = dataset_service.get_latest_version(dataset_id)
    if not version:
        raise VersionNotFoundError(dataset_id, "latest")
    return version


@router.get(
    "/{dataset_id}/versions/{version_id}",
    response_model=DatasetVersion,
    summary="Get Specific Dataset Version",
    description="Retrieve a specific version record for a dataset by version_id.",
)
async def get_dataset_version(dataset_id: str, version_id: str) -> DatasetVersion:
    """Get a specific version of a dataset."""
    dataset = dataset_service.get_dataset(dataset_id)
    if not dataset:
        raise DatasetNotFoundError(dataset_id)
    version = dataset_service.get_version(dataset_id, version_id)
    if not version:
        raise VersionNotFoundError(dataset_id, version_id)
    return version


@router.post(
    "/{dataset_id}/reanalyze",
    response_model=ProcessingJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-analyze Dataset",
    description="Enqueues a fresh background analysis pipeline execution for the active dataset version.",
)
async def reanalyze_dataset(dataset_id: str) -> ProcessingJob:
    """Enqueue fresh background analysis pipeline for dataset."""
    return dataset_service.reanalyze_dataset(dataset_id)



@router.post(
    "/{dataset_id}/discover",
    response_model=DatasetDiscoveryResult,
    summary="Discover and Ingest Dataset",
)
async def discover_dataset(dataset_id: str) -> DatasetDiscoveryResult:
    """
    Execute filesystem discovery for a registered dataset.
    Scans supported image formats, indexes class hierarchy, and returns structured ingestion metadata.
    """
    return dataset_service.discover_dataset(dataset_id)


@router.get(
    "/{dataset_id}/discovery",
    response_model=DatasetDiscoveryResult,
    summary="Get Dataset Discovery Metadata",
)
async def get_dataset_discovery(dataset_id: str) -> DatasetDiscoveryResult:
    """Retrieve cached discovery metadata for a dataset."""
    result = dataset_service.get_discovery_result(dataset_id)
    if not result:
        raise DatasetNotFoundError(f"{dataset_id} (discovery not yet executed)")
    return result


@router.post(
    "/{dataset_id}/validate",
    response_model=DatasetValidationResult,
    summary="Validate Image Integrity and Decodability",
)
async def validate_dataset(dataset_id: str) -> DatasetValidationResult:
    """
    Execute byte-level integrity verification and decodability validation for discovered images.
    Detects truncated images, zero-byte payloads, unreadable headers, and extracts geometry metadata.
    """
    return dataset_service.validate_dataset(dataset_id)


@router.get(
    "/{dataset_id}/validation",
    response_model=DatasetValidationResult,
    summary="Get Dataset Validation Metadata",
)
async def get_dataset_validation(dataset_id: str) -> DatasetValidationResult:
    """Retrieve previously computed validation metadata for a dataset."""
    return dataset_service.get_validation_result(dataset_id)


@router.post(
    "/{dataset_id}/duplicates/detect",
    response_model=DuplicateAnalysisResult,
    summary="Detect Exact Duplicate Images via SHA-256",
)
async def detect_duplicates(dataset_id: str) -> DuplicateAnalysisResult:
    """
    Execute streaming SHA-256 exact content duplicate detection for validated images.
    Identifies byte-for-byte identical files, canonical representatives, and cross-class duplicates.
    """
    return dataset_service.detect_duplicates(dataset_id)


@router.get(
    "/{dataset_id}/duplicates",
    response_model=DuplicateAnalysisResult,
    summary="Get Exact Duplicate Analysis Metadata",
)
async def get_dataset_duplicates(dataset_id: str) -> DuplicateAnalysisResult:
    """Retrieve previously computed exact duplicate analysis report for a dataset."""
    return dataset_service.get_duplicate_result(dataset_id)


@router.post(
    "/{dataset_id}/near-duplicates/detect",
    response_model=NearDuplicateAnalysisResult,
    summary="Detect Perceptual Near-Duplicate Images",
)
async def detect_near_duplicates(
    dataset_id: str,
    config: Optional[NearDuplicateQueryConfig] = None,
) -> NearDuplicateAnalysisResult:
    """
    Execute perceptual near-duplicate image detection using pHash, dHash, or aHash.
    Identifies visually similar images within configured Hamming distance threshold.
    """
    return dataset_service.detect_near_duplicates(dataset_id, config)


@router.get(
    "/{dataset_id}/near-duplicates",
    response_model=NearDuplicateAnalysisResult,
    summary="Get Near-Duplicate Analysis Metadata",
)
async def get_dataset_near_duplicates(dataset_id: str) -> NearDuplicateAnalysisResult:
    """Retrieve previously computed near-duplicate analysis report for a dataset."""
    return dataset_service.get_near_duplicate_result(dataset_id)


@router.post(
    "/{dataset_id}/analyze",
    response_model=UnifiedAnalysisResult,
    summary="Execute Unified Dataset Analysis",
)
async def analyze_dataset(
    dataset_id: str,
    config: Optional[AnalysisConfig] = None,
) -> UnifiedAnalysisResult:
    """
    Execute end-to-end dataset analysis pipeline (M2.1 through M2.4).
    Consolidates discovery, validation, exact-duplicates, and near-duplicates into a single unified report.
    """
    return dataset_service.analyze_dataset(dataset_id, config)


@router.get(
    "/{dataset_id}/analysis",
    response_model=UnifiedAnalysisResult,
    summary="Get Latest Unified Analysis Report",
)
async def get_dataset_analysis(dataset_id: str) -> UnifiedAnalysisResult:
    """Retrieve the latest unified analysis result computed for this dataset."""
    result = dataset_service.get_latest_analysis(dataset_id)
    if not result:
        raise DatasetAnalysisNotFoundError(dataset_id)
    return result


@router.get(
    "/{dataset_id}/analysis/status",
    response_model=AnalysisStatusResponse,
    summary="Get Latest Analysis Status",
)
async def get_dataset_analysis_status(dataset_id: str) -> AnalysisStatusResponse:
    """Retrieve execution status for the latest analysis of this dataset."""
    from app.services.analysis_service import analysis_service

    latest = dataset_service.get_latest_analysis(dataset_id)
    if not latest:
        raise DatasetAnalysisNotFoundError(dataset_id)
    status_res = analysis_service.get_analysis_status(latest.id)
    if not status_res:
        raise DatasetAnalysisNotFoundError(dataset_id)
    return status_res


@router.post(
    "/{dataset_id}/quality-assessments",
    response_model=DataQualityAssessment,
    summary="Trigger Dataset Quality Assessment",
)
async def assess_dataset_quality(
    dataset_id: str,
    force_refresh: bool = False,
) -> DataQualityAssessment:
    """
    Execute comprehensive dataset quality assessment across image integrity,
    class imbalance, dimensional consistency, and duplicate impacts.
    """
    from app.services.data_quality_service import data_quality_service

    return data_quality_service.assess_dataset(dataset_id, force_refresh=force_refresh)


@router.get(
    "/{dataset_id}/quality-assessment",
    response_model=DataQualityAssessment,
    summary="Get Latest Dataset Quality Assessment",
)
async def get_dataset_quality_assessment(dataset_id: str) -> DataQualityAssessment:
    """Retrieve the latest quality assessment report for a dataset."""
    from app.services.data_quality_service import data_quality_service

    assessment = data_quality_service.get_latest_assessment_for_dataset(dataset_id)
    if not assessment:
        raise DatasetQualityAssessmentNotFoundError(dataset_id)
    return assessment


@router.get(
    "/{dataset_id}/quality-assessment/status",
    response_model=QualityAssessmentStatusResponse,
    summary="Get Latest Dataset Quality Assessment Status",
)
async def get_dataset_quality_assessment_status(
    dataset_id: str,
) -> QualityAssessmentStatusResponse:
    """Retrieve execution status for the latest quality assessment of this dataset."""
    from app.services.data_quality_service import data_quality_service

    assessment = data_quality_service.get_latest_assessment_for_dataset(dataset_id)
    if not assessment:
        raise DatasetQualityAssessmentNotFoundError(dataset_id)
    status_res = data_quality_service.get_assessment_status(assessment.id)
    if not status_res:
        raise DatasetQualityAssessmentNotFoundError(dataset_id)
    return status_res


@router.get(
    "/{dataset_id}/quality-assessment/findings",
    response_model=List[QualityFinding],
    summary="Get Dataset Quality Findings",
)
async def get_dataset_quality_findings(dataset_id: str) -> List[QualityFinding]:
    """Retrieve structured, evidence-backed quality findings and recommendations for a dataset."""
    from app.services.data_quality_service import data_quality_service

    assessment = data_quality_service.get_latest_assessment_for_dataset(dataset_id)
    if not assessment:
        raise DatasetQualityAssessmentNotFoundError(dataset_id)
    return assessment.findings


# ---------------------------------------------------------------------------
# EDA (Exploratory Data Analysis) endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/eda",
    response_model=EdaReport,
    summary="Run Exploratory Data Analysis",
)
async def run_dataset_eda(
    dataset_id: str,
    force_refresh: bool = False,
) -> EdaReport:
    """
    Execute the full EDA pipeline for a dataset.
    Returns comprehensive dataset statistics, distribution analysis, and evidence-backed findings.
    """
    from app.services.eda_service import eda_service

    return eda_service.run_eda(dataset_id, force_refresh=force_refresh)


@router.get(
    "/{dataset_id}/eda",
    response_model=EdaReport,
    summary="Get Latest Dataset EDA Report",
)
async def get_dataset_eda(dataset_id: str) -> EdaReport:
    """Retrieve the latest EDA report for a dataset."""
    from app.services.eda_service import eda_service

    report = eda_service.get_latest_report_for_dataset(dataset_id)
    if not report:
        raise DatasetEdaNotFoundError(dataset_id)
    return report


@router.get(
    "/{dataset_id}/eda/status",
    response_model=EdaStatusResponse,
    summary="Get Latest Dataset EDA Status",
)
async def get_dataset_eda_status(dataset_id: str) -> EdaStatusResponse:
    """Retrieve execution status for the latest EDA report of this dataset."""
    from app.services.eda_service import eda_service

    report = eda_service.get_latest_report_for_dataset(dataset_id)
    if not report:
        raise DatasetEdaNotFoundError(dataset_id)
    status_res = eda_service.get_report_status(report.id)
    if not status_res:
        raise DatasetEdaNotFoundError(dataset_id)
    return status_res


@router.get(
    "/{dataset_id}/eda/findings",
    response_model=List[EdaFinding],
    summary="Get Dataset EDA Findings",
)
async def get_dataset_eda_findings(dataset_id: str) -> List[EdaFinding]:
    """Retrieve structured EDA findings for a dataset."""
    from app.services.eda_service import eda_service

    report = eda_service.get_latest_report_for_dataset(dataset_id)
    if not report:
        raise DatasetEdaNotFoundError(dataset_id)
    return report.findings


# ---------------------------------------------------------------------------
# Visualization Specification endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{dataset_id}/visualizations",
    response_model=VisualizationCollectionResponse,
    summary="Get Dataset Visualizations",
    description="Retrieve all generated visualization specifications and chart-ready data for the active dataset version.",
)
async def get_dataset_visualizations(
    dataset_id: str,
    category: Optional[VisualizationCategory] = Query(None, description="Filter by visualization category"),
    chart_type: Optional[ChartType] = Query(None, description="Filter by canonical chart type"),
) -> VisualizationCollectionResponse:
    """Retrieve visualization specifications for the active dataset version."""
    return visualization_service.get_visualizations(
        dataset_id=dataset_id,
        category=category,
        chart_type=chart_type,
    )


@router.get(
    "/{dataset_id}/visualizations/{visualization_id}",
    response_model=VisualizationSpecification,
    summary="Get Specific Visualization Specification",
    description="Retrieve a single visualization specification by its deterministic identifier.",
)
async def get_dataset_visualization(
    dataset_id: str,
    visualization_id: str,
) -> VisualizationSpecification:
    """Retrieve individual visualization specification."""
    return visualization_service.get_visualization(dataset_id, visualization_id)


@router.get(
    "/{dataset_id}/versions/{version_id}/visualizations",
    response_model=VisualizationCollectionResponse,
    summary="Get Dataset Version Visualizations",
    description="Retrieve visualization specifications scoped to a specific historical or active dataset version.",
)
async def get_dataset_version_visualizations(
    dataset_id: str,
    version_id: str,
    category: Optional[VisualizationCategory] = Query(None, description="Filter by visualization category"),
    chart_type: Optional[ChartType] = Query(None, description="Filter by canonical chart type"),
) -> VisualizationCollectionResponse:
    """Retrieve visualization specifications for a specific dataset version."""
    return visualization_service.get_visualizations(
        dataset_id=dataset_id,
        version_id=version_id,
        category=category,
        chart_type=chart_type,
    )


@router.post(
    "/{dataset_id}/visualizations/regenerate",
    response_model=VisualizationCollectionResponse,
    summary="Regenerate Dataset Visualizations",
    description="Force recomputation and regeneration of all visualization specifications for the dataset.",
)
async def regenerate_dataset_visualizations(
    dataset_id: str,
    version_id: Optional[str] = Query(None, description="Optional target version ID to regenerate"),
) -> VisualizationCollectionResponse:
    """Force recomputation of dataset visualizations."""
    return visualization_service.regenerate_visualizations(
        dataset_id=dataset_id,
        version_id=version_id,
    )


# ---------------------------------------------------------------------------
# M7 — Dataset Insights Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{dataset_id}/insights",
    response_model=InsightCollectionResponse,
    summary="Get Dataset Insights",
    description="Retrieve M7 dataset findings and insights, optionally filtered by category or severity.",
)
async def get_dataset_insights(
    dataset_id: str,
    category: Optional[InsightCategory] = Query(None, description="Filter by insight category"),
    severity: Optional[InsightSeverity] = Query(None, description="Filter by insight severity"),
) -> InsightCollectionResponse:
    """Retrieve M7 insights for a dataset."""
    return insights_service.get_insights(
        dataset_id=dataset_id,
        category=category,
        severity=severity,
    )


@router.get(
    "/{dataset_id}/insights/{insight_id}",
    response_model=DatasetInsight,
    summary="Get Single Dataset Insight",
    description="Retrieve a single M7 insight by its unique identifier.",
)
async def get_dataset_insight_by_id(
    dataset_id: str,
    insight_id: str,
) -> DatasetInsight:
    """Retrieve a single insight by ID."""
    return insights_service.get_insight_by_id(dataset_id=dataset_id, insight_id=insight_id)


@router.get(
    "/{dataset_id}/versions/{version_id}/insights",
    response_model=InsightCollectionResponse,
    summary="Get Dataset Version Insights",
    description="Retrieve M7 insights scoped to a specific dataset version.",
)
async def get_dataset_version_insights(
    dataset_id: str,
    version_id: str,
    category: Optional[InsightCategory] = Query(None, description="Filter by insight category"),
    severity: Optional[InsightSeverity] = Query(None, description="Filter by insight severity"),
) -> InsightCollectionResponse:
    """Retrieve insights for a specific dataset version."""
    return insights_service.get_insights(
        dataset_id=dataset_id,
        version_id=version_id,
        category=category,
        severity=severity,
    )


@router.post(
    "/{dataset_id}/insights/regenerate",
    response_model=InsightCollectionResponse,
    summary="Regenerate Dataset Insights",
    description="Force recomputation and regeneration of all M7 insights for the dataset.",
)
async def regenerate_dataset_insights(
    dataset_id: str,
    version_id: Optional[str] = Query(None, description="Optional target version ID"),
) -> InsightCollectionResponse:
    """Force recomputation of dataset insights."""
    return insights_service.regenerate_insights(
        dataset_id=dataset_id,
        version_id=version_id,
    )

