from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from app.core.errors import DatasetNotFoundError, VersionNotFoundError
from app.schemas.image_explorer import (
    DatasetImage,
    DatasetImageListResponse,
    ImageClassCount,
    ImageAnnotation,
    ImageAnnotationResponse,
    AnnotationClassCount,
    ImagePreprocessingPreviewResponse,
)
from app.schemas.preprocessing import PreprocessingModality, PreprocessingOperationType
from app.services.dataset_service import dataset_service
from app.services.image_thumbnail_service import image_thumbnail_service
from app.services.preprocessing.preprocessing_registry import preprocessing_registry
from app.storage.local import storage_backend


class ImageExplorerService:
    """Version-bound image lookup without accepting client filesystem paths."""

    SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
    STRUCTURAL_DIRS = {"images", "image", "imgs", "data", "dataset", "train", "training", "val", "valid", "validation", "test", "testing"}
    PREVIEW_OPERATIONS = {
        PreprocessingOperationType.RESIZE_IMAGES,
        PreprocessingOperationType.CONVERT_FORMAT,
        PreprocessingOperationType.CONVERT_COLOR_MODE,
    }

    def _version_root(self, dataset_id: str, version_id: str) -> Path:
        if not dataset_service.get_dataset(dataset_id):
            raise DatasetNotFoundError(dataset_id)
        version = dataset_service.get_version(dataset_id, version_id)
        if not version:
            raise VersionNotFoundError(dataset_id, version_id)
        root = (storage_backend.base_dir / version.storage_relative_path).resolve()
        if not storage_backend.is_safe_path(root) or not root.is_dir():
            raise VersionNotFoundError(dataset_id, version_id)
        return root

    @staticmethod
    def _id(relative_path: str) -> str:
        return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    @lru_cache(maxsize=8)
    def _records_cached(root_value: str):
        root = Path(root_value)
        root_resolved = root.resolve()
        records = []
        for current, dirs, names in os.walk(root, followlinks=False):
            base = Path(current)
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (base / d).is_symlink())
            for name in names:
                path = base / name
                if path.suffix.lower() not in ImageExplorerService.SUPPORTED or path.is_symlink():
                    continue
                resolved = path.resolve()
                if root_resolved not in resolved.parents or not resolved.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                parent = path.parent.relative_to(root).as_posix()
                parts = [] if parent == "." else list(Path(parent).parts)
                class_parts = [part for part in parts if part.casefold() not in ImageExplorerService.STRUCTURAL_DIRS]
                class_name = "/".join(class_parts) if class_parts else "Unclassified"
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                records.append((relative, class_name, size, path))
        return records

    def _records(self, root: Path):
        return self._records_cached(str(root.resolve()))

    def _resolve_image(self, root: Path, image_id: str):
        if len(image_id) != 32 or any(c not in "0123456789abcdef" for c in image_id):
            return None
        return next((record for record in self._records(root) if self._id(record[0]) == image_id), None)

    def list_images(
        self,
        dataset_id: str,
        version_id: str,
        page: int = 1,
        page_size: int = 30,
        class_name: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "filename",
        descending: bool = False,
        annotation_class_id: Optional[str] = None,
    ) -> DatasetImageListResponse:
        root = self._version_root(dataset_id, version_id)
        records = self._records(root)
        counts = Counter(item[1] for item in records)
        classes = [ImageClassCount(class_name=name, image_count=count) for name, count in sorted(counts.items(), key=lambda pair: pair[0].casefold())]
        selected = records
        if class_name:
            selected = [item for item in selected if item[1] == class_name]
        if search:
            query = search.casefold()
            selected = [item for item in selected if query in Path(item[0]).name.casefold()]
        if annotation_class_id is not None:
            _, annotation_index, _ = self._annotation_index(str(root.resolve()))
            selected = [item for item in selected if any(annotation["class_id"] == annotation_class_id for annotation in annotation_index.get(item[0], []))]
        if sort_by == "file_size":
            selected.sort(key=lambda item: (item[2], item[0].casefold()), reverse=descending)
        elif sort_by in {"width", "height"}:
            def dimension(item):
                try:
                    with Image.open(item[3]) as image:
                        return (getattr(image, sort_by), item[0].casefold())
                except Exception:
                    return (-1, item[0].casefold())
            selected.sort(key=dimension, reverse=descending)
        else:
            selected.sort(key=lambda item: item[0].casefold(), reverse=descending)

        total = len(selected)
        start = (page - 1) * page_size
        items = []
        for relative, name, size, path in selected[start:start + page_size]:
            width = height = None
            fmt = mode = None
            status = "valid"
            try:
                with Image.open(path) as image:
                    width, height, fmt, mode = image.width, image.height, image.format, image.mode
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                status = "corrupt"
            except Exception:
                status = "unreadable"
            image_id = self._id(relative)
            base = f"/api/v1/datasets/{dataset_id}/versions/{version_id}/images/{image_id}"
            items.append(DatasetImage(
                image_id=image_id,
                filename=Path(relative).name,
                class_name=name,
                width=width,
                height=height,
                file_size_bytes=size,
                format=fmt,
                color_mode=mode,
                status=status,
                thumbnail_url=f"{base}/thumbnail",
                preview_url=f"{base}/preview",
            ))
        return DatasetImageListResponse(
            dataset_id=dataset_id,
            version_id=version_id,
            modality="image" if records else "non_image",
            class_structure="directory" if any(name != "Unclassified" for name in counts) else "unclassified",
            total=total,
            page=page,
            page_size=page_size,
            classes=classes,
            items=items,
        )

    def image_path(self, dataset_id: str, version_id: str, image_id: str) -> Path:
        root = self._version_root(dataset_id, version_id)
        record = self._resolve_image(root, image_id)
        if not record:
            raise FileNotFoundError("Image not found in the selected dataset version")
        return record[3]

    def get_image(self, dataset_id: str, version_id: str, image_id: str) -> DatasetImage:
        root = self._version_root(dataset_id, version_id)
        record = self._resolve_image(root, image_id)
        if not record:
            raise FileNotFoundError("Image not found in the selected dataset version")
        relative, class_name, size, path = record
        width = height = None
        fmt = mode = None
        status = "valid"
        try:
            with Image.open(path) as image:
                width, height, fmt, mode = image.width, image.height, image.format, image.mode
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            status = "corrupt"
        except Exception:
            status = "unreadable"
        base = f"/api/v1/datasets/{dataset_id}/versions/{version_id}/images/{image_id}"
        return DatasetImage(
            image_id=image_id,
            filename=Path(relative).name,
            class_name=class_name,
            width=width,
            height=height,
            file_size_bytes=size,
            format=fmt,
            color_mode=mode,
            status=status,
            thumbnail_url=f"{base}/thumbnail",
            preview_url=f"{base}/preview",
        )

    @staticmethod
    @lru_cache(maxsize=8)
    def _annotation_index(root_value: str):
        """Parse actual COCO or YOLO annotations once per immutable version root."""
        root = Path(root_value)
        records = ImageExplorerService._records_cached(root_value)
        rel_paths = {record[0] for record in records}
        by_basename: dict[str, list[str]] = {}
        for relative in rel_paths:
            by_basename.setdefault(Path(relative).name.casefold(), []).append(relative)
        def match_image(raw_name: str) -> Optional[str]:
            normalized = raw_name.replace("\\", "/")
            if normalized.startswith("/") or ".." in Path(normalized).parts:
                return None
            if normalized.startswith("./"):
                normalized = normalized[2:]
            candidate = (root / normalized).resolve()
            if root.resolve() in candidate.parents:
                candidate_rel = candidate.relative_to(root.resolve()).as_posix()
                if candidate_rel in rel_paths:
                    return candidate_rel
            matches = by_basename.get(Path(normalized).name.casefold(), [])
            return matches[0] if len(matches) == 1 else None

        # COCO provides source category names, image IDs, and pixel-coordinate boxes.
        for json_path in sorted(root.rglob("*.json")):
            if json_path.is_symlink() or not json_path.is_file() or json_path.stat().st_size > 50 * 1024 * 1024:
                continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or not all(key in data for key in ("images", "annotations", "categories")):
                continue
            categories = {str(row["id"]): str(row["name"]) for row in data["categories"] if isinstance(row, dict) and "id" in row and isinstance(row.get("name"), str)}
            image_ids = {str(row["id"]): match_image(str(row.get("file_name", ""))) for row in data["images"] if isinstance(row, dict) and "id" in row}
            found: dict[str, list[dict]] = {}
            counts: dict[str, list] = {key: [label, 0, set()] for key, label in categories.items()}
            for index, annotation in enumerate(data["annotations"]):
                if not isinstance(annotation, dict):
                    continue
                relative = image_ids.get(str(annotation.get("image_id")))
                bbox = annotation.get("bbox")
                if not relative or not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                try:
                    x, y, width, height = [float(value) for value in bbox]
                except (TypeError, ValueError):
                    continue
                if not all(math.isfinite(value) for value in (x, y, width, height)):
                    continue
                class_id = str(annotation.get("category_id", ""))
                label = categories.get(class_id)
                item = {"annotation_id": str(annotation.get("id", f"{json_path.name}:{index}")), "class_id": class_id, "label": label, "x": x, "y": y, "width": width, "height": height}
                if isinstance(annotation.get("score"), (int, float)) and math.isfinite(float(annotation["score"])):
                    item["confidence"] = float(annotation["score"])
                found.setdefault(relative, []).append(item)
                current = counts.setdefault(class_id, [label, 0, set()])
                current[1] += 1
                current[2].add(relative)
            classes = [{"class_id": key, "label": value[0], "annotation_count": value[1], "image_count": len(value[2])} for key, value in sorted(counts.items())]
            return "coco", found, classes

        # YOLO text rows are normalized center-x/center-y/width/height coordinates.
        from app.services.preprocessing.annotation_preprocessing import _find_yolo_files
        yolo_files = _find_yolo_files(root)
        if not yolo_files:
            return "none", {}, []
        names: dict[str, str] = {}
        try:
            import yaml
            for yaml_path in sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")]):
                if yaml_path.is_symlink() or not yaml_path.is_file() or yaml_path.stat().st_size > 2 * 1024 * 1024:
                    continue
                try:
                    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                except (yaml.YAMLError, UnicodeError, OSError):
                    continue
                raw_names = config.get("names") if isinstance(config, dict) else None
                if isinstance(raw_names, list):
                    names.update({str(index): str(label) for index, label in enumerate(raw_names) if isinstance(label, str)})
                elif isinstance(raw_names, dict):
                    names.update({str(key): str(label) for key, label in raw_names.items() if isinstance(label, str)})
        except ImportError:
            pass
        for names_path in sorted(root.rglob("classes.txt")):
            if names_path.is_file() and not names_path.is_symlink():
                try:
                    names.update({str(index): line.strip() for index, line in enumerate(names_path.read_text(encoding="utf-8").splitlines()) if line.strip()})
                except (OSError, UnicodeError):
                    pass

        found = {}
        counts: dict[str, list] = {}
        for label_path in yolo_files:
            relative_label = label_path.relative_to(root).as_posix()
            parts = list(Path(relative_label).parts)
            if "labels" in [part.casefold() for part in parts]:
                index = next(i for i, part in enumerate(parts) if part.casefold() == "labels")
                parts[index] = "images"
            image_base = str(Path(*parts).with_suffix(""))
            candidates = [path for path in rel_paths if str(Path(path).with_suffix("")) == image_base]
            if not candidates:
                candidates = by_basename.get(f"{label_path.stem}.jpg".casefold(), []) or by_basename.get(f"{label_path.stem}.png".casefold(), [])
            relative_image = candidates[0] if len(candidates) == 1 else None
            if not relative_image:
                continue
            try:
                lines = label_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for row_index, line in enumerate(lines):
                columns = line.split()
                if len(columns) not in (5, 6):
                    continue
                try:
                    class_number = str(int(columns[0]))
                    center_x, center_y, norm_width, norm_height = [float(value) for value in columns[1:5]]
                except (TypeError, ValueError):
                    continue
                if not all(math.isfinite(value) for value in (center_x, center_y, norm_width, norm_height)):
                    continue
                try:
                    with Image.open(root / relative_image) as source_image:
                        image_width, image_height = source_image.size
                except Exception:
                    continue
                x = (center_x - norm_width / 2) * image_width
                y = (center_y - norm_height / 2) * image_height
                width, height = norm_width * image_width, norm_height * image_height
                item = {"annotation_id": f"{label_path.name}:{row_index}", "class_id": class_number, "label": names.get(class_number), "x": x, "y": y, "width": width, "height": height}
                if len(columns) == 6:
                    try:
                        confidence = float(columns[5])
                        if math.isfinite(confidence):
                            item["confidence"] = confidence
                    except ValueError:
                        pass
                found.setdefault(relative_image, []).append(item)
                current = counts.setdefault(class_number, [names.get(class_number), 0, set()])
                current[1] += 1
                current[2].add(relative_image)
        classes = [{"class_id": key, "label": value[0], "annotation_count": value[1], "image_count": len(value[2])} for key, value in sorted(counts.items(), key=lambda pair: int(pair[0]) if pair[0].isdigit() else pair[0])]
        return "yolo", found, classes

    def get_annotations(self, dataset_id: str, version_id: str, image_id: str) -> ImageAnnotationResponse:
        root = self._version_root(dataset_id, version_id)
        record = self._resolve_image(root, image_id)
        if not record:
            raise FileNotFoundError("Image not found in the selected dataset version")
        annotation_format, by_image, class_counts = self._annotation_index(str(root.resolve()))
        relative, _, _, path = record
        try:
            with Image.open(path) as image:
                image_width, image_height = image.size
        except Exception:
            image_width = image_height = None
        annotations = [ImageAnnotation(**item) for item in by_image.get(relative, [])]
        return ImageAnnotationResponse(
            dataset_id=dataset_id,
            version_id=version_id,
            image_id=image_id,
            annotation_format=annotation_format,
            image_width=image_width,
            image_height=image_height,
            annotation_count=len(annotations),
            annotations=annotations,
            classes=[AnnotationClassCount(**item) for item in class_counts],
        )

    @staticmethod
    def _metadata(path: Path) -> dict:
        metadata = image_thumbnail_service.inspect_image_metadata_safe(path)
        if not metadata:
            raise ValueError("Image cannot be decoded")
        return metadata

    @staticmethod
    def _thumbnail_data_url(path: Path, max_dim: int = 640) -> str:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=85, optimize=True)
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{data}"

    def preview_preprocessing(self, dataset_id: str, version_id: str, image_id: str, config):
        source = self.image_path(dataset_id, version_id, image_id)
        if config.operation_type not in self.PREVIEW_OPERATIONS:
            raise ValueError("Image preview currently supports resize, format conversion, and color conversion")
        handler = preprocessing_registry.get_operation(config.operation_type)
        config.modality = PreprocessingModality.IMAGE
        annotation_format, _, _ = self._annotation_index(str(self._version_root(dataset_id, version_id).resolve()))
        if annotation_format != "none" and config.operation_type in {
            PreprocessingOperationType.RESIZE_IMAGES,
            PreprocessingOperationType.CONVERT_FORMAT,
        }:
            raise ValueError("Resize and format conversion are blocked for annotation-linked datasets until linked labels can be updated safely")
        errors = handler.validate_parameters(config)
        if errors:
            raise ValueError("; ".join(errors))

        # Execute the same operation implementation used by derived-version processing
        # inside an isolated temporary directory; the uploaded version stays untouched.
        with tempfile.TemporaryDirectory(prefix="croplens-image-preview-") as tmp:
            root = Path(tmp)
            relative = source.relative_to(self._version_root(dataset_id, version_id))
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            config.target_file = relative.as_posix()
            handler.apply(root, config)
            results = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in self.SUPPORTED)
            if not results:
                raise ValueError("The preprocessing operation did not produce an image preview")
            output = results[0]
            return ImagePreprocessingPreviewResponse(
                dataset_id=dataset_id,
                version_id=version_id,
                image_id=image_id,
                operation_type=config.operation_type.value,
                original_data_url=self._thumbnail_data_url(source),
                preview_data_url=self._thumbnail_data_url(output),
                original_metadata=self._metadata(source),
                preview_metadata=self._metadata(output),
            )


image_explorer_service = ImageExplorerService()
