import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.core.errors import (
    DatasetDirectoryNotFoundError,
    DatasetNotValidatedError,
    InvalidHammingThresholdError,
    InvalidPerceptualHashAlgorithmError,
)
from app.schemas.dataset import (
    DatasetMetadata,
    NearDuplicateAnalysisResult,
    NearDuplicateGroup,
    NearDuplicateMember,
    NearDuplicateQueryConfig,
    PerClassNearDuplicateMetric,
    PerceptualHashAlgorithm,
    ValidationStatus,
)
from app.services.duplicate_detection_service import duplicate_detection_service
from app.services.perceptual_hash_service import perceptual_hash_service
from app.storage.base import StorageBackend


class NearDuplicateDetectionService:
    """
    Intelligence engine for detecting perceptual near-duplicate images in agricultural datasets.
    Supports pHash (default), dHash, and aHash with configurable Hamming distance thresholds.
    Integrates with M2.3 exact duplicates to prevent false inflation.
    Preserves original dataset files (strictly read-only).
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

    def _extract_class_name(self, relative_path: str) -> str:
        """Extract normalized class identifier matching dataset discovery convention."""
        parent = str(Path(relative_path).parent).replace("\\", "/")
        return parent if parent != "." else "_root_"

    def detect_near_duplicates(
        self,
        dataset: DatasetMetadata,
        storage: StorageBackend,
        config: Optional[NearDuplicateQueryConfig] = None,
    ) -> NearDuplicateAnalysisResult:
        """
        Execute perceptual near-duplicate detection on a validated dataset.
        """
        start_time = time.perf_counter()
        now = datetime.now(timezone.utc).isoformat()
        warnings: List[str] = []

        if dataset.validation is None:
            raise DatasetNotValidatedError(dataset.id)

        query_config = config or NearDuplicateQueryConfig()
        algorithm = query_config.algorithm
        hash_size = query_config.hash_size
        distance_threshold = query_config.distance_threshold
        total_bits = hash_size * hash_size

        # Validate algorithm
        if algorithm not in PerceptualHashAlgorithm:
            raise InvalidPerceptualHashAlgorithmError(
                str(algorithm), [a.value for a in PerceptualHashAlgorithm]
            )

        # Validate threshold
        if distance_threshold < 0 or distance_threshold > total_bits:
            raise InvalidHammingThresholdError(distance_threshold, total_bits)

        similarity_threshold = perceptual_hash_service.compute_similarity(
            distance_threshold, total_bits=total_bits
        )

        # Resolve dataset filesystem root
        if dataset.is_curated:
            dataset_root = storage.get_curated_path(dataset.slug)
        else:
            dataset_root = storage.get_extract_path(dataset.id)

        if not dataset_root.exists() or not dataset_root.is_dir():
            raise DatasetDirectoryNotFoundError(dataset.id, str(dataset_root))

        dataset_root_resolved = dataset_root.resolve()

        # Gather eligible images from M2.2 validation (status == VALID)
        all_validation_records = dataset.validation.images or []
        eligible_records = [
            r for r in all_validation_records if r.status == ValidationStatus.VALID
        ]
        total_eligible = len(eligible_records)

        # Retrieve or compute M2.3 exact duplicates to prevent inflating near-duplicate metrics
        exact_duplicate_paths: Set[str] = set()
        if dataset.duplicates is None:
            try:
                exact_res = duplicate_detection_service.detect_duplicates(dataset, storage)
                dataset.duplicates = exact_res
                dataset.duplicate_groups_count = exact_res.exact_duplicate_groups
            except Exception as exc:
                warnings.append(f"Notice: Exact duplicate pre-scan could not be completed: {exc}")

        if dataset.duplicates:
            for g in dataset.duplicates.groups:
                for dup in g.duplicates:
                    exact_duplicate_paths.add(dup.relative_path)

        collapsed_exact_count = len(exact_duplicate_paths)

        # Sort records deterministically by relative_path
        sorted_records = sorted(eligible_records, key=lambda r: r.relative_path)

        # Compute perceptual hashes for eligible images
        # Map: relative_path -> (perceptual_hash_hex, file_size_bytes, class_name)
        image_hashes: Dict[str, Tuple[str, int, str]] = {}
        unique_hashes_set: Set[str] = set()
        hashing_failures = 0
        class_eligible_counts: Dict[str, int] = defaultdict(int)

        for record in sorted_records:
            class_name = self._extract_class_name(record.relative_path)
            class_eligible_counts[class_name] += 1
            file_path = dataset_root / record.relative_path

            if file_path.is_symlink() and not self._is_symlink_safe(
                file_path, dataset_root_resolved
            ):
                hashing_failures += 1
                warnings.append(
                    f"Symlink escapes dataset boundary, skipped: {record.relative_path}"
                )
                continue

            try:
                if not file_path.exists():
                    hashing_failures += 1
                    warnings.append(
                        f"File missing on filesystem when hashing: {record.relative_path}"
                    )
                    continue

                phash_hex = perceptual_hash_service.compute_hash(
                    file_path=file_path,
                    algorithm=algorithm,
                    hash_size=hash_size,
                )
                image_hashes[record.relative_path] = (
                    phash_hex,
                    record.file_size_bytes,
                    class_name,
                )
                unique_hashes_set.add(phash_hex)

            except Exception as exc:
                hashing_failures += 1
                warnings.append(
                    f"Perceptual hashing failed for {record.relative_path}: {exc}"
                )

        successfully_hashed = len(image_hashes)
        unique_hashes_count = len(unique_hashes_set)

        # Filter candidates for pairwise comparison:
        # Exclude redundant exact duplicates to avoid duplicate inflation
        candidate_paths = [
            p for p in sorted(image_hashes.keys()) if p not in exact_duplicate_paths
        ]
        num_candidates = len(candidate_paths)

        # Total pairwise comparisons: N * (N - 1) // 2
        pairwise_comparisons = (
            (num_candidates * (num_candidates - 1)) // 2 if num_candidates > 1 else 0
        )

        # Build candidate adjacency graph: path -> List of (neighbor_path, distance, similarity)
        adjacency: Dict[str, List[Tuple[str, int, float]]] = defaultdict(list)

        for i in range(num_candidates):
            path_i = candidate_paths[i]
            hash_i = image_hashes[path_i][0]

            for j in range(i + 1, num_candidates):
                path_j = candidate_paths[j]
                hash_j = image_hashes[path_j][0]

                dist = perceptual_hash_service.compute_hamming_distance(hash_i, hash_j)
                if dist <= distance_threshold:
                    sim = perceptual_hash_service.compute_similarity(
                        dist, total_bits=total_bits
                    )
                    adjacency[path_i].append((path_j, dist, sim))
                    adjacency[path_j].append((path_i, dist, sim))

        # Clustering & Group Formation:
        # Find connected components in the candidate adjacency graph
        visited: Set[str] = set()
        components: List[List[str]] = []

        for p in candidate_paths:
            if p not in visited and p in adjacency:
                comp: List[str] = []
                queue = [p]
                visited.add(p)

                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor, _, _ in adjacency[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                if len(comp) >= 2:
                    components.append(sorted(comp))

        # Sort components deterministically by representative path
        components.sort(key=lambda c: c[0])

        near_duplicate_groups: List[NearDuplicateGroup] = []
        cross_class_group_count = 0
        total_redundant_instances = 0
        total_images_in_groups = 0
        class_duplicate_instances: Dict[str, int] = defaultdict(int)

        for comp in components:
            # Canonical representative is lexicographically smallest path
            rep_path = comp[0]
            rep_hash, rep_size, rep_class = image_hashes[rep_path]

            representative_member = NearDuplicateMember(
                relative_path=rep_path,
                class_name=rep_class,
                perceptual_hash=rep_hash,
                file_size_bytes=rep_size,
                is_representative=True,
                hamming_distance_to_representative=0,
                similarity_to_representative=1.0,
            )

            near_duplicate_members: List[NearDuplicateMember] = []
            distances_to_rep: List[int] = [0]
            similarities_to_rep: List[float] = [1.0]

            # Verify within-group relationships and check for non-transitive chains
            has_transitive_chain = False
            max_within_pair_dist = 0

            for member_path in comp[1:]:
                m_hash, m_size, m_class = image_hashes[member_path]
                dist_to_rep = perceptual_hash_service.compute_hamming_distance(
                    rep_hash, m_hash
                )
                sim_to_rep = perceptual_hash_service.compute_similarity(
                    dist_to_rep, total_bits=total_bits
                )

                distances_to_rep.append(dist_to_rep)
                similarities_to_rep.append(sim_to_rep)

                near_duplicate_members.append(
                    NearDuplicateMember(
                        relative_path=member_path,
                        class_name=m_class,
                        perceptual_hash=m_hash,
                        file_size_bytes=m_size,
                        is_representative=False,
                        hamming_distance_to_representative=dist_to_rep,
                        similarity_to_representative=sim_to_rep,
                    )
                )

            # Check if any pairwise distance between members exceeds threshold (transitive chain)
            for a_idx in range(len(comp)):
                for b_idx in range(a_idx + 1, len(comp)):
                    h_a = image_hashes[comp[a_idx]][0]
                    h_b = image_hashes[comp[b_idx]][0]
                    d_ab = perceptual_hash_service.compute_hamming_distance(h_a, h_b)
                    if d_ab > max_within_pair_dist:
                        max_within_pair_dist = d_ab
                    if d_ab > distance_threshold:
                        has_transitive_chain = True

            group_id = f"ndup-{rep_hash[:16]}"

            if has_transitive_chain:
                warnings.append(
                    f"Transitive similarity chain observed in group '{group_id}': maximum pairwise distance is {max_within_pair_dist} bits (threshold is {distance_threshold})."
                )

            all_members_in_group = [representative_member] + near_duplicate_members
            classes_involved = sorted(list(set(m.class_name for m in all_members_in_group)))
            is_cross_class = len(classes_involved) > 1

            if is_cross_class:
                cross_class_group_count += 1

            group = NearDuplicateGroup(
                group_id=group_id,
                algorithm=algorithm.value,
                representative=representative_member,
                near_duplicates=near_duplicate_members,
                image_count=len(all_members_in_group),
                classes_involved=classes_involved,
                is_cross_class=is_cross_class,
                max_distance_in_group=max(distances_to_rep),
                min_similarity_in_group=min(similarities_to_rep),
            )
            near_duplicate_groups.append(group)

            total_redundant_instances += len(near_duplicate_members)
            total_images_in_groups += len(all_members_in_group)

            for dup in near_duplicate_members:
                class_duplicate_instances[dup.class_name] += 1

        # Sort groups deterministically: largest group first, then by group_id
        near_duplicate_groups.sort(key=lambda g: (-g.image_count, g.group_id))

        # Overall near-duplicate percentage
        if successfully_hashed > 0:
            near_duplicate_percentage = round(
                (total_redundant_instances / successfully_hashed) * 100, 2
            )
        else:
            near_duplicate_percentage = 0.0

        # Calculate per-class near-duplicate metrics
        class_metrics: Dict[str, PerClassNearDuplicateMetric] = {}
        for class_name in sorted(class_eligible_counts.keys()):
            c_total = class_eligible_counts[class_name]
            c_dups = class_duplicate_instances.get(class_name, 0)
            c_pct = round((c_dups / c_total) * 100, 2) if c_total > 0 else 0.0

            class_metrics[class_name] = PerClassNearDuplicateMetric(
                class_name=class_name,
                total_images=c_total,
                near_duplicate_instances=c_dups,
                near_duplicate_percentage=c_pct,
            )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return NearDuplicateAnalysisResult(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            analysis_timestamp=now,
            algorithm=algorithm.value,
            hash_size=hash_size,
            distance_threshold=distance_threshold,
            similarity_threshold=similarity_threshold,
            total_eligible_images=total_eligible,
            successfully_hashed_images=successfully_hashed,
            hashing_failures=hashing_failures,
            unique_perceptual_hashes=unique_hashes_count,
            exact_duplicates_collapsed_count=collapsed_exact_count,
            unique_content_representatives_compared=num_candidates,
            pairwise_comparisons_performed=pairwise_comparisons,
            near_duplicate_groups=len(near_duplicate_groups),
            images_in_near_duplicate_groups=total_images_in_groups,
            redundant_near_duplicate_instances=total_redundant_instances,
            near_duplicate_percentage=near_duplicate_percentage,
            cross_class_near_duplicate_groups=cross_class_group_count,
            analysis_duration_ms=duration_ms,
            groups=near_duplicate_groups,
            class_metrics=class_metrics,
            warnings=warnings,
        )


# Global singleton instance
near_duplicate_detection_service = NearDuplicateDetectionService()

