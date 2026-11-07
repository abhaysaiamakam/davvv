import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.errors import (
    CropLensBaseException,
    DatasetNotFoundError,
)
from app.schemas.analysis import (
    AnalysisConfig,
    AnalysisListResponse,
    AnalysisStatus,
    AnalysisStatusResponse,
    AnalysisSummary,
    UnifiedAnalysisMetrics,
    UnifiedAnalysisResult,
)
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetStatus,
    NearDuplicateQueryConfig,
)
from app.storage.base import StorageBackend
from app.storage.local import storage_backend

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Unified analysis service orchestrating dataset discovery, image validation,
    exact duplicate detection, and perceptual near-duplicate detection.
    Persists results to disk and manages analysis lifecycles.
    """

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or storage_backend
        self._analyses: Dict[str, UnifiedAnalysisResult] = {}
        self._rehydrate_from_storage()

    def _rehydrate_from_storage(self) -> None:
        """Load previously persisted analysis records from storage into in-memory cache."""
        try:
            persisted = self.storage.list_persisted_analyses()
            for record in persisted:
                try:
                    result = UnifiedAnalysisResult.model_validate(record)
                    self._analyses[result.id] = result
                except Exception as parse_err:
                    logger.warning(
                        f"Failed to parse persisted analysis record {record.get('id')}: {parse_err}"
                    )
        except Exception as exc:
            logger.warning(f"Error rehydrating analyses from storage: {exc}")

    def list_analyses(self) -> AnalysisListResponse:
        """Return list of all analyses, newest first."""
        items: List[AnalysisSummary] = [
            res.to_summary() for res in self._analyses.values()
        ]
        # Sort newest first
        items.sort(key=lambda s: str(s.created_at), reverse=True)
        return AnalysisListResponse(
            total=len(items),
            items=items,
            is_placeholder=len(items) == 0,
            note="Unified analysis records."
            if items
            else "No analyses executed yet.",
        )

    def get_analysis(self, analysis_id: str) -> Optional[UnifiedAnalysisResult]:
        """Retrieve a specific analysis by its identifier, checking cache then storage."""
        if analysis_id in self._analyses:
            return self._analyses[analysis_id]

        data = self.storage.load_analysis(analysis_id)
        if data:
            try:
                result = UnifiedAnalysisResult.model_validate(data)
                self._analyses[result.id] = result
                return result
            except Exception as parse_err:
                logger.error(f"Failed to validate loaded analysis {analysis_id}: {parse_err}")
                return None
        return None

    def get_latest_analysis_for_dataset(self, dataset_id: str) -> Optional[UnifiedAnalysisResult]:
        """Retrieve the latest analysis result for a dataset."""
        latest_id = self.storage.get_latest_analysis_id_for_dataset(dataset_id)
        if latest_id:
            res = self.get_analysis(latest_id)
            if res:
                return res

        # Fallback: scan in-memory analyses for dataset_id
        matching = [
            res for res in self._analyses.values()
            if res.dataset_id == dataset_id or (getattr(res, "dataset_id", "") == dataset_id)
        ]
        if matching:
            matching.sort(key=lambda r: str(r.created_at), reverse=True)
            return matching[0]

        return None

    def get_analysis_status(self, analysis_id: str) -> Optional[AnalysisStatusResponse]:
        """Retrieve current lifecycle status for an analysis run."""
        res = self.get_analysis(analysis_id)
        if not res:
            return None

        return AnalysisStatusResponse(
            analysis_id=res.id,
            dataset_id=res.dataset_id,
            status=res.status,
            created_at=res.created_at,
            started_at=res.started_at,
            completed_at=res.completed_at,
            duration_ms=res.duration_ms,
            stages_completed=res.stages_completed,
            current_stage=None if res.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED) else "running",
            error_message=res.error_message,
        )

    def run_analysis(
        self,
        dataset_id: str,
        config: Optional[AnalysisConfig] = None,
    ) -> UnifiedAnalysisResult:
        """
        Execute unified analysis workflow orchestrating M2.1–M2.4.
        
        Stages:
          1. Discovery (M2.1)
          2. Image validation (M2.2)
          3. Exact duplicate detection (M2.3)
          4. Perceptual near-duplicate detection (M2.4)
          
        Reuses valid existing stage results if not force_refresh.
        Assembles metrics without double-counting and persists result.
        """
        # Local import to prevent circular import
        from app.services.dataset_service import dataset_service

        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        effective_config = config or AnalysisConfig()
        analysis_id = f"ana-{dataset.slug}-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()

        # Initialize result model
        result = UnifiedAnalysisResult(
            id=analysis_id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            status=AnalysisStatus.RUNNING,
            created_at=now,
            started_at=now,
            config=effective_config,
            stages_completed=[],
            stage_durations_ms={},
            metrics=UnifiedAnalysisMetrics(),
            warnings=[],
        )

        # Register in active cache
        self._analyses[analysis_id] = result
        dataset.status = DatasetStatus.ANALYZING

        start_time = time.perf_counter()
        warnings_set = set()

        try:
            # -------------------------------------------------------------
            # Stage 1: Discovery (M2.1)
            # -------------------------------------------------------------
            t_stage_start = time.perf_counter()
            if not effective_config.force_refresh and dataset.discovery is not None:
                discovery_res = dataset.discovery
                logger.info(f"Reusing existing discovery result for {dataset_id}")
            else:
                discovery_res = dataset_service.discover_dataset(dataset.id)

            t_discovery_duration = (time.perf_counter() - t_stage_start) * 1000.0
            result.stage_durations_ms["discovery"] = round(t_discovery_duration, 2)
            result.stages_completed.append("discovery")
            result.discovery = discovery_res
            result.metrics.total_files_discovered = discovery_res.discovered_image_files
            result.metrics.total_classes_discovered = discovery_res.discovered_class_directories
            for w in discovery_res.warnings:
                warnings_set.add(w)

            # -------------------------------------------------------------
            # Stage 2: Image Integrity & Validation (M2.2)
            # -------------------------------------------------------------
            t_stage_start = time.perf_counter()
            if not effective_config.force_refresh and dataset.validation is not None:
                validation_res = dataset.validation
                logger.info(f"Reusing existing validation result for {dataset_id}")
            else:
                validation_res = dataset_service.validate_dataset(dataset.id)

            t_val_duration = (time.perf_counter() - t_stage_start) * 1000.0
            result.stage_durations_ms["validation"] = round(t_val_duration, 2)
            result.stages_completed.append("validation")
            result.validation = validation_res
            result.metrics.total_validated_images = validation_res.total_validated_images
            result.metrics.total_corrupted_images = validation_res.total_corrupted_images
            result.metrics.total_unreadable_images = validation_res.total_unreadable_images
            result.metrics.total_processing_errors = validation_res.total_processing_errors
            result.metrics.total_unsupported_files = validation_res.total_unsupported_files
            for w in validation_res.warnings:
                warnings_set.add(w)

            # -------------------------------------------------------------
            # Stage 3: Exact Duplicate Detection (M2.3)
            # -------------------------------------------------------------
            t_stage_start = time.perf_counter()
            if not effective_config.force_refresh and dataset.duplicates is not None:
                duplicates_res = dataset.duplicates
                logger.info(f"Reusing existing exact duplicate result for {dataset_id}")
            else:
                duplicates_res = dataset_service.detect_duplicates(dataset.id)

            t_dup_duration = (time.perf_counter() - t_stage_start) * 1000.0
            result.stage_durations_ms["exact_duplicates"] = round(t_dup_duration, 2)
            result.stages_completed.append("exact_duplicates")
            result.exact_duplicates = duplicates_res
            result.metrics.exact_duplicate_groups = duplicates_res.exact_duplicate_groups
            result.metrics.exact_duplicate_redundant_instances = duplicates_res.duplicate_instances_count
            result.metrics.exact_duplicate_percentage = duplicates_res.duplicate_percentage
            result.metrics.cross_class_exact_duplicate_groups = duplicates_res.cross_class_duplicate_groups
            for w in duplicates_res.warnings:
                warnings_set.add(w)

            # -------------------------------------------------------------
            # Stage 4: Perceptual Near-Duplicate Detection (M2.4)
            # -------------------------------------------------------------
            if effective_config.include_near_duplicates:
                t_stage_start = time.perf_counter()
                ndup_cfg = effective_config.near_duplicate_config
                if (
                    not effective_config.force_refresh
                    and dataset.near_duplicates is not None
                    and (ndup_cfg is None or (
                        dataset.near_duplicates.algorithm == ndup_cfg.algorithm
                        and dataset.near_duplicates.distance_threshold == ndup_cfg.distance_threshold
                        and dataset.near_duplicates.hash_size == ndup_cfg.hash_size
                    ))
                ):
                    near_dups_res = dataset.near_duplicates
                    logger.info(f"Reusing existing near duplicate result for {dataset_id}")
                else:
                    near_dups_res = dataset_service.detect_near_duplicates(
                        dataset.id, ndup_cfg
                    )

                t_ndup_duration = (time.perf_counter() - t_stage_start) * 1000.0
                result.stage_durations_ms["near_duplicates"] = round(t_ndup_duration, 2)
                result.stages_completed.append("near_duplicates")
                result.near_duplicates = near_dups_res
                result.metrics.near_duplicate_groups = near_dups_res.near_duplicate_groups
                result.metrics.near_duplicate_images_in_groups = near_dups_res.images_in_near_duplicate_groups
                result.metrics.near_duplicate_redundant_instances = near_dups_res.redundant_near_duplicate_instances
                
                # Near-duplicate percentage with explicit total_validated_images denominator
                total_valid = validation_res.total_validated_images
                if total_valid > 0:
                    result.metrics.near_duplicate_percentage = round(
                        (near_dups_res.redundant_near_duplicate_instances / total_valid) * 100.0, 2
                    )
                else:
                    result.metrics.near_duplicate_percentage = 0.0

                result.metrics.cross_class_near_duplicate_groups = near_dups_res.cross_class_near_duplicate_groups
                for w in near_dups_res.warnings:
                    warnings_set.add(w)

            # -------------------------------------------------------------
            # Consolidated Non-Redundant & Quality Metrics
            # -------------------------------------------------------------
            # M2.4 collapses exact duplicates before pairwise hashing, so exact and near
            # redundant instances are mutually exclusive sets.
            exact_red = result.metrics.exact_duplicate_redundant_instances or 0
            near_red = result.metrics.near_duplicate_redundant_instances or 0
            total_red = exact_red + near_red
            result.metrics.total_redundant_images = total_red

            total_valid = result.metrics.total_validated_images or 0
            clean_unique = max(0, total_valid - total_red)
            result.metrics.clean_unique_images = clean_unique

            # Quality Score [0.0 - 100.0]:
            # 50% image integrity (valid / (valid + corrupted)) + 50% image uniqueness (clean / valid)
            total_evaluated = total_valid + (result.metrics.total_corrupted_images or 0)
            if total_evaluated > 0 and total_valid > 0:
                integrity_ratio = total_valid / total_evaluated
                uniqueness_ratio = clean_unique / total_valid
                score = round((integrity_ratio * 0.5 + uniqueness_ratio * 0.5) * 100.0, 2)
                result.metrics.quality_score = score
            else:
                result.metrics.quality_score = None

            # Finalize analysis metadata
            total_wall_ms = (time.perf_counter() - start_time) * 1000.0
            result.duration_ms = round(total_wall_ms, 2)
            result.completed_at = datetime.now(timezone.utc).isoformat()
            result.status = AnalysisStatus.COMPLETED
            result.warnings = sorted(list(warnings_set))

            dataset.status = DatasetStatus.READY

            # Persist completed analysis to disk
            try:
                self.storage.save_analysis(
                    analysis_id=result.id,
                    data=result.model_dump(),
                    dataset_id=dataset.id,
                )
            except Exception as persist_err:
                logger.error(f"Failed to persist analysis {result.id} to storage: {persist_err}")
                result.warnings.append(f"Persistence warning: {persist_err}")

            return result

        except Exception as exc:
            total_wall_ms = (time.perf_counter() - start_time) * 1000.0
            result.duration_ms = round(total_wall_ms, 2)
            result.completed_at = datetime.now(timezone.utc).isoformat()
            result.status = AnalysisStatus.FAILED
            result.error_message = str(exc)
            dataset.status = DatasetStatus.ERROR

            # Persist failed analysis for inspection
            try:
                self.storage.save_analysis(
                    analysis_id=result.id,
                    data=result.model_dump(),
                    dataset_id=dataset.id,
                )
            except Exception:
                pass

            if isinstance(exc, CropLensBaseException):
                raise
            raise


analysis_service = AnalysisService()
