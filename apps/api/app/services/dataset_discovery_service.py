import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from app.core.errors import DatasetDirectoryNotFoundError
from app.schemas.dataset import (
    ClassDiscoveryInfo,
    DatasetDiscoveryResult,
    DatasetMetadata,
    DatasetStatus,
)
from app.storage.base import StorageBackend


class DatasetDiscoveryService:
    """
    Engine for discovering, cataloging, and validating dataset directory structures,
    identifying supported image formats, and indexing class hierarchies.
    """

    SUPPORTED_IMAGE_EXTENSIONS: Set[str] = {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
    }

    # Common non-class metadata/audit files and directories to ignore without warning
    IGNORED_DIRECTORY_NAMES: Set[str] = {
        ".git",
        ".cache",
        "__pycache__",
        ".pytest_cache",
        ".venv",
    }

    IGNORED_FILE_NAMES: Set[str] = {
        ".ds_store",
        "thumbs.db",
        ".gitattributes",
        ".gitignore",
    }

    def is_supported_image(self, filename: str) -> bool:
        """Check if filename possesses a supported image extension case-insensitively."""
        ext = os.path.splitext(filename)[1].lower()
        return ext in self.SUPPORTED_IMAGE_EXTENSIONS

    def _is_symlink_safe(self, child_path: Path, dataset_root_resolved: Path) -> bool:
        """
        Verify that a symlink does not escape the configured dataset root.
        Returns False if the target resolves outside dataset_root_resolved.
        """
        try:
            target_resolved = child_path.resolve()
            return (
                target_resolved == dataset_root_resolved
                or dataset_root_resolved in target_resolved.parents
            )
        except Exception:
            return False

    def scan_directory(
        self, dataset_root: Path
    ) -> Tuple[
        List[ClassDiscoveryInfo],
        int,
        List[str],
        int,
        List[str],
    ]:
        """
        Deterministically scan directory tree for supported images and nested classes.
        Returns:
            - List of ClassDiscoveryInfo
            - Total discovered image count
            - List of supported extensions encountered
            - Count of unreadable/inaccessible files or directories
            - List of human-readable warnings
        """
        dataset_root_resolved = dataset_root.resolve()

        class_image_counts: Dict[str, int] = defaultdict(int)
        class_rel_paths: Dict[str, str] = {}
        extensions_encountered: Set[str] = set()
        unreadable_count = 0
        warnings: List[str] = []

        # Deterministic traversal using os.walk with sorted subdirectories and filenames
        # followlinks=False to prevent infinite loops and unauthorized traversal
        for root, dirs, files in os.walk(str(dataset_root), followlinks=False, topdown=True):
            current_dir = Path(root)

            # Check if current directory is a symlink pointing outside
            if current_dir.is_symlink() and not self._is_symlink_safe(
                current_dir, dataset_root_resolved
            ):
                unreadable_count += 1
                warnings.append(
                    f"Symlink directory pointing outside dataset root was skipped: {current_dir.name}"
                )
                dirs.clear()  # Do not recurse into escaped directory
                continue

            # Filter out ignored internal directories in-place and sort deterministically
            dirs[:] = sorted(
                [
                    d
                    for d in dirs
                    if d.lower() not in self.IGNORED_DIRECTORY_NAMES
                    and not d.startswith(".")
                ]
            )

            # Handle directory permission issues safely
            try:
                sorted_files = sorted(files)
            except OSError as exc:
                unreadable_count += 1
                warnings.append(f"Inaccessible directory listing: {current_dir.name} ({exc})")
                continue

            # Determine relative path from dataset root
            try:
                rel_path = current_dir.relative_to(dataset_root)
                rel_str = str(rel_path).replace("\\", "/")
            except ValueError:
                rel_str = current_dir.name

            # Scan files in current directory
            for filename in sorted_files:
                if filename.lower() in self.IGNORED_FILE_NAMES:
                    continue

                file_path = current_dir / filename

                # Check if file is a symlink escaping dataset root
                if file_path.is_symlink() and not self._is_symlink_safe(
                    file_path, dataset_root_resolved
                ):
                    unreadable_count += 1
                    warnings.append(
                        f"Symlink file pointing outside dataset root was skipped: {filename}"
                    )
                    continue

                try:
                    # Test file readability without loading entire content into memory
                    if not file_path.exists():
                        unreadable_count += 1
                        warnings.append(f"Broken or inaccessible file link: {filename}")
                        continue
                except OSError as exc:
                    unreadable_count += 1
                    warnings.append(f"Error checking file {filename}: {exc}")
                    continue

                if self.is_supported_image(filename):
                    ext = os.path.splitext(filename)[1].lower()
                    extensions_encountered.add(ext)

                    # Class name convention:
                    # For nested agricultural hierarchies (e.g. Rice/Disease/01_Bacterial_leaf_blight),
                    # use normalized forward-slash relative path as class identifier.
                    class_key = rel_str if rel_str != "." else "_root_"
                    class_image_counts[class_key] += 1
                    class_rel_paths[class_key] = rel_str

        # Assemble deterministically sorted classes list
        classes: List[ClassDiscoveryInfo] = []
        for class_name in sorted(class_image_counts.keys()):
            classes.append(
                ClassDiscoveryInfo(
                    class_name=class_name,
                    relative_path=class_rel_paths[class_name],
                    image_count=class_image_counts[class_name],
                )
            )

        total_images = sum(c.image_count for c in classes)
        sorted_exts = sorted(extensions_encountered)

        return (
            classes,
            total_images,
            sorted_exts,
            unreadable_count,
            warnings,
        )

    def discover_dataset(
        self, dataset: DatasetMetadata, storage: StorageBackend
    ) -> DatasetDiscoveryResult:
        """
        Execute discovery on a configured dataset.
        Validates directory existence, scans image files, and produces structured metadata.
        """
        target_path = storage.resolve_dataset_path(dataset)
        sanitized_rel_path = storage.sanitize_relative_path(target_path)

        if not target_path.exists():
            raise DatasetDirectoryNotFoundError(dataset.id, sanitized_rel_path)

        if not target_path.is_dir():
            now = datetime.now(timezone.utc).isoformat()
            return DatasetDiscoveryResult(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                dataset_source=dataset.source,
                dataset_root_relative_path=sanitized_rel_path,
                discovery_status=DatasetStatus.INVALID,
                discovered_image_files=0,
                discovered_class_directories=0,
                supported_extensions_encountered=[],
                classes=[],
                unreadable_or_inaccessible_count=1,
                ingestion_timestamp=now,
                warnings=[f"Target path '{sanitized_rel_path}' is a file, not a directory."],
                validated_image_files=None,
            )

        now = datetime.now(timezone.utc).isoformat()
        try:
            (
                classes,
                total_images,
                extensions,
                unreadable_count,
                warnings,
            ) = self.scan_directory(target_path)

            if total_images == 0:
                discovery_status = DatasetStatus.INVALID
                warnings.append("No supported image files found in dataset directory.")
            else:
                discovery_status = DatasetStatus.DISCOVERED

            return DatasetDiscoveryResult(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                dataset_source=dataset.source,
                dataset_root_relative_path=sanitized_rel_path,
                discovery_status=discovery_status,
                discovered_image_files=total_images if total_images > 0 else 0,
                discovered_class_directories=len(classes),
                supported_extensions_encountered=extensions,
                classes=classes,
                unreadable_or_inaccessible_count=unreadable_count,
                ingestion_timestamp=now,
                warnings=warnings,
                validated_image_files=None,
            )
        except Exception as exc:
            return DatasetDiscoveryResult(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                dataset_source=dataset.source,
                dataset_root_relative_path=sanitized_rel_path,
                discovery_status=DatasetStatus.ERROR,
                discovered_image_files=None,
                discovered_class_directories=None,
                supported_extensions_encountered=[],
                classes=[],
                unreadable_or_inaccessible_count=1,
                ingestion_timestamp=now,
                warnings=[f"Unexpected discovery failure: {str(exc)}"],
                validated_image_files=None,
            )


# Global service instance
dataset_discovery_service = DatasetDiscoveryService()

