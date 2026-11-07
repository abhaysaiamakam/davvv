"""
M9 — Feature Engineering API Endpoints.

Provides FastAPI routes for inspecting available features, previewing transformations,
applying feature engineering, and reviewing feature operation audit histories.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query, status

from app.schemas.feature_engineering import (
    AvailableFeaturesResponse,
    FeatureApplyRequest,
    FeatureApplyResponse,
    FeatureHistoryListResponse,
    FeatureHistoryRecord,
    FeaturePreviewRequest,
    FeaturePreviewResponse,
)
from app.services.feature_engineering.feature_engineering_service import feature_engineering_service

router = APIRouter()


@router.get(
    "/{dataset_id}/feature-engineering/features",
    response_model=AvailableFeaturesResponse,
    summary="Get Available Dataset Features",
    description="Inspect discovered features and available feature engineering operations.",
)
async def get_available_features(dataset_id: str) -> AvailableFeaturesResponse:
    """List dataset features and available feature operations."""
    return feature_engineering_service.get_available_features(dataset_id)


@router.post(
    "/{dataset_id}/feature-engineering/preview",
    response_model=FeaturePreviewResponse,
    summary="Preview Feature Engineering",
    description="Simulate feature transformations, selections, or PCA in a sandbox without mutating source data.",
)
async def preview_feature_engineering(
    dataset_id: str,
    req: FeaturePreviewRequest,
) -> FeaturePreviewResponse:
    """Preview feature engineering operations."""
    req.dataset_id = dataset_id
    return feature_engineering_service.preview_features(req)


@router.post(
    "/{dataset_id}/feature-engineering/apply",
    response_model=FeatureApplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply Feature Engineering",
    description="Execute feature operations, generate a derived dataset version, and trigger re-analysis.",
)
async def apply_feature_engineering(
    dataset_id: str,
    req: FeatureApplyRequest,
) -> FeatureApplyResponse:
    """Execute feature engineering and create derived version."""
    req.dataset_id = dataset_id
    return feature_engineering_service.apply_features(req)


@router.get(
    "/{dataset_id}/feature-engineering/history",
    response_model=FeatureHistoryListResponse,
    summary="List Feature Engineering History",
    description="Retrieve the audit trail of applied feature engineering operations.",
)
async def list_feature_history(dataset_id: str) -> FeatureHistoryListResponse:
    """List feature history records."""
    return feature_engineering_service.list_feature_history(dataset_id)
