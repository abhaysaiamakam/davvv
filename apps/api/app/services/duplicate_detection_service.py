import hashlib
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.core.errors import (
    DatasetDirectoryNotFoundError,
    DatasetNotDiscoveredError,
    DatasetNotValidatedError,
)
from app.schemas.dataset import (
    ClassDuplicateMetric,
    DatasetMetadata,
    DatasetStatus,
    DuplicateAnalysisResult,
    DuplicateImageMember,
    ExactDuplicateGroup,
    ValidationStatus,
)
from app.storage.base import StorageBackend

# 64 KB read buffer for streaming SHA-256 calculation
CHUNK_SIZE = 65536


class DuplicateDetectionService:
    """
    Engine for detecting exact (byte-for-byte) duplicate images in agricultural datasets.
    Uses chunked streaming SHA-256 content hashing on validated images.
    Preserves original dataset files (strictly read-only) with path traversal protections.
    """

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

    def compute_file_sha256(self, file_path: Path) -> str:
        """
        Compute SHA-256 hex digest using streaming chunked reads.
        Memory efficient and avoids loading large image files into memory at once.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _extract_class_name(self, relative_path: str) -> str:
        """
        Extract normalized class identifier matching dataset discovery convention.
        Nested folders use forward slash relative path, or '_root_' if directly in dataset root.
        """
        parent = str(Path(relative_path).parent).replace("\\", "/")
        return parent if parent != "." else "_root_"

    def detect_duplicates(
        self, dataset: DatasetMetadata, storage: StorageBackend
    ) -> DuplicateAnalysisResult:
        """
        Execute exact duplicate detection across validated images of a dataset.
        Requires M2.2 validation to have completed.
        """
        now = datetime.now(timezone.utc).isoformat()
        warnings: List[str] = []

        if dataset.validation is None:
            raise DatasetNotValidatedError(dataset.id)

        # Resolve dataset filesystem root
        if dataset.is_curated:
            dataset_root = storage.get_curated_path(dataset.slug)
        else:
            dataset_root = storage.get_extract_path(dataset.id)

        if not dataset_root.exists() or not dataset_root.is_dir():
            raise DatasetDirectoryNotFoundError(dataset.id, str(dataset_root))

        dataset_root_resolved = dataset_root.resolve()

        # Gather eligible images from validation result (status == VALID)
        all_validation_records = dataset.validation.images or []
        eligible_records = [
            r for r in all_validation_records if r.status == ValidationStatus.VALID
        ]

        total_eligible = len(eligible_records)

        # Deterministic processing: sort by relative_path
        sorted_records = sorted(eligible_records, key=lambda r: r.relative_path)

        # Hash map: sha256_hash -> List of DuplicateImageMember
        hash_to_members: Dict[str, List[DuplicateImageMember]] = defaultdict(list)
        file_size_by_hash: Dict[str, int] = {}
        successfully_hashed = 0
        hashing_failures = 0

        # Track class totals for eligible images
        class_eligible_counts: Dict[str, int] = defaultdict(int)

        for record in sorted_records:
            class_name = self._extract_class_name(record.relative_path)
            class_eligible_counts[class_name] += 1

            file_path = dataset_root / record.relative_path

            # Symlink safety check
            if file_path.is_symlink() and not self._is_symlink_safe(
                file_path, dataset_root_resolved
            ):
                hashing_failures += 1
                warnings.append(
                    f"Symlink escapes dataset boundary, skipped hashing: {record.relative_path}"
                )
                continue

            try:
                if not file_path.exists():
                    hashing_failures += 1
                    warnings.append(
                        f"File missing on filesystem when hashing: {record.relative_path}"
                    )
                    continue

                sha256_hex = self.compute_file_sha256(file_path)
                successfully_hashed += 1

                file_size_by_hash[sha256_hex] = record.file_size_bytes

                member = DuplicateImageMember(
                    relative_path=record.relative_path,
                    class_name=class_name,
                    file_size_bytes=record.file_size_bytes,
                    is_representative=False,
                )
                hash_to_members[sha256_hex].append(member)

            except (OSError, PermissionError) as exc:
                hashing_failures += 1
                warnings.append(
                    f"I/O error computing hash for {record.relative_path}: {exc}"
                )

        unique_content_groups = len(hash_to_members)

        # Build duplicate groups (groups with 2 or more members)
        duplicate_groups: List[ExactDuplicateGroup] = []
        cross_class_group_count = 0
        total_duplicate_instances = 0
        total_images_in_groups = 0

        # Track duplicate instances per class
        class_duplicate_instances: Dict[str, int] = defaultdict(int)

        for sha256_hex, members in hash_to_members.items():
            if len(members) >= 2:
                # Deterministic sorting within group
                sorted_members = sorted(members, key=lambda m: m.relative_path)

                # Canonical representative: lexicographically smallest relative path
                representative = sorted_members[0].model_copy(
                    update={"is_representative": True}
                )

                # Remaining members are duplicate instances
                duplicates = [
                    m.model_copy(update={"is_representative": False})
                    for m in sorted_members[1:]
                ]

                # Identify all unique classes in this group
                classes_involved = sorted(list(set(m.class_name for m in sorted_members)))
                is_cross_class = len(classes_involved) > 1

                if is_cross_class:
                    cross_class_group_count += 1

                group_id = f"dup-{sha256_hex[:16]}"
                file_size = file_size_by_hash.get(sha256_hex, representative.file_size_bytes)

                group = ExactDuplicateGroup(
                    group_id=group_id,
                    sha256_hash=sha256_hex,
                    file_size_bytes=file_size,
                    image_count=len(sorted_members),
                    representative=representative,
                    duplicates=duplicates,
                    classes_involved=classes_involved,
                    is_cross_class=is_cross_class,
                )
                duplicate_groups.append(group)

                # Metrics aggregation
                total_duplicate_instances += len(duplicates)
                total_images_in_groups += len(sorted_members)

                # Attribute duplicate instances to classes of the duplicate copies
                for dup in duplicates:
                    class_duplicate_instances[dup.class_name] += 1

        # Deterministic sorting of groups: largest duplicate count first, then by sha256_hash
        duplicate_groups.sort(key=lambda g: (-g.image_count, g.sha256_hash))

        # Overall duplicate percentage (redundant duplicate instances / successfully hashed images)
        if successfully_hashed > 0:
            duplicate_percentage = round(
                (total_duplicate_instances / successfully_hashed) * 100, 2
            )
        else:
            duplicate_percentage = 0.0

        # Calculate per-class duplicate metrics
        class_metrics: Dict[str, ClassDuplicateMetric] = {}
        for class_name in sorted(class_eligible_counts.keys()):
            c_total = class_eligible_counts[class_name]
            c_dups = class_duplicate_instances.get(class_name, 0)
            c_pct = round((c_dups / c_total) * 100, 2) if c_total > 0 else 0.0

            class_metrics[class_name] = ClassDuplicateMetric(
                class_name=class_name,
                total_images=c_total,
                duplicate_instances=c_dups,
                duplicate_percentage=c_pct,
            )

        return DuplicateAnalysisResult(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            analysis_timestamp=now,
            total_eligible_images=total_eligible,
            successfully_hashed_images=successfully_hashed,
            hashing_failures=hashing_failures,
            unique_content_groups=unique_content_groups,
            exact_duplicate_groups=len(duplicate_groups),
            duplicate_instances_count=total_duplicate_instances,
            images_in_duplicate_groups=total_images_in_groups,
            duplicate_percentage=duplicate_percentage,
            cross_class_duplicate_groups=cross_class_group_count,
            groups=duplicate_groups,
            class_metrics=class_metrics,
            warnings=warnings,
        )


# Global singleton instance
duplicate_detection_service = DuplicateDetectionService()

