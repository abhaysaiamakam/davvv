from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.preprocessing import PreprocessingOperationConfig


class ImageClassCount(BaseModel):
    class_name: str
    image_count: int


class DatasetImage(BaseModel):
    image_id: str
    filename: str
    class_name: str
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_bytes: int
    format: Optional[str] = None
    color_mode: Optional[str] = None
    status: str = "valid"
    thumbnail_url: str
    preview_url: str


class DatasetImageListResponse(BaseModel):
    dataset_id: str
    version_id: str
    modality: str = Field(description="Detected from supported image files in this version")
    class_structure: str = Field(description="Directory class structure or unclassified image collection")
    total: int
    page: int
    page_size: int
    classes: List[ImageClassCount]
    items: List[DatasetImage]


class ImagePreprocessingPreviewRequest(BaseModel):
    operation: PreprocessingOperationConfig


class ImagePreprocessingPreviewResponse(BaseModel):
    dataset_id: str
    version_id: str
    image_id: str
    operation_type: str
    original_data_url: str
    preview_data_url: str
    original_metadata: dict
    preview_metadata: dict
    warning: Optional[str] = None


class ImageAnnotation(BaseModel):
    annotation_id: str
    class_id: str
    label: Optional[str] = None
    x: float
    y: float
    width: float
    height: float
    coordinate_system: str = "pixels"
    confidence: Optional[float] = None


class AnnotationClassCount(BaseModel):
    class_id: str
    label: Optional[str] = None
    annotation_count: int
    image_count: int


class ImageAnnotationResponse(BaseModel):
    dataset_id: str
    version_id: str
    image_id: str
    annotation_format: str
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    annotation_count: int
    annotations: List[ImageAnnotation]
    classes: List[AnnotationClassCount]
