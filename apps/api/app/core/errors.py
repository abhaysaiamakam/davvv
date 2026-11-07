import datetime
import logging
from typing import List, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.error import ApiErrorResponse

logger = logging.getLogger(__name__)


class CropLensBaseException(Exception):
    """Base exception for CropLens platform."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_SERVER_ERROR",
    ):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code


class DatasetNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Dataset with ID or slug '{dataset_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_NOT_FOUND",
        )


class DatasetDirectoryNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str, relative_path: str = ""):
        path_hint = f" at '{relative_path}'" if relative_path else ""
        super().__init__(
            detail=f"Dataset directory for '{dataset_id}' does not exist on filesystem{path_hint}.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_DIRECTORY_NOT_FOUND",
        )


class DatasetNotUploadedError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Evaluator dataset '{dataset_id}' has not been uploaded yet.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="DATASET_NOT_UPLOADED",
        )


class DatasetNotDiscoveredError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Dataset '{dataset_id}' must be discovered before validation can be run.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="DATASET_NOT_DISCOVERED",
        )


class DatasetNotValidatedError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Validation has not been computed for dataset '{dataset_id}'. Run POST /api/v1/datasets/{dataset_id}/validate first.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="DATASET_NOT_VALIDATED",
        )


class DuplicateAnalysisNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Duplicate analysis has not been performed for dataset '{dataset_id}'. Run POST /api/v1/datasets/{dataset_id}/duplicates/detect first.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DUPLICATE_ANALYSIS_NOT_FOUND",
        )


class NearDuplicateAnalysisNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Near-duplicate analysis has not been performed for dataset '{dataset_id}'. Run POST /api/v1/datasets/{dataset_id}/near-duplicates/detect first.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NEAR_DUPLICATE_ANALYSIS_NOT_FOUND",
        )


class InvalidPerceptualHashAlgorithmError(CropLensBaseException):
    def __init__(self, algorithm: str, supported: List[str]):
        super().__init__(
            detail=f"Unsupported perceptual hash algorithm '{algorithm}'. Supported algorithms: {', '.join(supported)}.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_HASH_ALGORITHM",
        )


class InvalidHammingThresholdError(CropLensBaseException):
    def __init__(self, threshold: int, max_allowed: int):
        super().__init__(
            detail=f"Invalid distance threshold '{threshold}'. Must be between 0 and {max_allowed}.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_DISTANCE_THRESHOLD",
        )


class AnalysisNotFoundError(CropLensBaseException):
    def __init__(self, analysis_id: str):
        super().__init__(
            detail=f"Analysis job '{analysis_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ANALYSIS_NOT_FOUND",
        )


class DatasetAnalysisNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Analysis has not been performed for dataset '{dataset_id}'. Run POST /api/v1/datasets/{dataset_id}/analyze first.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_ANALYSIS_NOT_FOUND",
        )


class QualityAssessmentNotFoundError(CropLensBaseException):
    def __init__(self, assessment_id: str):
        super().__init__(
            detail=f"Quality assessment '{assessment_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="QUALITY_ASSESSMENT_NOT_FOUND",
        )


class DatasetQualityAssessmentNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Quality assessment has not been performed for dataset '{dataset_id}'. Run POST /api/v1/datasets/{dataset_id}/quality-assessments first.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_QUALITY_ASSESSMENT_NOT_FOUND",
        )


class EdaReportNotFoundError(CropLensBaseException):
    def __init__(self, eda_id: str):
        super().__init__(
            detail=f"EDA report '{eda_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EDA_REPORT_NOT_FOUND",
        )


class DatasetEdaNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"EDA has not been executed for dataset '{dataset_id}'. Run POST /api/v1/datasets/{dataset_id}/eda first.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_EDA_NOT_FOUND",
        )


class DatasetVisualizationsNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Visualizations have not been generated for dataset '{dataset_id}'.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_VISUALIZATIONS_NOT_FOUND",
        )


class VisualizationNotFoundError(CropLensBaseException):
    def __init__(self, visualization_id: str):
        super().__init__(
            detail=f"Visualization specification '{visualization_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="VISUALIZATION_NOT_FOUND",
        )


class VisualizationGenerationError(CropLensBaseException):
    def __init__(self, dataset_id: str, detail: str = "Visualization generation failed."):
        super().__init__(
            detail=f"Visualization generation failed for dataset '{dataset_id}': {detail}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="VISUALIZATION_GENERATION_FAILED",
        )


class ComparisonNotFoundError(CropLensBaseException):
    def __init__(self, comparison_id: str):
        super().__init__(
            detail=f"Comparison report '{comparison_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COMPARISON_NOT_FOUND",
        )


class ComparisonPrerequisiteError(CropLensBaseException):
    def __init__(self, dataset_id: str, reason: str):
        super().__init__(
            detail=f"Cannot compare dataset '{dataset_id}': {reason}",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="COMPARISON_PREREQUISITE_MISSING",
        )


class SelfComparisonError(CropLensBaseException):
    def __init__(self):
        super().__init__(
            detail="A dataset cannot be compared with itself. Provide two distinct dataset IDs.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="SELF_COMPARISON_NOT_ALLOWED",
        )


class DatasetAlreadyExistsError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"Dataset with ID '{dataset_id}' already exists in registry.",
            status_code=status.HTTP_409_CONFLICT,
            error_code="DATASET_ALREADY_EXISTS",
        )


class InvalidArchiveError(CropLensBaseException):
    def __init__(self, detail: str = "Invalid or unsupported dataset archive format."):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_ARCHIVE_FORMAT",
        )


class ArchiveExtractionError(CropLensBaseException):
    def __init__(self, detail: str):
        super().__init__(
            detail=f"Failed to extract dataset archive: {detail}",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ARCHIVE_EXTRACTION_FAILED",
        )


class ArchiveSecurityError(CropLensBaseException):
    def __init__(self, detail: str = "Archive contains unsafe or unauthorized path structures."):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ARCHIVE_SECURITY_VIOLATION",
        )


class DatasetEmptyError(CropLensBaseException):
    def __init__(self, detail: str = "Uploaded dataset archive contains zero valid supported image files."):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="DATASET_EMPTY",
        )


class JobNotFoundError(CropLensBaseException):
    def __init__(self, job_id: str):
        super().__init__(
            detail=f"Processing job '{job_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="JOB_NOT_FOUND",
        )


class VersionNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str, version_id: str):
        super().__init__(
            detail=f"Version '{version_id}' for dataset '{dataset_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_VERSION_NOT_FOUND",
        )


class InvalidDatasetStateError(CropLensBaseException):
    def __init__(self, detail: str = "Dataset is in an invalid or corrupted state."):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_DATASET_STATE",
        )


class JobAlreadyRunningError(CropLensBaseException):
    def __init__(self, dataset_id: str, version_id: str):
        super().__init__(
            detail=f"An analysis job is already active for dataset '{dataset_id}' version '{version_id}'.",
            status_code=status.HTTP_409_CONFLICT,
            error_code="JOB_ALREADY_RUNNING",
        )


class PayloadTooLargeError(CropLensBaseException):
    def __init__(self, detail: str = "Uploaded payload exceeds permitted resource boundaries."):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            error_code="PAYLOAD_TOO_LARGE",
        )


class DatasetInsightsNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str):
        super().__init__(
            detail=f"No insights have been generated for dataset '{dataset_id}' yet. Run the analysis pipeline or POST /insights/regenerate.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DATASET_INSIGHTS_NOT_FOUND",
        )


class InsightNotFoundError(CropLensBaseException):
    def __init__(self, insight_id: str):
        super().__init__(
            detail=f"Insight with ID '{insight_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="INSIGHT_NOT_FOUND",
        )


class PreprocessingError(CropLensBaseException):
    def __init__(self, detail: str):
        super().__init__(
            detail=f"Preprocessing operation failed: {detail}",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PREPROCESSING_OPERATION_FAILED",
        )


class PreprocessingValidationError(CropLensBaseException):
    def __init__(self, detail: str):
        super().__init__(
            detail=f"Preprocessing configuration invalid: {detail}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="PREPROCESSING_VALIDATION_ERROR",
        )


class PreprocessingOperationNotFoundError(CropLensBaseException):
    def __init__(self, operation_type: str):
        super().__init__(
            detail=f"Preprocessing operation '{operation_type}' is not recognized or supported for this dataset.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PREPROCESSING_OPERATION_NOT_FOUND",
        )


class PreprocessingHistoryNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str, version_id: Optional[str] = None):
        scope = f" version '{version_id}'" if version_id else ""
        super().__init__(
            detail=f"No preprocessing history found for dataset '{dataset_id}'{scope}.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PREPROCESSING_HISTORY_NOT_FOUND",
        )


class ReadinessAssessmentNotFoundError(CropLensBaseException):
    def __init__(self, dataset_id: str, version_id: Optional[str] = None):
        scope = f" version '{version_id}'" if version_id else ""
        super().__init__(
            detail=f"No readiness assessment found for dataset '{dataset_id}'{scope}.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="READINESS_ASSESSMENT_NOT_FOUND",
        )


class ReportNotFoundError(CropLensBaseException):
    def __init__(self, report_id: str):
        super().__init__(
            detail=f"Analytical report with ID '{report_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="REPORT_NOT_FOUND",
        )


class ReportExportError(CropLensBaseException):
    def __init__(self, detail: str):
        super().__init__(
            detail=f"Report export failed: {detail}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="REPORT_EXPORT_FAILED",
        )


class StorageError(CropLensBaseException):
    def __init__(self, detail: str):
        super().__init__(
            detail=f"Storage operation failed: {detail}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="STORAGE_OPERATION_FAILED",
        )


class PathTraversalError(CropLensBaseException):
    def __init__(self):
        super().__init__(
            detail="Access denied: Path traversal detected.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_STORAGE_PATH",
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CropLensBaseException)
    async def croplens_exception_handler(request: Request, exc: CropLensBaseException):
        logger.warning(f"Handled application exception on {request.url.path}: {exc.detail}")
        payload = ApiErrorResponse(
            detail=exc.detail,
            status_code=exc.status_code,
            error_code=exc.error_code,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.info(f"Validation error on {request.url.path}: {exc.errors()}")
        first_error = exc.errors()[0] if exc.errors() else {"msg": "Validation failed"}
        msg = f"{first_error.get('loc', ('input',))[-1]}: {first_error.get('msg', 'Invalid input')}"
        payload = ApiErrorResponse(
            detail=f"Request validation failed: {msg}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=payload.model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        payload = ApiErrorResponse(
            detail=str(exc.detail),
            status_code=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled server error on {request.url.path}: {exc}")
        payload = ApiErrorResponse(
            detail="An unexpected internal server error occurred.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR",
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=payload.model_dump(),
        )

