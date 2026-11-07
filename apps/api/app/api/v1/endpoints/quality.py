from typing import List
from fastapi import APIRouter
from app.core.errors import QualityAssessmentNotFoundError
from app.schemas.quality import (
    DataQualityAssessment,
    QualityAssessmentListResponse,
    QualityAssessmentStatusResponse,
    QualityFinding,
)
from app.services.data_quality_service import data_quality_service

router = APIRouter()


@router.get("", response_model=QualityAssessmentListResponse, summary="List Quality Assessments")
async def list_quality_assessments() -> QualityAssessmentListResponse:
    """Return all historical and completed dataset quality assessments."""
    return data_quality_service.list_assessments()


@router.get("/{assessment_id}", response_model=DataQualityAssessment, summary="Get Quality Assessment")
async def get_quality_assessment(assessment_id: str) -> DataQualityAssessment:
    """Retrieve full data quality assessment report by assessment identifier."""
    assessment = data_quality_service.get_assessment(assessment_id)
    if not assessment:
        raise QualityAssessmentNotFoundError(assessment_id)
    return assessment


@router.get(
    "/{assessment_id}/status",
    response_model=QualityAssessmentStatusResponse,
    summary="Get Quality Assessment Status",
)
async def get_quality_assessment_status(assessment_id: str) -> QualityAssessmentStatusResponse:
    """Retrieve execution lifecycle status for an assessment."""
    status_res = data_quality_service.get_assessment_status(assessment_id)
    if not status_res:
        raise QualityAssessmentNotFoundError(assessment_id)
    return status_res


@router.get(
    "/{assessment_id}/findings",
    response_model=List[QualityFinding],
    summary="Get Quality Assessment Findings",
)
async def get_quality_assessment_findings(assessment_id: str) -> List[QualityFinding]:
    """Retrieve structured quality findings and recommendations for an assessment."""
    assessment = data_quality_service.get_assessment(assessment_id)
    if not assessment:
        raise QualityAssessmentNotFoundError(assessment_id)
    return assessment.findings

