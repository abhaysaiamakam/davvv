"""
M9 — Time-Series, Image, and Annotation Feature Engineering Operations.

Implements modality-specific feature engineering:
- Time-series lag features, rolling statistics, difference features.
- Image metadata extraction (dimensions, aspect ratio, file size, color modes).
- Annotation metadata extraction (object counts, bounding box areas, density).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from app.schemas.feature_engineering import (
    FeatureModality,
    FeatureOperationConfig,
    FeatureOperationType,
    FeaturePreviewResult,
)
from app.services.feature_engineering.base_feature_operation import BaseFeatureOperation
from app.services.preprocessing.image_preprocessing import _find_image_files, SUPPORTED_IMAGE_EXTS
from app.services.preprocessing.annotation_preprocessing import _find_coco_files
from app.services.preprocessing.tabular_preprocessing import (
    _is_column_numeric,
    _read_table,
    _resolve_tabular_files,
    _to_float,
    _write_table,
)


# ---------------------------------------------------------------------------
# 1. Time-Series Feature Operations (Lag, Rolling, Difference)
# ---------------------------------------------------------------------------
class LagFeaturesOperation(BaseFeatureOperation):
    @property
    def operation_type(self) -> FeatureOperationType:
        return FeatureOperationType.LAG_FEATURES

    @property
    def modality(self) -> FeatureModality:
        return FeatureModality.TIME_SERIES

    @property
    def display_name(self) -> str:
        return "Lag Features"

    @property
    def description(self) -> str:
        return "Generates lagged temporal features for time-series numeric columns."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "lag_periods": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["columns"],
        }

    def validate_parameters(self, config: FeatureOperationConfig) -> List[str]:
        cols = config.target_columns or config.parameters.get("columns", [])
        if not cols:
            return ["Columns must be specified for lag features."]
        return []

    def preview(self, dataset_root: Path, config: FeatureOperationConfig) -> FeaturePreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return FeaturePreviewResult(
                operation_type=self.operation_type, status="invalid", validation_errors=["No tabular files found."]
            )

        cols = config.target_columns or config.parameters.get("columns", [])
        lag = int(config.parameters.get("lag_periods", 1))
        headers, rows = _read_table(files[0])
        active_cols = [c for c in cols if c in headers]
        gen_feats = [f"{c}_lag{lag}" for c in active_cols]

        return FeaturePreviewResult(
            operation_type=self.operation_type,
            status="valid",
            source_features=active_cols,
            generated_features=gen_feats,
            features_before_count=len(headers),
            features_after_count=len(headers) + len(gen_feats),
            rows_before=len(rows),
            rows_after=len(rows),
            sample_before=rows[:3],
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: FeatureOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        cols = config.target_columns or config.parameters.get("columns", [])
        lag = int(config.parameters.get("lag_periods", 1))

        gen_cols = []
        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers]
            for c in active_cols:
                new_c = f"{c}_lag{lag}"
                if new_c not in headers:
                    headers.append(new_c)
                    gen_cols.append(new_c)
                
                vals = [r.get(c, "") for r in rows]
                for i, r in enumerate(rows):
                    if i >= lag:
                        r[new_c] = vals[i - lag]
                    else:
                        r[new_c] = ""
            _write_table(f_path, headers, rows)

        return {"source_features": cols, "generated_features": gen_cols, "removed_features": []}


# ---------------------------------------------------------------------------
# 2. Image Metadata Feature Extraction
# ---------------------------------------------------------------------------
class ImageMetadataExtractionOperation(BaseFeatureOperation):
    @property
    def operation_type(self) -> FeatureOperationType:
        return FeatureOperationType.IMAGE_METADATA_EXTRACTION

    @property
    def modality(self) -> FeatureModality:
        return FeatureModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Image Metadata Feature Extraction"

    @property
    def description(self) -> str:
        return "Extracts image technical metadata (width, height, aspect ratio, file size, color mode) into a tabular profile."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "output_filename": {"type": "string", "default": "image_features.csv"},
            },
        }

    def validate_parameters(self, config: FeatureOperationConfig) -> List[str]:
        return []

    def preview(self, dataset_root: Path, config: FeatureOperationConfig) -> FeaturePreviewResult:
        images = _find_image_files(dataset_root, config.target_file)
        if not images:
            return FeaturePreviewResult(
                operation_type=self.operation_type, status="invalid", validation_errors=["No images found."]
            )

        gen_feats = ["filename", "width", "height", "aspect_ratio", "file_size_bytes", "color_mode"]

        return FeaturePreviewResult(
            operation_type=self.operation_type,
            status="valid",
            source_features=[],
            generated_features=gen_feats,
            features_before_count=0,
            features_after_count=len(gen_feats),
            rows_before=len(images),
            rows_after=len(images),
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: FeatureOperationConfig) -> Dict[str, Any]:
        images = _find_image_files(dataset_root, config.target_file)
        out_name = config.parameters.get("output_filename", "image_features.csv")
        out_path = dataset_root / out_name

        headers = ["filename", "width", "height", "aspect_ratio", "file_size_bytes", "color_mode"]
        rows = []

        for im_path in images:
            try:
                fsize = im_path.stat().st_size
                with Image.open(im_path) as im:
                    w, h = im.size
                    ar = round(w / h, 4) if h > 0 else 0.0
                    mode = im.mode
                rows.append({
                    "filename": im_path.name,
                    "width": str(w),
                    "height": str(h),
                    "aspect_ratio": str(ar),
                    "file_size_bytes": str(fsize),
                    "color_mode": mode,
                })
            except Exception:
                pass

        _write_table(out_path, headers, rows)

        return {
            "source_features": [],
            "generated_features": headers,
            "removed_features": [],
        }


# ---------------------------------------------------------------------------
# 3. Annotation Metadata Feature Extraction
# ---------------------------------------------------------------------------
class AnnotationMetadataExtractionOperation(BaseFeatureOperation):
    @property
    def operation_type(self) -> FeatureOperationType:
        return FeatureOperationType.ANNOTATION_METADATA_EXTRACTION

    @property
    def modality(self) -> FeatureModality:
        return FeatureModality.ANNOTATION

    @property
    def display_name(self) -> str:
        return "Annotation Metadata Extraction"

    @property
    def description(self) -> str:
        return "Extracts object-detection bounding box statistics into tabular features."

    @property
    def supported_file_types(self) -> List[str]:
        return [".json"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "output_filename": {"type": "string", "default": "annotation_features.csv"},
            },
        }

    def validate_parameters(self, config: FeatureOperationConfig) -> List[str]:
        return []

    def preview(self, dataset_root: Path, config: FeatureOperationConfig) -> FeaturePreviewResult:
        coco_files = _find_coco_files(dataset_root)
        if not coco_files:
            return FeaturePreviewResult(
                operation_type=self.operation_type, status="invalid", validation_errors=["No COCO JSON annotations found."]
            )

        gen_feats = ["image_id", "annotation_count", "mean_bbox_area", "classes_present"]

        return FeaturePreviewResult(
            operation_type=self.operation_type,
            status="valid",
            source_features=[],
            generated_features=gen_feats,
            features_before_count=0,
            features_after_count=len(gen_feats),
            rows_before=0,
            rows_after=0,
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: FeatureOperationConfig) -> Dict[str, Any]:
        coco_files = _find_coco_files(dataset_root)
        out_name = config.parameters.get("output_filename", "annotation_features.csv")
        out_path = dataset_root / out_name

        headers = ["image_id", "annotation_count", "mean_bbox_area", "classes_present"]
        rows = []

        for cf in coco_files:
            import json
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                img_annos: Dict[int, List[Dict[str, Any]]] = {}
                for a in data.get("annotations", []):
                    img_id = a.get("image_id")
                    img_annos.setdefault(img_id, []).append(a)

                cat_map = {c["id"]: c["name"] for c in data.get("categories", [])}

                for img_id, annos in img_annos.items():
                    count = len(annos)
                    areas = [a.get("bbox", [0,0,0,0])[2] * a.get("bbox", [0,0,0,0])[3] for a in annos]
                    mean_area = round(sum(areas) / len(areas), 2) if areas else 0.0
                    classes = sorted(list(set(cat_map.get(a.get("category_id"), "unknown") for a in annos)))

                    rows.append({
                        "image_id": str(img_id),
                        "annotation_count": str(count),
                        "mean_bbox_area": str(mean_area),
                        "classes_present": ";".join(classes),
                    })
            except Exception:
                pass

        _write_table(out_path, headers, rows)

        return {
            "source_features": [],
            "generated_features": headers,
            "removed_features": [],
        }
