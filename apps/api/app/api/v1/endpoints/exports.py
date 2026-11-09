from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.exports import ExportCreateRequest, ExportJobResponse
from app.services.export_job_service import export_job_service

router = APIRouter()


@router.post("/datasets/{dataset_id}/versions/{version_id}/exports", response_model=ExportJobResponse, status_code=202)
def create_export(dataset_id: str, version_id: str, request: ExportCreateRequest) -> ExportJobResponse:
    try:
        return export_job_service.create(dataset_id, version_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/datasets/{dataset_id}/versions/{version_id}/exports", response_model=list[ExportJobResponse])
def list_exports(dataset_id: str, version_id: str) -> list[ExportJobResponse]:
    return export_job_service.list_for_version(dataset_id, version_id)


@router.get("/exports/{export_id}", response_model=ExportJobResponse)
def get_export(export_id: str) -> ExportJobResponse:
    job = export_job_service.get(export_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export not found")
    return job


@router.get("/exports/{export_id}/download")
def download_export(export_id: str):
    job = export_job_service.get(export_id)
    artifact = export_job_service.download_path(export_id)
    if not job or job.status != "completed" or not artifact:
        raise HTTPException(status_code=404, detail="Export is not ready for download")
    path, filename = artifact
    content_type = {
        ".csv": "text/csv; charset=utf-8", ".json": "application/json",
        ".pdf": "application/pdf", ".zip": "application/zip",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=content_type, filename=filename)
