from typing import Optional
from fastapi import APIRouter
from app.schemas.readiness import (
    DatasetReadinessAssessment,
    ReadinessAssessRequest,
    TaskContext,
)
from app.services.readiness_service import readiness_service

router = APIRouter()


@router.get(
    "/{dataset_id}/readiness",
    response_model=DatasetReadinessAssessment,
    summary="Get Dataset Readiness Assessment",
)
async def get_dataset_readiness(
    dataset_id: str,
) -> DatasetReadinessAssessment:
    """Retrieve multi-dimensional dataset readiness assessment for the latest version."""
    return readiness_service.get_readiness_assessment(dataset_id)


@router.post(
    "/{dataset_id}/readiness/assess",
    response_model=DatasetReadinessAssessment,
    summary="Evaluate Dataset Readiness",
)
async def assess_dataset_readiness(
    dataset_id: str,
    req: Optional[ReadinessAssessRequest] = None,
) -> DatasetReadinessAssessment:
    """Evaluate or re-evaluate dataset readiness with optional task context."""
    version_id = req.version_id if req else None
    task_context = req.task_context if req else None
    return readiness_service.assess_readiness(
        dataset_id=dataset_id,
        version_id=version_id,
        task_context=task_context,
    )


@router.get(
    "/{dataset_id}/versions/{version_id}/readiness",
    response_model=DatasetReadinessAssessment,
    summary="Get Readiness for Specific Version",
)
async def get_version_readiness(
    dataset_id: str,
    version_id: str,
) -> DatasetReadinessAssessment:
    """Retrieve multi-dimensional dataset readiness assessment for a specific dataset version."""
    return readiness_service.get_readiness_assessment(dataset_id, version_id)
