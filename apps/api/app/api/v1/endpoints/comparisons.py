"""
M5 — Dataset Comparison API Endpoints.

Provides global pairwise comparison between any two analyzed datasets.
"""
import logging
from typing import List

from fastapi import APIRouter, status

from app.core.errors import ComparisonNotFoundError
from app.schemas.comparison import (
    ComparisonCreateRequest,
    ComparisonFinding,
    ComparisonFreshnessResponse,
    ComparisonStatusResponse,
    DatasetComparisonListResponse,
    DatasetComparisonReport,
)
from app.services.comparison_service import comparison_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=DatasetComparisonReport,
    status_code=status.HTTP_200_OK,
    summary="Run or retrieve dataset comparison",
    description=(
        "Executes a pairwise comparison between two datasets using their latest "
        "persisted M2 analysis, M3 quality, and M4 EDA results. If a comparison "
        "already exists for this pair and force_refresh is False, the cached result is returned."
    ),
)
def run_comparison(request: ComparisonCreateRequest) -> DatasetComparisonReport:
    """Compare two datasets side-by-side."""
    return comparison_service.run_comparison(
        dataset_a_id=request.dataset_a_id,
        dataset_b_id=request.dataset_b_id,
        force_refresh=request.force_refresh,
    )


@router.get(
    "",
    response_model=DatasetComparisonListResponse,
    summary="List all dataset comparisons",
    description="Retrieve high-level summaries of all persisted dataset comparisons, sorted newest first.",
)
def list_comparisons() -> DatasetComparisonListResponse:
    """List all persisted comparison records."""
    return comparison_service.list_comparisons()


@router.get(
    "/{comparison_id}",
    response_model=DatasetComparisonReport,
    summary="Get comparison report by ID",
    description="Retrieve the complete dataset comparison report by its unique ID.",
)
def get_comparison(comparison_id: str) -> DatasetComparisonReport:
    """Retrieve full comparison report."""
    report = comparison_service.get_comparison(comparison_id)
    if not report:
        raise ComparisonNotFoundError(comparison_id)
    return report


@router.get(
    "/{comparison_id}/status",
    response_model=ComparisonStatusResponse,
    summary="Get comparison status",
    description="Check the execution and availability status of a comparison.",
)
def get_comparison_status(comparison_id: str) -> ComparisonStatusResponse:
    """Retrieve comparison status."""
    st = comparison_service.get_comparison_status(comparison_id)
    if not st:
        raise ComparisonNotFoundError(comparison_id)
    return st


@router.get(
    "/{comparison_id}/findings",
    response_model=List[ComparisonFinding],
    summary="Get comparison findings",
    description="Retrieve evidence-backed comparative findings and differences for a comparison.",
)
def get_comparison_findings(comparison_id: str) -> List[ComparisonFinding]:
    """Retrieve comparison findings."""
    report = comparison_service.get_comparison(comparison_id)
    if not report:
        raise ComparisonNotFoundError(comparison_id)
    return report.findings


@router.get(
    "/{comparison_id}/freshness",
    response_model=ComparisonFreshnessResponse,
    summary="Check comparison freshness",
    description="Determine if comparison inputs are up-to-date with current dataset versions or stale.",
)
def get_comparison_freshness(comparison_id: str) -> ComparisonFreshnessResponse:
    """Retrieve comparison freshness status."""
    return comparison_service.check_freshness(comparison_id)

