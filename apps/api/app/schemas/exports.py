from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field


class ExportType(str, enum.Enum):
    COMPREHENSIVE = "comprehensive"
    EDA = "eda"
    QUALITY = "quality"
    PREPROCESSING = "preprocessing"
    FEATURE_ENGINEERING = "feature_engineering"
    READINESS = "readiness"
    METHODOLOGY = "methodology"
    DATASET = "dataset"


class ExportFormat(str, enum.Enum):
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"
    ZIP = "zip"


class ExportCreateRequest(BaseModel):
    export_type: ExportType = ExportType.COMPREHENSIVE
    format: ExportFormat
    include_methodology: bool = True
    include_visualizations: bool = False
    title: Optional[str] = Field(default=None, max_length=160)


class ExportJobResponse(BaseModel):
    export_id: str
    dataset_id: str
    version_id: str
    export_type: ExportType
    format: ExportFormat
    status: str
    progress_pct: float = 0
    created_at: str
    completed_at: Optional[str] = None
    filename: Optional[str] = None
    download_url: Optional[str] = None
    error_message: Optional[str] = None
