"""
API endpoint for on-demand image thumbnails and high-performance visual previews.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services.dataset_service import dataset_service
from app.services.image_thumbnail_service import image_thumbnail_service

router = APIRouter()


@router.get(
    "/datasets/{dataset_id}/images/thumbnail",
    response_class=FileResponse,
    summary="Retrieve image thumbnail with on-demand disk caching",
)
def get_image_thumbnail(
    dataset_id: str,
    image_path: str = Query(..., description="Relative path of image within dataset archive"),
    version_id: Optional[str] = Query(None, description="Dataset version ID"),
    max_dim: int = Query(300, ge=50, le=1000, description="Maximum width/height dimension in pixels"),
):
    """Serve a scaled, cached thumbnail for an image dataset file without loading full-resolution image bytes."""
    v_info = dataset_service.get_version_info(dataset_id, version_id)
    if not v_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset or version not found for dataset '{dataset_id}'",
        )

    try:
        thumb_path, mime_type = image_thumbnail_service.get_or_create_thumbnail(
            dataset_root=v_info.extracted_dir,
            relative_image_path=image_path,
            max_dim=max_dim,
        )
        return FileResponse(
            path=thumb_path,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image file '{image_path}' not found in dataset version '{v_info.version_id}'",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate thumbnail: {str(exc)}",
        )
