import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from PIL import Image, ImageFile, UnidentifiedImageError

from app.core.errors import DatasetDirectoryNotFoundError
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetStatus,
    DatasetValidationResult,
    DimensionSummary,
    ImageValidationRecord,
    ValidationStatus,
)
from app.services.dataset_discovery_service import dataset_discovery_service
from app.storage.base import StorageBackend

# Enforce strict decoding: do not globally allow truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = False


class ImageValidationService:
    """
    Service responsible for verifying the byte-level integrity, readability,
    and metadata properties of image assets across agricultural datasets.
    """

    def __init__(self):
        self.supported_extensions: Set[str] = (
            dataset_discovery_service.SUPPORTED_IMAGE_EXTENSIONS
        )

    def _is_symlink_safe(self, child_path: Path, dataset_root_resolved: Path) -> bool:
        """Verify that a symlink does not escape the configured dataset root."""
        try:
            target_resolved = child_path.resolve()
            return (
                target_resolved == dataset_root_resolved
                or dataset_root_resolved in target_resolved.parents
            )
        except Exception:
            return False

    def validate_image_file(
        self, file_path: Path, dataset_root: Path
    ) -> ImageValidationRecord:
        """
        Perform rigorous byte-level integrity validation and metadata extraction
        for a single candidate image file. Original files are strictly preserved.
        """
        dataset_root_resolved = dataset_root.resolve()

        try:
            rel_path_str = str(file_path.relative_to(dataset_root)).replace("\\", "/")
        except ValueError:
            rel_path_str = file_path.name

        # Symlink boundary check
        if file_path.is_symlink() and not self._is_symlink_safe(
            file_path, dataset_root_resolved
        ):
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=0,
                status=ValidationStatus.UNREADABLE,
                error_message="Symlink target escapes dataset root boundary",
            )

        # File existence check
        try:
            if not file_path.exists():
                return ImageValidationRecord(
                    relative_path=rel_path_str,
                    file_size_bytes=0,
                    status=ValidationStatus.UNREADABLE,
                    error_message="File does not exist or was removed after discovery",
                )
        except PermissionError as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=0,
                status=ValidationStatus.UNREADABLE,
                error_message=f"Permission denied accessing file: {exc}",
            )
        except OSError as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=0,
                status=ValidationStatus.ERROR,
                error_message=f"Filesystem access error: {exc}",
            )

        # File size & zero-byte check
        try:
            file_size = os.path.getsize(file_path)
        except OSError as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=0,
                status=ValidationStatus.UNREADABLE,
                error_message=f"Cannot determine file size: {exc}",
            )

        if file_size == 0:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=0,
                status=ValidationStatus.CORRUPT,
                error_message="Zero-byte file (empty image payload)",
            )

        # Extension check
        ext = os.path.splitext(file_path.name)[1].lower()
        if ext not in self.supported_extensions:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                status=ValidationStatus.UNSUPPORTED,
                error_message=f"Unsupported file extension '{ext}'",
            )

        fmt: Optional[str] = None
        mode: Optional[str] = None
        width: Optional[int] = None
        height: Optional[int] = None

        # Stage 1: Header verification with Image.verify()
        try:
            with Image.open(file_path) as img:
                fmt = img.format
                mode = img.mode
                width, height = img.size
                img.verify()
        except UnidentifiedImageError as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                status=ValidationStatus.CORRUPT,
                error_message=f"Unidentified image format or malformed header: {exc}",
            )
        except (OSError, SyntaxError) as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                status=ValidationStatus.CORRUPT,
                error_message=f"Malformed image header: {exc}",
            )
        except PermissionError as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                status=ValidationStatus.UNREADABLE,
                error_message=f"Permission denied reading image: {exc}",
            )
        except Exception as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                status=ValidationStatus.ERROR,
                error_message=f"Unexpected error during header verification: {exc}",
            )

        # Stage 2: Full pixel stream decode via load() to detect truncated byte streams
        try:
            with Image.open(file_path) as img:
                img.load()
                fmt = img.format or fmt
                mode = img.mode or mode
                width, height = img.size

                # Determine channel count safely
                channels: Optional[int] = None
                if hasattr(img, "getbands"):
                    bands = img.getbands()
                    channels = len(bands) if bands else None

                if not channels and mode:
                    mode_channel_map = {
                        "1": 1,
                        "L": 1,
                        "P": 1,
                        "RGB": 3,
                        "RGBA": 4,
                        "CMYK": 4,
                        "YCbCr": 3,
                        "LAB": 3,
                        "HSV": 3,
                        "I": 1,
                        "F": 1,
                    }
                    channels = mode_channel_map.get(mode, 3)

                # Validate dimensions sanity
                if width <= 0 or height <= 0:
                    return ImageValidationRecord(
                        relative_path=rel_path_str,
                        file_size_bytes=file_size,
                        format=fmt,
                        width=width,
                        height=height,
                        status=ValidationStatus.CORRUPT,
                        error_message="Image contains invalid non-positive dimensions",
                    )

                aspect_ratio = round(float(width) / float(height), 4)

                return ImageValidationRecord(
                    relative_path=rel_path_str,
                    file_size_bytes=file_size,
                    format=fmt,
                    width=width,
                    height=height,
                    aspect_ratio=aspect_ratio,
                    color_mode=mode,
                    channels=channels,
                    status=ValidationStatus.VALID,
                )
        except (OSError, SyntaxError) as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                format=fmt,
                width=width,
                height=height,
                status=ValidationStatus.CORRUPT,
                error_message=f"Decoding failure (truncated or corrupt pixel data): {exc}",
            )
        except Exception as exc:
            return ImageValidationRecord(
                relative_path=rel_path_str,
                file_size_bytes=file_size,
                status=ValidationStatus.ERROR,
                error_message=f"Unexpected error during pixel decoding: {exc}",
            )

    def validate_dataset(
        self, dataset: DatasetMetadata, storage: StorageBackend
    ) -> DatasetValidationResult:
        """
        Validate all candidate image assets belonging to a discovered dataset.
        Produces deterministic metrics, summary statistics, and corruption records.
        """
        target_path = storage.resolve_dataset_path(dataset)
        sanitized_rel_path = storage.sanitize_relative_path(target_path)

        if not target_path.exists() or not target_path.is_dir():
            raise DatasetDirectoryNotFoundError(dataset.id, sanitized_rel_path)

        now = datetime.now(timezone.utc).isoformat()
        records: List[ImageValidationRecord] = []
        corrupted_files: List[ImageValidationRecord] = []
        warnings: List[str] = []

        total_discovered = 0
        total_valid = 0
        total_corrupt = 0
        total_unreadable = 0
        total_errors = 0
        total_unsupported = 0

        color_mode_counts: Dict[str, int] = {}
        format_counts: Dict[str, int] = {}

        valid_widths: List[int] = []
        valid_heights: List[int] = []
        valid_ratios: List[float] = []

        # Deterministic walk of dataset tree
        for root, dirs, files in os.walk(str(target_path), followlinks=False, topdown=True):
            current_dir = Path(root)

            # Ignore internal non-class directories
            dirs[:] = sorted(
                [
                    d
                    for d in dirs
                    if d.lower() not in dataset_discovery_service.IGNORED_DIRECTORY_NAMES
                    and not d.startswith(".")
                ]
            )

            for filename in sorted(files):
                if filename.lower() in dataset_discovery_service.IGNORED_FILE_NAMES:
                    continue

                ext = os.path.splitext(filename)[1].lower()
                # Check if it was considered a candidate image by discovery
                if ext not in self.supported_extensions:
                    continue

                total_discovered += 1
                file_path = current_dir / filename
                record = self.validate_image_file(file_path, target_path)
                records.append(record)

                if record.status == ValidationStatus.VALID:
                    total_valid += 1
                    if record.color_mode:
                        color_mode_counts[record.color_mode] = (
                            color_mode_counts.get(record.color_mode, 0) + 1
                        )
                    if record.format:
                        format_counts[record.format] = (
                            format_counts.get(record.format, 0) + 1
                        )
                    if record.width is not None and record.height is not None:
                        valid_widths.append(record.width)
                        valid_heights.append(record.height)
                    if record.aspect_ratio is not None:
                        valid_ratios.append(record.aspect_ratio)
                elif record.status == ValidationStatus.CORRUPT:
                    total_corrupt += 1
                    corrupted_files.append(record)
                    warnings.append(
                        f"Corrupted image: {record.relative_path} ({record.error_message})"
                    )
                elif record.status == ValidationStatus.UNREADABLE:
                    total_unreadable += 1
                    corrupted_files.append(record)
                    warnings.append(
                        f"Unreadable file: {record.relative_path} ({record.error_message})"
                    )
                elif record.status == ValidationStatus.UNSUPPORTED:
                    total_unsupported += 1
                else:
                    total_errors += 1
                    corrupted_files.append(record)
                    warnings.append(
                        f"Validation error on {record.relative_path}: {record.error_message}"
                    )

        # Dimension summary for valid images
        dimension_summary: Optional[DimensionSummary] = None
        if valid_widths and valid_heights:
            dimension_summary = DimensionSummary(
                min_width=min(valid_widths),
                max_width=max(valid_widths),
                min_height=min(valid_heights),
                max_height=max(valid_heights),
                mean_width=round(sum(valid_widths) / len(valid_widths), 2),
                mean_height=round(sum(valid_heights) / len(valid_heights), 2),
                min_aspect_ratio=min(valid_ratios) if valid_ratios else None,
                max_aspect_ratio=max(valid_ratios) if valid_ratios else None,
            )

        if total_discovered == 0:
            validation_status = DatasetStatus.INVALID
            warnings.append("No candidate image files were present for validation.")
        elif total_valid > 0:
            validation_status = DatasetStatus.VALIDATED
        else:
            validation_status = DatasetStatus.INVALID

        return DatasetValidationResult(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            dataset_source=dataset.source,
            validation_status=validation_status,
            total_discovered_images=total_discovered,
            total_validated_images=total_valid,
            total_corrupted_images=total_corrupt,
            total_unreadable_images=total_unreadable,
            total_processing_errors=total_errors,
            total_unsupported_files=total_unsupported,
            validation_timestamp=now,
            dimension_summary=dimension_summary,
            color_mode_distribution=color_mode_counts,
            format_distribution=format_counts,
            corrupted_files=corrupted_files,
            images=records,
            warnings=warnings,
        )


# Global singleton instance
image_validation_service = ImageValidationService()

