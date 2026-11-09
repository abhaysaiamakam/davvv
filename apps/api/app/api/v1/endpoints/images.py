from __future__ import annotations

import hashlib
from PIL import Image
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.schemas.image_explorer import (
    DatasetImageListResponse,
    ImageAnnotationResponse,
    ImagePreprocessingPreviewRequest,
    ImagePreprocessingPreviewResponse,
)
from app.services.image_explorer_service import image_explorer_service
from app.services.image_thumbnail_service import image_thumbnail_service
from app.storage.local import storage_backend

router = APIRouter()


@router.get(
    "/datasets/{dataset_id}/versions/{version_id}/images",
    response_model=DatasetImageListResponse,
    summary="List images in a dataset version",
)
def list_version_images(
    dataset_id: str,
    version_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    class_name: str | None = Query(None),
    search: str | None = Query(None, max_length=160),
    sort_by: str = Query("filename", pattern="^(filename|file_size|width|height)$"),
    descending: bool = Query(False),
    annotation_class_id: str | None = Query(None, max_length=80),
    crop: str | None = Query(None, max_length=80),
) -> DatasetImageListResponse:
    return image_explorer_service.list_images(
        dataset_id, version_id, page, page_size, class_name, search, sort_by, descending, annotation_class_id, crop
    )


@router.get("/datasets/{dataset_id}/versions/{version_id}/images/{image_id}/thumbnail")
def get_version_image_thumbnail(
    dataset_id: str,
    version_id: str,
    image_id: str,
    max_dim: int = Query(320, ge=50, le=1000),
):
    try:
        root = image_explorer_service._version_root(dataset_id, version_id)
        source = image_explorer_service.image_path(dataset_id, version_id, image_id)
        relative = source.relative_to(root).as_posix()
        cache_key = hashlib.sha256(f"{dataset_id}:{version_id}".encode()).hexdigest()
        path, mime_type = image_thumbnail_service.get_or_create_thumbnail(
            root, relative, max_dim=max_dim,
            cache_root=storage_backend.results_dir / "image-thumbnails" / cache_key,
        )
        return FileResponse(path, media_type=mime_type, headers={"Cache-Control": "private, max-age=86400"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found in this dataset version")
    except Exception:
        raise HTTPException(status_code=422, detail="Image thumbnail could not be generated")


@router.get("/datasets/{dataset_id}/versions/{version_id}/images/{image_id}")
def get_version_image_metadata(dataset_id: str, version_id: str, image_id: str):
    try:
        return image_explorer_service.get_image(dataset_id, version_id, image_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found in this dataset version")


@router.get("/datasets/{dataset_id}/versions/{version_id}/images/{image_id}/preview")
def get_version_image_preview(dataset_id: str, version_id: str, image_id: str):
    try:
        path = image_explorer_service.image_path(dataset_id, version_id, image_id)
        with Image.open(path) as image:
            fmt = (image.format or "").upper()
        mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "BMP": "image/bmp", "TIFF": "image/tiff"}.get(fmt)
        if not mime:
            raise ValueError("Unsupported image media type")
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found in this dataset version")
    except Exception:
        raise HTTPException(status_code=404, detail="Dataset image is unavailable")


@router.get(
    "/datasets/{dataset_id}/versions/{version_id}/images/{image_id}/annotations",
    response_model=ImageAnnotationResponse,
)
def get_version_image_annotations(dataset_id: str, version_id: str, image_id: str):
    try:
        return image_explorer_service.get_annotations(dataset_id, version_id, image_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found in this dataset version")


@router.post(
    "/datasets/{dataset_id}/versions/{version_id}/images/{image_id}/preprocessing-preview",
    response_model=ImagePreprocessingPreviewResponse,
)
def preview_image_preprocessing(
    dataset_id: str,
    version_id: str,
    image_id: str,
    request: ImagePreprocessingPreviewRequest,
) -> ImagePreprocessingPreviewResponse:
    try:
        return image_explorer_service.preview_preprocessing(
            dataset_id, version_id, image_id, request.operation
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found in this dataset version")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=422, detail="Image preprocessing preview failed")
