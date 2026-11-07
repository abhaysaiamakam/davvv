from fastapi import APIRouter
from app.core.errors import AnalysisNotFoundError
from app.schemas.analysis import (
    AnalysisCreateRequest,
    AnalysisListResponse,
    AnalysisStatusResponse,
    UnifiedAnalysisResult,
)
from app.services.analysis_service import analysis_service

router = APIRouter()


@router.get("", response_model=AnalysisListResponse, summary="List Analysis Jobs")
async def list_analyses() -> AnalysisListResponse:
    """Returns all registered and completed analysis jobs, newest first."""
    return analysis_service.list_analyses()


@router.post("", response_model=UnifiedAnalysisResult, summary="Trigger Unified Analysis")
async def create_analysis(request: AnalysisCreateRequest) -> UnifiedAnalysisResult:
    """
    Trigger end-to-end unified analysis pipeline for a dataset.
    Orchestrates discovery, validation, exact-duplicate, and near-duplicate detection.
    """
    return analysis_service.run_analysis(request.dataset_id, request.config)


@router.get("/{analysis_id}", response_model=UnifiedAnalysisResult, summary="Get Analysis Details")
async def get_analysis(analysis_id: str) -> UnifiedAnalysisResult:
    """Retrieve full unified analysis report for a specific analysis run."""
    analysis = analysis_service.get_analysis(analysis_id)
    if not analysis:
        raise AnalysisNotFoundError(analysis_id)
    return analysis


@router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse, summary="Get Analysis Status")
async def get_analysis_status(analysis_id: str) -> AnalysisStatusResponse:
    """Retrieve execution status and completed stages for a specific analysis run."""
    status_res = analysis_service.get_analysis_status(analysis_id)
    if not status_res:
        raise AnalysisNotFoundError(analysis_id)
    return status_res


