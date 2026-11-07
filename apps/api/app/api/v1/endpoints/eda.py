"""Global EDA report endpoints for CropLens."""
from typing import List

from fastapi import APIRouter

from app.core.errors import EdaReportNotFoundError
from app.schemas.eda import EdaFinding, EdaReport, EdaReportListResponse, EdaStatusResponse

router = APIRouter()


@router.get("", response_model=EdaReportListResponse, summary="List EDA Reports")
async def list_eda_reports() -> EdaReportListResponse:
    """List all persisted EDA reports across all datasets."""
    from app.services.eda_service import eda_service

    return eda_service.list_reports()


@router.get("/{eda_id}", response_model=EdaReport, summary="Get EDA Report by ID")
async def get_eda_report(eda_id: str) -> EdaReport:
    """Retrieve a specific EDA report by its identifier."""
    from app.services.eda_service import eda_service

    report = eda_service.get_report(eda_id)
    if not report:
        raise EdaReportNotFoundError(eda_id)
    return report


@router.get("/{eda_id}/status", response_model=EdaStatusResponse, summary="Get EDA Report Status")
async def get_eda_report_status(eda_id: str) -> EdaStatusResponse:
    """Retrieve execution status for an EDA report."""
    from app.services.eda_service import eda_service

    status = eda_service.get_report_status(eda_id)
    if not status:
        raise EdaReportNotFoundError(eda_id)
    return status


@router.get("/{eda_id}/findings", response_model=List[EdaFinding], summary="Get EDA Findings")
async def get_eda_report_findings(eda_id: str) -> List[EdaFinding]:
    """Retrieve structured EDA findings for a specific report."""
    from app.services.eda_service import eda_service

    report = eda_service.get_report(eda_id)
    if not report:
        raise EdaReportNotFoundError(eda_id)
    return report.findings

