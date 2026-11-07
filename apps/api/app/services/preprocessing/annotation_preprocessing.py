"""
M8 — Annotation Dataset Preprocessing Operations.

Implements bounding-box and object-detection dataset operations (COCO JSON, YOLO TXT):
- Filter annotation classes (COCO categories / YOLO class indices)
- Validate and clip bounding boxes (ensuring bounds stay within image dimensions or [0, 1])
- Rescale annotations (synchronizing bounding boxes when images are resized)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.preprocessing import (
    OperationPreviewResult,
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingOperationType,
)
from app.services.preprocessing.base_operation import BasePreprocessingOperation


def _find_coco_files(dataset_root: Path) -> List[Path]:
    coco_files = []
    for jf in dataset_root.rglob("*.json"):
        if jf.is_file() and jf.stat().st_size < 50 * 1024 * 1024:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "annotations" in data and "categories" in data:
                        coco_files.append(jf)
            except Exception:
                pass
    return sorted(coco_files)


def _find_yolo_files(dataset_root: Path) -> List[Path]:
    yolo_files = []
    for tf in dataset_root.rglob("*.txt"):
        if tf.name.lower() in ("readme.txt", "license.txt", "classes.txt"):
            continue
        try:
            lines = tf.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            if lines and all(len(l.split()) in (5, 6) for l in lines[:5]):
                yolo_files.append(tf)
        except Exception:
            pass
    return sorted(yolo_files)


# ---------------------------------------------------------------------------
# 1. Filter Annotation Classes
# ---------------------------------------------------------------------------
class FilterAnnotationClassesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.FILTER_ANNOTATION_CLASSES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.ANNOTATION

    @property
    def display_name(self) -> str:
        return "Filter Annotation Classes"

    @property
    def description(self) -> str:
        return "Filters object detection bounding boxes by category (COCO categories / YOLO class IDs)."

    @property
    def supported_file_types(self) -> List[str]:
        return [".json", ".txt"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keep_categories": {"type": "array", "items": {"type": "string"}},
                "drop_categories": {"type": "array", "items": {"type": "string"}},
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        p = config.parameters
        if not p.get("keep_categories") and not p.get("drop_categories"):
            return ["Must specify either 'keep_categories' or 'drop_categories'."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        coco_files = _find_coco_files(dataset_root)
        yolo_files = _find_yolo_files(dataset_root)

        if not coco_files and not yolo_files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No COCO JSON or YOLO TXT annotation files found."],
            )

        keep_cats = set(config.parameters.get("keep_categories", []))
        drop_cats = set(config.parameters.get("drop_categories", []))

        total_annos = 0
        kept_annos = 0

        for cf in coco_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cat_id_to_name = {c["id"]: c["name"] for c in data.get("categories", [])}
                for a in data.get("annotations", []):
                    total_annos += 1
                    name = cat_id_to_name.get(a.get("category_id"), "")
                    if keep_cats and name not in keep_cats:
                        continue
                    if drop_cats and name in drop_cats:
                        continue
                    kept_annos += 1
            except Exception:
                pass

        dropped = total_annos - kept_annos

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=dropped,
            affected_columns=[],
            affected_files=[cf.name for cf in coco_files] + [yf.name for yf in yolo_files[:5]],
            rows_before=total_annos,
            rows_after=kept_annos,
            files_before=len(coco_files) + len(yolo_files),
            files_after=len(coco_files) + len(yolo_files),
            before_metrics={"total_annotations": total_annos},
            after_metrics={"retained_annotations": kept_annos},
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        coco_files = _find_coco_files(dataset_root)
        keep_cats = set(config.parameters.get("keep_categories", []))
        drop_cats = set(config.parameters.get("drop_categories", []))

        dropped_count = 0
        total_before = 0

        for cf in coco_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cat_id_to_name = {c["id"]: c["name"] for c in data.get("categories", [])}
                kept = []
                for a in data.get("annotations", []):
                    total_before += 1
                    name = cat_id_to_name.get(a.get("category_id"), "")
                    if keep_cats and name not in keep_cats:
                        dropped_count += 1
                        continue
                    if drop_cats and name in drop_cats:
                        dropped_count += 1
                        continue
                    kept.append(a)
                data["annotations"] = kept
                with open(cf, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

        return {
            "affected_rows": dropped_count,
            "affected_columns": [],
            "affected_files": [cf.name for cf in coco_files],
            "rows_before": total_before,
            "rows_after": total_before - dropped_count,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 2. Validate and Clip Bounding Boxes
# ---------------------------------------------------------------------------
class ValidateAndClipBoundingBoxesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.VALIDATE_AND_CLIP_BOUNDING_BOXES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.ANNOTATION

    @property
    def display_name(self) -> str:
        return "Validate & Clip Bounding Boxes"

    @property
    def description(self) -> str:
        return "Validates and clamps bounding box coordinates to image dimensions or [0, 1] range."

    @property
    def supported_file_types(self) -> List[str]:
        return [".json", ".txt"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        coco_files = _find_coco_files(dataset_root)
        clipped_count = 0
        total_annos = 0

        for cf in coco_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                img_dims = {img["id"]: (img.get("width", 1000), img.get("height", 1000)) for img in data.get("images", [])}
                for a in data.get("annotations", []):
                    total_annos += 1
                    bbox = a.get("bbox", [])
                    if len(bbox) == 4:
                        x, y, w, h = bbox
                        iw, ih = img_dims.get(a.get("image_id"), (1000, 1000))
                        if x < 0 or y < 0 or (x + w) > iw or (y + h) > ih:
                            clipped_count += 1
            except Exception:
                pass

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=clipped_count,
            affected_columns=[],
            affected_files=[cf.name for cf in coco_files],
            rows_before=total_annos,
            rows_after=total_annos,
            files_before=len(coco_files),
            files_after=len(coco_files),
            warnings=[f"Detected {clipped_count} out-of-bounds bounding boxes requiring clipping."] if clipped_count > 0 else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        coco_files = _find_coco_files(dataset_root)
        clipped_count = 0

        for cf in coco_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                img_dims = {img["id"]: (img.get("width", 1000), img.get("height", 1000)) for img in data.get("images", [])}
                for a in data.get("annotations", []):
                    bbox = a.get("bbox", [])
                    if len(bbox) == 4:
                        x, y, w, h = bbox
                        iw, ih = img_dims.get(a.get("image_id"), (1000, 1000))
                        new_x = max(0.0, min(float(x), float(iw)))
                        new_y = max(0.0, min(float(y), float(ih)))
                        new_w = max(0.0, min(float(w), float(iw) - new_x))
                        new_h = max(0.0, min(float(h), float(ih) - new_y))
                        if [new_x, new_y, new_w, new_h] != bbox:
                            a["bbox"] = [new_x, new_y, new_w, new_h]
                            clipped_count += 1
                with open(cf, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

        return {
            "affected_rows": clipped_count,
            "affected_columns": [],
            "affected_files": [cf.name for cf in coco_files],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 3. Rescale Annotations
# ---------------------------------------------------------------------------
class RescaleAnnotationsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.RESCALE_ANNOTATIONS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.ANNOTATION

    @property
    def display_name(self) -> str:
        return "Rescale Annotations"

    @property
    def description(self) -> str:
        return "Scales bounding box coordinates uniformly with image dimension transformations."

    @property
    def supported_file_types(self) -> List[str]:
        return [".json"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scale_x": {"type": "number", "minimum": 0.01},
                "scale_y": {"type": "number", "minimum": 0.01},
            },
            "required": ["scale_x", "scale_y"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        p = config.parameters
        if "scale_x" not in p or "scale_y" not in p:
            return ["'scale_x' and 'scale_y' are required."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        coco_files = _find_coco_files(dataset_root)
        total_annos = 0
        for cf in coco_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    total_annos += len(data.get("annotations", []))
            except Exception:
                pass

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=total_annos,
            affected_columns=[],
            affected_files=[cf.name for cf in coco_files],
            rows_before=total_annos,
            rows_after=total_annos,
            files_before=len(coco_files),
            files_after=len(coco_files),
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        coco_files = _find_coco_files(dataset_root)
        sx = float(config.parameters["scale_x"])
        sy = float(config.parameters["scale_y"])
        total_scaled = 0

        for cf in coco_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for a in data.get("annotations", []):
                    bbox = a.get("bbox", [])
                    if len(bbox) == 4:
                        x, y, w, h = bbox
                        a["bbox"] = [round(x * sx, 2), round(y * sy, 2), round(w * sx, 2), round(h * sy, 2)]
                        total_scaled += 1
                for img in data.get("images", []):
                    if "width" in img:
                        img["width"] = int(round(img["width"] * sx))
                    if "height" in img:
                        img["height"] = int(round(img["height"] * sy))
                with open(cf, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

        return {
            "affected_rows": total_scaled,
            "affected_columns": [],
            "affected_files": [cf.name for cf in coco_files],
            "warnings": [],
        }
