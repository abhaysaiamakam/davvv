"""
M8 — Image Classification Preprocessing Operations.

Implements image dataset cleaning operations:
- Resize images (width/height or max_dim with aspect ratio preserved)
- Format conversion (JPEG, PNG, WEBP)
- Color mode conversion (RGB, L / grayscale)
- Exact duplicate removal (SHA-256 collision removal)
- Corrupt image exclusion (unreadable / 0-byte / invalid header cleanup)
- Class filtering (filtering target disease/plant classes)
"""
from __future__ import annotations

import hashlib
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from PIL import Image

from app.schemas.preprocessing import (
    OperationPreviewResult,
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingOperationType,
)
from app.services.dataset_discovery_service import DatasetDiscoveryService
from app.services.preprocessing.base_operation import BasePreprocessingOperation

SUPPORTED_IMAGE_EXTS = DatasetDiscoveryService.SUPPORTED_IMAGE_EXTENSIONS


def _find_image_files(dataset_root: Path, target_file: Optional[str] = None) -> List[Path]:
    """Find all decodable image files in dataset directory."""
    if target_file:
        clean = target_file.lstrip("/\\")
        p = (dataset_root / clean).resolve()
        if p.is_file() and dataset_root.resolve() in p.parents and p.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            return [p]
        return []

    found: List[Path] = []
    for root, _, files in os.walk(str(dataset_root)):
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_IMAGE_EXTS:
                found.append(Path(root) / f)
    found.sort()
    return found


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Resize Images
# ---------------------------------------------------------------------------
class ResizeImagesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.RESIZE_IMAGES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Resize Images"

    @property
    def description(self) -> str:
        return "Resizes images to target dimensions (width/height or max_dim preserving aspect ratio)."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "width": {"type": "integer", "minimum": 16, "maximum": 4096},
                "height": {"type": "integer", "minimum": 16, "maximum": 4096},
                "max_dim": {"type": "integer", "minimum": 16, "maximum": 4096},
                "resample": {
                    "type": "string",
                    "enum": ["bilinear", "bicubic", "lanczos", "nearest"],
                    "default": "bilinear",
                },
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        p = config.parameters
        w = p.get("width")
        h = p.get("height")
        max_d = p.get("max_dim")

        if not (max_d or (w and h)):
            errors.append("Must specify either 'max_dim' or both 'width' and 'height'.")
        if w is not None and w <= 0:
            errors.append("'width' must be > 0.")
        if h is not None and h <= 0:
            errors.append("'height' must be > 0.")
        if max_d is not None and max_d <= 0:
            errors.append("'max_dim' must be > 0.")
        return errors

    def _get_resample_filter(self, name: str):
        mapping = {
            "bilinear": Image.Resampling.BILINEAR,
            "bicubic": Image.Resampling.BICUBIC,
            "lanczos": Image.Resampling.LANCZOS,
            "nearest": Image.Resampling.NEAREST,
        }
        return mapping.get(name.lower(), Image.Resampling.BILINEAR)

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        errors = self.validate_parameters(config)
        if errors:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=errors,
            )

        images = _find_image_files(dataset_root, config.target_file)
        if not images:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No images found to resize."],
            )

        p = config.parameters
        w = p.get("width")
        h = p.get("height")
        max_d = p.get("max_dim")

        sample_before: List[Dict[str, Any]] = []
        sample_after: List[Dict[str, Any]] = []

        for img_path in images[:3]:
            try:
                with Image.open(img_path) as im:
                    orig_w, orig_h = im.size
                    sample_before.append({"file": img_path.name, "width": orig_w, "height": orig_h})
                    if max_d:
                        scale = max_d / max(orig_w, orig_h)
                        target_w, target_h = int(round(orig_w * scale)), int(round(orig_h * scale))
                    else:
                        target_w, target_h = int(w), int(h)
                    sample_after.append({"file": img_path.name, "width": target_w, "height": target_h})
            except Exception:
                pass

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=[],
            affected_files=[img.name for img in images[:10]],
            rows_before=0,
            rows_after=0,
            files_before=len(images),
            files_after=len(images),
            sample_before=sample_before,
            sample_after=sample_after,
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        errors = self.validate_parameters(config)
        if errors:
            raise ValueError("; ".join(errors))

        images = _find_image_files(dataset_root, config.target_file)
        p = config.parameters
        w = p.get("width")
        h = p.get("height")
        max_d = p.get("max_dim")
        filter_mode = self._get_resample_filter(p.get("resample", "bilinear"))

        processed = 0
        for img_path in images:
            try:
                with Image.open(img_path) as im:
                    orig_w, orig_h = im.size
                    if max_d:
                        scale = max_d / max(orig_w, orig_h)
                        tw, th = max(1, int(round(orig_w * scale))), max(1, int(round(orig_h * scale)))
                    else:
                        tw, th = int(w), int(h)

                    resized = im.resize((tw, th), filter_mode)
                    resized.save(img_path)
                    processed += 1
            except Exception as exc:
                continue

        return {
            "affected_rows": 0,
            "affected_columns": [],
            "affected_files": [img.name for img in images[:10]],
            "files_before": len(images),
            "files_after": len(images),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 2. Convert Format
# ---------------------------------------------------------------------------
class ConvertFormatOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.CONVERT_FORMAT

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Convert Image Format"

    @property
    def description(self) -> str:
        return "Converts image files to a uniform target format (JPEG, PNG, WEBP)."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_format": {"type": "string", "enum": ["jpeg", "jpg", "png", "webp"]},
            },
            "required": ["target_format"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        fmt = config.parameters.get("target_format", "").lower()
        if fmt not in ("jpeg", "jpg", "png", "webp"):
            return [f"Invalid target_format '{fmt}'. Must be jpeg, jpg, png, or webp."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        errors = self.validate_parameters(config)
        if errors:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=errors,
            )

        images = _find_image_files(dataset_root, config.target_file)
        target_fmt = config.parameters["target_format"].lower()
        target_ext = ".jpg" if target_fmt in ("jpeg", "jpg") else f".{target_fmt}"

        to_convert = [im for im in images if im.suffix.lower() != target_ext]

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=[],
            affected_files=[im.name for im in to_convert[:10]],
            files_before=len(images),
            files_after=len(images),
            after_metrics={"format_target": target_fmt, "files_requiring_conversion": len(to_convert)},
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        images = _find_image_files(dataset_root, config.target_file)
        target_fmt = config.parameters["target_format"].lower()
        target_ext = ".jpg" if target_fmt in ("jpeg", "jpg") else f".{target_fmt}"
        pil_fmt = "JPEG" if target_fmt in ("jpeg", "jpg") else target_fmt.upper()

        converted_count = 0
        for img_path in images:
            if img_path.suffix.lower() == target_ext:
                continue
            try:
                with Image.open(img_path) as im:
                    new_path = img_path.with_suffix(target_ext)
                    if pil_fmt == "JPEG" and im.mode in ("RGBA", "P"):
                        rgb_im = im.convert("RGB")
                        rgb_im.save(new_path, format=pil_fmt)
                    else:
                        im.save(new_path, format=pil_fmt)
                    img_path.unlink()
                    converted_count += 1
            except Exception:
                continue

        return {
            "affected_rows": 0,
            "affected_columns": [],
            "affected_files": [img.name for img in images[:10]],
            "files_before": len(images),
            "files_after": len(images),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 3. Convert Color Mode
# ---------------------------------------------------------------------------
class ConvertColorModeOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.CONVERT_COLOR_MODE

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Convert Color Mode"

    @property
    def description(self) -> str:
        return "Standardizes image color spaces (e.g. RGB or L/grayscale)."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_mode": {"type": "string", "enum": ["RGB", "L", "RGBA"], "default": "RGB"},
            },
            "required": ["target_mode"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        mode = config.parameters.get("target_mode")
        if mode not in ("RGB", "L", "RGBA"):
            return [f"Invalid target_mode '{mode}'."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        images = _find_image_files(dataset_root, config.target_file)
        target_mode = config.parameters.get("target_mode", "RGB")

        mode_counts: Dict[str, int] = defaultdict(int)
        for img in images[:50]:
            try:
                with Image.open(img) as im:
                    mode_counts[im.mode] += 1
            except Exception:
                pass

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=[],
            affected_files=[im.name for im in images[:10]],
            files_before=len(images),
            files_after=len(images),
            before_metrics={"detected_modes": dict(mode_counts)},
            after_metrics={"target_mode": target_mode},
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        images = _find_image_files(dataset_root, config.target_file)
        target_mode = config.parameters.get("target_mode", "RGB")

        for img_path in images:
            try:
                with Image.open(img_path) as im:
                    if im.mode != target_mode:
                        converted = im.convert(target_mode)
                        converted.save(img_path)
            except Exception:
                continue

        return {
            "affected_rows": 0,
            "affected_columns": [],
            "affected_files": [im.name for im in images[:10]],
            "files_before": len(images),
            "files_after": len(images),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 4. Remove Exact Duplicates
# ---------------------------------------------------------------------------
class RemoveExactDuplicatesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.REMOVE_EXACT_DUPLICATES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Remove Exact Duplicate Images"

    @property
    def description(self) -> str:
        return "Identifies byte-for-byte duplicate images via SHA-256 and removes redundant copies."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keep": {"type": "string", "enum": ["first", "last"], "default": "first"},
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        images = _find_image_files(dataset_root, config.target_file)
        hash_map: Dict[str, List[Path]] = defaultdict(list)

        for img in images:
            try:
                h = _sha256_file(img)
                hash_map[h].append(img)
            except Exception:
                pass

        dup_groups = [paths for paths in hash_map.values() if len(paths) > 1]
        dup_count = sum(len(paths) - 1 for paths in dup_groups)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=[],
            affected_files=[p.name for group in dup_groups for p in group[1:5]],
            files_before=len(images),
            files_after=len(images) - dup_count,
            before_metrics={"exact_duplicate_groups": len(dup_groups), "redundant_files": dup_count},
            after_metrics={"duplicate_files_remaining": 0},
            warnings=[f"Detected {dup_count} duplicate image files."] if dup_count > 0 else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        images = _find_image_files(dataset_root, config.target_file)
        hash_map: Dict[str, List[Path]] = defaultdict(list)

        for img in images:
            try:
                h = _sha256_file(img)
                hash_map[h].append(img)
            except Exception:
                pass

        removed_files: List[str] = []
        keep = config.parameters.get("keep", "first")

        for h, paths in hash_map.items():
            if len(paths) > 1:
                to_delete = paths[1:] if keep == "first" else paths[:-1]
                for p in to_delete:
                    try:
                        p.unlink()
                        removed_files.append(p.name)
                    except Exception:
                        pass

        return {
            "affected_rows": 0,
            "affected_columns": [],
            "affected_files": removed_files[:20],
            "files_before": len(images),
            "files_after": len(images) - len(removed_files),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 5. Exclude Corrupt Images
# ---------------------------------------------------------------------------
class ExcludeCorruptImagesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.EXCLUDE_CORRUPT_IMAGES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Exclude Corrupt Images"

    @property
    def description(self) -> str:
        return "Scans image headers and decodability; deletes corrupt, truncated, or 0-byte images."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        return []

    def _is_corrupt(self, p: Path) -> bool:
        if not p.is_file() or p.stat().st_size == 0:
            return True
        try:
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im:
                im.load()
                if im.width <= 0 or im.height <= 0:
                    return True
            return False
        except Exception:
            return True

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        images = _find_image_files(dataset_root, config.target_file)
        corrupt: List[Path] = [p for p in images if self._is_corrupt(p)]

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=[],
            affected_files=[p.name for p in corrupt],
            files_before=len(images),
            files_after=len(images) - len(corrupt),
            before_metrics={"corrupt_files_count": len(corrupt)},
            after_metrics={"corrupt_files_remaining": 0},
            warnings=[f"Identified {len(corrupt)} unreadable or corrupt images."] if corrupt else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        images = _find_image_files(dataset_root, config.target_file)
        removed: List[str] = []

        for p in images:
            if self._is_corrupt(p):
                try:
                    p.unlink()
                    removed.append(p.name)
                except Exception:
                    pass

        return {
            "affected_rows": 0,
            "affected_columns": [],
            "affected_files": removed,
            "files_before": len(images),
            "files_after": len(images) - len(removed),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 6. Filter Classes
# ---------------------------------------------------------------------------
class FilterClassesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.FILTER_CLASSES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.IMAGE

    @property
    def display_name(self) -> str:
        return "Filter Classes"

    @property
    def description(self) -> str:
        return "Filters specific disease or plant classes (keep_classes or drop_classes)."

    @property
    def supported_file_types(self) -> List[str]:
        return list(SUPPORTED_IMAGE_EXTS)

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keep_classes": {"type": "array", "items": {"type": "string"}},
                "drop_classes": {"type": "array", "items": {"type": "string"}},
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        p = config.parameters
        if not p.get("keep_classes") and not p.get("drop_classes"):
            return ["Must specify either 'keep_classes' or 'drop_classes'."]
        return []

    def _discover_classes(self, dataset_root: Path) -> Dict[str, List[Path]]:
        classes: Dict[str, List[Path]] = defaultdict(list)
        for p in _find_image_files(dataset_root):
            rel = p.relative_to(dataset_root)
            cls_name = rel.parent.name if rel.parent != Path(".") else "root"
            classes[cls_name].append(p)
        return classes

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        errors = self.validate_parameters(config)
        if errors:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=errors,
            )

        classes = self._discover_classes(dataset_root)
        keep_cls = set(config.parameters.get("keep_classes", []))
        drop_cls = set(config.parameters.get("drop_classes", []))

        kept_classes = {}
        dropped_classes = {}

        for c_name, files in classes.items():
            if keep_cls and c_name not in keep_cls:
                dropped_classes[c_name] = len(files)
            elif drop_cls and c_name in drop_cls:
                dropped_classes[c_name] = len(files)
            else:
                kept_classes[c_name] = len(files)

        total_before = sum(len(f) for f in classes.values())
        total_after = sum(kept_classes.values())

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=[],
            affected_files=list(dropped_classes.keys()),
            files_before=total_before,
            files_after=total_after,
            before_metrics={"classes": {k: len(v) for k, v in classes.items()}},
            after_metrics={"kept_classes": kept_classes, "dropped_classes": dropped_classes},
            warnings=[f"Operation drops classes: {', '.join(dropped_classes.keys())}"] if dropped_classes else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        classes = self._discover_classes(dataset_root)
        keep_cls = set(config.parameters.get("keep_classes", []))
        drop_cls = set(config.parameters.get("drop_classes", []))

        removed_count = 0
        for c_name, files in classes.items():
            should_drop = (keep_cls and c_name not in keep_cls) or (drop_cls and c_name in drop_cls)
            if should_drop:
                for f in files:
                    try:
                        f.unlink()
                        removed_count += 1
                    except Exception:
                        pass
                # Also remove the class directory if now empty
                parent_dir = files[0].parent
                if parent_dir.is_dir() and not any(parent_dir.iterdir()):
                    shutil.rmtree(parent_dir, ignore_errors=True)

        return {
            "affected_rows": 0,
            "affected_columns": [],
            "affected_files": list(drop_cls or (set(classes.keys()) - keep_cls)),
            "files_before": sum(len(f) for f in classes.values()),
            "files_after": sum(len(f) for f in classes.values()) - removed_count,
            "warnings": [],
        }
