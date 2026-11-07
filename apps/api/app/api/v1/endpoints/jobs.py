"""
M6 — Processing Job API Endpoints.

Provides status monitoring, lifecycle inspection, listing, and retry capability
for asynchronous background dataset analysis jobs.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.errors import JobNotFoundError
from app.schemas.job import (
    JobListResponse,
    JobStatus,
    JobStatusResponse,
    ProcessingJob,
)
from app.services.job_service import job_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=JobListResponse,
    summary="List processing jobs",
    description="Retrieve processing jobs matching optional dataset_id and status filters, ordered newest first.",
)
def list_jobs(
    dataset_id: Optional[str] = Query(None, description="Filter by target dataset identifier"),
    status: Optional[JobStatus] = Query(None, description="Filter by job execution status"),
) -> JobListResponse:
    """List all processing jobs matching optional criteria."""
    jobs = job_service.list_jobs(dataset_id=dataset_id, status=status)
    return JobListResponse(total=len(jobs), items=jobs)


@router.get(
    "/{job_id}",
    response_model=ProcessingJob,
    summary="Get processing job details",
    description="Retrieve the full lifecycle state, stage, progress, and artifact references for a job.",
)
def get_job(job_id: str) -> ProcessingJob:
    """Retrieve full processing job record."""
    job = job_service.get_job(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return job


@router.get(
    "/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get lightweight job status",
    description="Retrieve a lightweight status payload suitable for polling UI progress bars.",
)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Retrieve lightweight job status."""
    job = job_service.get_job(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return JobStatusResponse(
        job_id=job.job_id,
        dataset_id=job.dataset_id,
        dataset_version=job.dataset_version,
        status=job.status,
        current_stage=job.current_stage,
        progress_pct=job.progress_pct,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=job.duration_ms,
        error_message=job.error_message,
    )


@router.post(
    "/{job_id}/retry",
    response_model=ProcessingJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed processing job",
    description="Submits a failed job for re-execution through the background analysis pipeline.",
)
def retry_job(job_id: str) -> ProcessingJob:
    """Retry a failed processing job."""
    return job_service.retry_job(job_id)

