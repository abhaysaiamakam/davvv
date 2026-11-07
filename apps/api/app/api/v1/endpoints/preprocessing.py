"""
M8 — Preprocessing API Endpoints.

Provides FastAPI routes for inspecting available preprocessing operations,
previewing cleaning transformations, executing derived dataset cleaning,
and querying operation history.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query, status

from app.schemas.preprocessing import (
    AvailableOperationsResponse,
    PreprocessingApplyRequest,
    PreprocessingApplyResponse,
    PreprocessingHistoryListResponse,
    PreprocessingHistoryRecord,
    PreprocessingPreviewRequest,
    PreprocessingPreviewResponse,
)
from app.services.preprocessing.preprocessing_service import preprocessing_service

router = APIRouter()


@router.get(
    "/{dataset_id}/preprocessing/operations",
    response_model=AvailableOperationsResponse,
    summary="Get Available Preprocessing Operations",
    description="Retrieve all dataset cleaning operations applicable to the modalities detected in the dataset.",
)
async def get_available_preprocessing_operations(dataset_id: str) -> AvailableOperationsResponse:
    """List available operations for dataset modalities."""
    return preprocessing_service.get_available_operations(dataset_id)


@router.post(
    "/{dataset_id}/preprocessing/preview",
    response_model=PreprocessingPreviewResponse,
    summary="Preview Preprocessing Operations",
    description="Simulate ordered preprocessing operations in a sandbox without mutating the source dataset.",
)
async def preview_preprocessing_operations(
    dataset_id: str,
    req: PreprocessingPreviewRequest,
) -> PreprocessingPreviewResponse:
    """Preview transformations and before/after metrics."""
    # Ensure dataset_id in URL matches request body
    req.dataset_id = dataset_id
    return preprocessing_service.preview_operations(req)


@router.post(
    "/{dataset_id}/preprocessing/apply",
    response_model=PreprocessingApplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply Preprocessing Operations",
    description="Execute preprocessing operations, generate a derived dataset version, compute fingerprints, and enqueue re-analysis.",
)
async def apply_preprocessing_operations(
    dataset_id: str,
    req: PreprocessingApplyRequest,
) -> PreprocessingApplyResponse:
    """Execute preprocessing and create derived dataset version."""
    req.dataset_id = dataset_id
    return preprocessing_service.apply_operations(req)


@router.get(
    "/{dataset_id}/preprocessing/history",
    response_model=PreprocessingHistoryListResponse,
    summary="List Preprocessing History",
    description="Retrieve the complete audit trail of applied preprocessing operations for a dataset.",
)
async def list_preprocessing_history(dataset_id: str) -> PreprocessingHistoryListResponse:
    """List all preprocessing history records for dataset."""
    return preprocessing_service.list_preprocessing_history(dataset_id)


@router.get(
    "/{dataset_id}/versions/{version_id}/preprocessing/history",
    response_model=PreprocessingHistoryRecord,
    summary="Get Version Preprocessing History",
    description="Retrieve preprocessing history specifically associated with a derived dataset version.",
)
async def get_version_preprocessing_history(
    dataset_id: str,
    version_id: str,
) -> PreprocessingHistoryRecord:
    """Get history for a specific dataset version."""
    return preprocessing_service.get_preprocessing_history(dataset_id, version_id)
