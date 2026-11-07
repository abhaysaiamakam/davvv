from typing import Optional
from fastapi import APIRouter, Query, Response
from app.schemas.reports import (
    AnalyticalReport,
    ReportExportFormat,
    ReportGenerateRequest,
    ReportListResponse,
)
from app.services.report_service import report_service

router = APIRouter()


@router.post(
    "/{dataset_id}/reports/generate",
    response_model=AnalyticalReport,
    summary="Generate Analytical Report",
)
async def generate_report(
    dataset_id: str,
    req: Optional[ReportGenerateRequest] = None,
) -> AnalyticalReport:
    """Generate or retrieve cached evidence-backed analytical report."""
    if req is None:
        req = ReportGenerateRequest(dataset_id=dataset_id)
    else:
        req.dataset_id = dataset_id
    return report_service.generate_report(req)


@router.get(
    "/{dataset_id}/reports",
    response_model=ReportListResponse,
    summary="List Analytical Reports",
)
async def list_reports(
    dataset_id: str,
) -> ReportListResponse:
    """List generated analytical reports for a dataset."""
    return report_service.list_reports(dataset_id)


@router.get(
    "/{dataset_id}/reports/{report_id}",
    response_model=AnalyticalReport,
    summary="Get Analytical Report",
)
async def get_report(
    dataset_id: str,
    report_id: str,
) -> AnalyticalReport:
    """Retrieve full analytical report by ID."""
    return report_service.get_report(report_id)


@router.get(
    "/{dataset_id}/reports/{report_id}/download",
    summary="Download Analytical Report Export",
)
async def download_report(
    dataset_id: str,
    report_id: str,
    format: ReportExportFormat = Query(default=ReportExportFormat.JSON, description="Export format: json or pdf"),
) -> Response:
    """Download analytical report as JSON or compiled PDF document."""
    content_bytes, media_type, filename = report_service.download_report(
        dataset_id=dataset_id,
        report_id=report_id,
        export_format=format,
    )
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content_bytes, media_type=media_type, headers=headers)


@router.get(
    "/{dataset_id}/versions/{version_id}/reports",
    response_model=ReportListResponse,
    summary="List Reports for Version",
)
async def list_version_reports(
    dataset_id: str,
    version_id: str,
) -> ReportListResponse:
    """List analytical reports generated for a specific dataset version."""
    return report_service.list_reports(dataset_id, version_id)
