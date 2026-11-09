import logging
import shutil
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from app.core.errors import (
    DatasetAlreadyExistsError,
    DatasetEmptyError,
    DatasetNotFoundError,
    DatasetNotUploadedError,
    DatasetNotDiscoveredError,
    DatasetNotValidatedError,
    DatasetAnalysisNotFoundError,
    DuplicateAnalysisNotFoundError,
    NearDuplicateAnalysisNotFoundError,
    VersionNotFoundError,
)
from app.schemas.analysis import AnalysisConfig, UnifiedAnalysisResult
from app.schemas.dataset import (
    DatasetDiscoveryResult,
    DatasetListResponse,
    DatasetMetadata,
    DatasetRegisterRequest,
    DatasetSource,
    DatasetStatus,
    DatasetUploadResponse,
    DatasetValidationResult,
    DatasetVersion,
    DatasetVersionListResponse,
    DuplicateAnalysisResult,
    NearDuplicateAnalysisResult,
    NearDuplicateQueryConfig,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.services.dataset_discovery_service import dataset_discovery_service
from app.services.image_validation_service import image_validation_service
from app.services.duplicate_detection_service import duplicate_detection_service
from app.services.near_duplicate_detection_service import near_duplicate_detection_service
from app.storage.local import storage_backend


class DatasetService:
    """Service managing curated agricultural dataset registry and evaluator uploads."""

    def __init__(self):
        now = datetime.now(timezone.utc).isoformat()
        self._discovery_results: Dict[str, DatasetDiscoveryResult] = {}
        self._validation_results: Dict[str, DatasetValidationResult] = {}
        self._duplicate_results: Dict[str, DuplicateAnalysisResult] = {}
        self._near_duplicate_results: Dict[str, NearDuplicateAnalysisResult] = {}
        self._dynamic_registry: Dict[str, DatasetMetadata] = {}
        self._versions: Dict[str, Dict[str, DatasetVersion]] = {}
        self._version_scope: ContextVar[Optional[Tuple[str, str, DatasetMetadata]]] = ContextVar(
            "croplens_dataset_version_scope", default=None
        )
        self._curated_registry: List[DatasetMetadata] = [
            DatasetMetadata(
                id="icar-rice-maize",
                name="ICAR Rice and Maize Disease Dataset",
                slug="icar-rice-maize",
                description="Primary reference dataset from Indian Council of Agricultural Research (ICAR) covering rice and maize foliar diseases.",
                source=DatasetSource.ICAR_RICE_MAIZE,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Rice", "Maize"],
                status=DatasetStatus.REGISTERED,
                tags=["primary", "icar", "field-conditions", "cereal-crops"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/icar-rice-maize",
            ),
            DatasetMetadata(
                id="paddy-doctor",
                name="Paddy Doctor Disease Dataset",
                slug="paddy-doctor",
                description="Supplementary benchmark dataset of real-world smartphone imagery of paddy crop diseases collected in Tamil Nadu.",
                source=DatasetSource.PADDY_DOCTOR,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Paddy / Rice"],
                status=DatasetStatus.REGISTERED,
                tags=["supplementary", "smartphone", "in-the-wild", "paddy"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/paddy-doctor",
            ),
            DatasetMetadata(
                id="mendeley-rice",
                name="Mendeley Rice Leaf Disease Dataset",
                slug="mendeley-rice",
                description="Laboratory and field imagery of major rice diseases for comparative benchmarking.",
                source=DatasetSource.MENDELEY_RICE,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Rice"],
                status=DatasetStatus.REGISTERED,
                tags=["supplementary", "laboratory", "rice"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/mendeley-rice",
            ),
            DatasetMetadata(
                id="plant-village",
                name="PlantVillage Agricultural Benchmark",
                slug="plant-village",
                description="Laboratory controlled background dataset used for cross-dataset domain generalization comparison.",
                source=DatasetSource.PLANT_VILLAGE,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Maize", "Tomato", "Potato", "Pepper"],
                status=DatasetStatus.REGISTERED,
                tags=["supplementary", "controlled-background", "benchmark"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/plant-village",
            ),
            DatasetMetadata(
                id="plant-doc",
                name="PlantDoc In-The-Wild Dataset",
                slug="plant-doc",
                description="Field-condition agricultural images for testing model robustness under variable lighting and occlusions.",
                source=DatasetSource.PLANT_DOC,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Rice", "Maize", "Multi-crop"],
                status=DatasetStatus.REGISTERED,
                tags=["supplementary", "in-the-wild", "complex-backgrounds"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/plant-doc",
            ),
            DatasetMetadata(
                id="chilli-leaf",
                name="Chilli Leaf Disease Dataset",
                slug="chilli-leaf",
                description="Horticultural leaf disease dataset for cross-crop transferability analysis.",
                source=DatasetSource.CHILLI_LEAF,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Chilli"],
                status=DatasetStatus.REGISTERED,
                tags=["supplementary", "horticulture", "chilli"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/chilli-leaf",
            ),
            DatasetMetadata(
                id="kaggle-paddy",
                name="Kaggle Paddy Disease Classification",
                slug="kaggle-paddy",
                description="Community competition dataset featuring extensive annotations across 10 paddy foliar conditions.",
                source=DatasetSource.KAGGLE_PADDY,
                is_curated=True,
                is_uploaded=False,
                created_at=now,
                updated_at=now,
                crops=["Paddy / Rice"],
                status=DatasetStatus.REGISTERED,
                tags=["supplementary", "competition", "paddy"],
                total_images=None,
                total_classes=None,
                validated_image_files=None,
                corrupted_image_files=None,
                storage_relative_path="curated/kaggle-paddy",
            ),
        ]
        self._rehydrate_from_storage()

    def _rehydrate_from_storage(self) -> None:
        """Load dynamic datasets and their versions from disk into memory."""
        try:
            persisted_meta = storage_backend.list_persisted_dataset_metadata()
            for raw_meta in persisted_meta:
                try:
                    ds = DatasetMetadata.model_validate(raw_meta)
                    self._dynamic_registry[ds.id] = ds
                    # Load versions for this dataset
                    v_records = storage_backend.list_persisted_dataset_versions(ds.id)
                    if ds.id not in self._versions:
                        self._versions[ds.id] = {}
                    for v_raw in v_records:
                        try:
                            ver = DatasetVersion.model_validate(v_raw)
                            self._versions[ds.id][ver.version_id] = ver
                        except Exception as v_err:
                            pass
                except Exception as exc:
                    pass
        except Exception:
            pass

    def list_datasets(self) -> DatasetListResponse:
        """
        Return registered datasets list (curated benchmarks + dynamic uploads).
        """
        all_datasets = list(self._curated_registry) + list(self._dynamic_registry.values())
        any_evaluated = any(
            ds.status in (DatasetStatus.DISCOVERED, DatasetStatus.VALIDATED, DatasetStatus.READY)
            for ds in all_datasets
        )
        return DatasetListResponse(
            total=len(all_datasets),
            items=all_datasets,
            is_placeholder=not any_evaluated,
            note="Registered benchmarks and dynamic evaluator datasets with ingestion data."
            if any_evaluated
            else "Development registry. Metric fields are unpopulated until M2 pipeline execution.",
        )

    def get_dataset(self, dataset_id: str) -> Optional[DatasetMetadata]:
        scoped = self._version_scope.get()
        if scoped and scoped[0] == dataset_id:
            return scoped[2]
        # Check dynamic registry first
        if dataset_id in self._dynamic_registry:
            return self._dynamic_registry[dataset_id]
        for ds in self._dynamic_registry.values():
            if ds.slug == dataset_id:
                return ds

        # Check curated registry
        for ds in self._curated_registry:
            if ds.id == dataset_id or ds.slug == dataset_id:
                return ds
        return None

    @contextmanager
    def version_scope(self, dataset_id: str, version_id: str):
        """Bind a worker's dataset reads to one immutable version snapshot."""
        base = self.get_dataset(dataset_id)
        if not base:
            raise DatasetNotFoundError(dataset_id)
        version = self.get_version(dataset_id, version_id)
        if not version:
            raise VersionNotFoundError(dataset_id, version_id)
        snapshot = base.model_copy(update={
            "current_version_id": version.version_id,
            "current_version_number": version.version_number,
            "storage_relative_path": version.storage_relative_path,
            "status": version.status,
        })
        token = self._version_scope.set((dataset_id, version_id, snapshot))
        try:
            yield snapshot
        finally:
            self._version_scope.reset(token)

    def discover_dataset(self, dataset_id: str) -> DatasetDiscoveryResult:
        """
        Trigger discovery on a configured dataset.
        Resolves safe dataset path, scans filesystem, and updates metadata registry.
        """
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        if dataset.is_uploaded and not dataset.storage_relative_path:
            raise DatasetNotUploadedError(dataset_id)

        # Execute discovery through discovery service
        result = dataset_discovery_service.discover_dataset(dataset, storage_backend)

        # Update registry state with computed real values
        dataset.status = result.discovery_status
        dataset.discovery = result
        if result.discovery_status == DatasetStatus.DISCOVERED:
            dataset.total_images = result.discovered_image_files
            dataset.total_classes = result.discovered_class_directories
        elif result.discovery_status == DatasetStatus.INVALID:
            dataset.total_images = 0
            dataset.total_classes = 0

        self._discovery_results[dataset.id] = result
        if dataset.slug != dataset.id:
            self._discovery_results[dataset.slug] = result

        return result

    def get_discovery_result(self, dataset_id: str) -> Optional[DatasetDiscoveryResult]:
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        res = self._discovery_results.get(dataset.id)
        if res:
            return res

        # Check if persisted analysis exists and has discovery
        from app.services.analysis_service import analysis_service
        latest = analysis_service.get_latest_analysis_for_dataset(dataset.id, selected_version_id)
        if latest and latest.discovery:
            self._discovery_results[dataset.id] = latest.discovery
            dataset.discovery = latest.discovery
            dataset.total_images = latest.discovery.discovered_image_files
            dataset.total_classes = latest.discovery.discovered_class_directories
            return latest.discovery

        return None

    def validate_dataset(self, dataset_id: str) -> DatasetValidationResult:
        """
        Trigger image integrity verification on a discovered dataset.
        Confirms discovery has completed, executes byte-level verification,
        and records verified image metrics.
        """
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        # Requirement 8: Confirm that discovery has been completed
        if dataset.status == DatasetStatus.REGISTERED or dataset.discovery is None:
            raise DatasetNotDiscoveredError(dataset_id)

        dataset.status = DatasetStatus.VALIDATING
        try:
            result = image_validation_service.validate_dataset(dataset, storage_backend)

            # Update dataset registry with actual validation metrics
            dataset.status = result.validation_status
            dataset.validation = result
            dataset.validated_image_files = result.total_validated_images
            dataset.corrupted_image_files = result.total_corrupted_images

            self._validation_results[dataset.id] = result
            if dataset.slug != dataset.id:
                self._validation_results[dataset.slug] = result

            return result
        except Exception:
            dataset.status = DatasetStatus.ERROR
            raise

    def get_validation_result(self, dataset_id: str) -> DatasetValidationResult:
        """Retrieve previously computed validation metadata for a dataset."""
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        result = self._validation_results.get(dataset.id)
        if result:
            return result

        # Rehydrate from persisted analysis if present
        from app.services.analysis_service import analysis_service
        latest = analysis_service.get_latest_analysis_for_dataset(dataset.id, selected_version_id)
        if latest and latest.validation:
            self._validation_results[dataset.id] = latest.validation
            dataset.validation = latest.validation
            dataset.validated_image_files = latest.validation.total_validated_images
            dataset.corrupted_image_files = latest.validation.total_corrupted_images
            return latest.validation

        raise DatasetNotValidatedError(dataset_id)

    def detect_duplicates(self, dataset_id: str, version_id: Optional[str] = None) -> DuplicateAnalysisResult:
        """
        Run exact duplicate detection on a validated dataset.
        Identifies byte-identical files using chunked streaming SHA-256.
        """
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        selected_version_id = version_id or dataset.current_version_id
        from app.services.analysis_service import analysis_service
        analysis = analysis_service.get_latest_analysis_for_dataset(dataset_id, selected_version_id)
        if analysis and analysis.validation:
            dataset = dataset.model_copy(update={"validation": analysis.validation})
        else:
            scoped = self._version_scope.get()
            if scoped and scoped[0] == dataset_id and scoped[1] == selected_version_id and scoped[2].validation:
                dataset = dataset.model_copy(update={"validation": scoped[2].validation})
            elif selected_version_id is not None or dataset.validation is None:
                raise DatasetNotValidatedError(dataset_id)

        result = duplicate_detection_service.detect_duplicates(
            dataset, storage_backend, version_id=selected_version_id
        )

        # Update dataset metadata with duplicate metrics
        if selected_version_id == dataset.current_version_id:
            dataset.duplicates = result
            dataset.duplicate_groups_count = result.exact_duplicate_groups

        cache_key = f"{dataset.id}:{selected_version_id or 'legacy'}"
        self._duplicate_results[cache_key] = result

        return result

    def get_duplicate_result(self, dataset_id: str, version_id: Optional[str] = None) -> DuplicateAnalysisResult:
        """Retrieve previously computed duplicate analysis metadata for a dataset."""
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        selected_version_id = version_id or dataset.current_version_id
        result = self._duplicate_results.get(f"{dataset.id}:{selected_version_id or 'legacy'}")
        if result and (selected_version_id is None or result.version_id == selected_version_id):
            return result

        # Rehydrate from persisted analysis if present
        latest = self.get_latest_analysis(dataset.id)
        if latest and latest.exact_duplicates:
            if selected_version_id is None or latest.version_id == selected_version_id:
                self._duplicate_results[f"{dataset.id}:{latest.version_id or 'legacy'}"] = latest.exact_duplicates
                return latest.exact_duplicates

        raise DuplicateAnalysisNotFoundError(dataset_id)

    def detect_near_duplicates(
        self, dataset_id: str, config: Optional[NearDuplicateQueryConfig] = None
    ) -> NearDuplicateAnalysisResult:
        """
        Execute perceptual near-duplicate detection on a validated dataset.
        Identifies visually similar images (pHash, dHash, aHash) within configurable Hamming distance.
        """
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        if dataset.validation is None:
            raise DatasetNotValidatedError(dataset_id)

        result = near_duplicate_detection_service.detect_near_duplicates(
            dataset, storage_backend, config
        )

        # Update dataset metadata with near-duplicate metrics
        dataset.near_duplicates = result
        dataset.near_duplicate_groups_count = result.near_duplicate_groups

        self._near_duplicate_results[dataset.id] = result
        if dataset.slug != dataset.id:
            self._near_duplicate_results[dataset.slug] = result

        return result

    def get_near_duplicate_result(self, dataset_id: str) -> NearDuplicateAnalysisResult:
        """Retrieve previously computed near-duplicate analysis metadata for a dataset."""
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        result = self._near_duplicate_results.get(dataset.id)
        if result:
            return result

        # Rehydrate from persisted analysis if present
        latest = self.get_latest_analysis(dataset.id)
        if latest and latest.near_duplicates:
            self._near_duplicate_results[dataset.id] = latest.near_duplicates
            dataset.near_duplicates = latest.near_duplicates
            dataset.near_duplicate_groups_count = latest.near_duplicates.near_duplicate_groups
            return latest.near_duplicates

        raise NearDuplicateAnalysisNotFoundError(dataset_id)

    def analyze_dataset(
        self,
        dataset_id: str,
        config: Optional[AnalysisConfig] = None,
    ) -> UnifiedAnalysisResult:
        """Execute unified analysis workflow on a dataset via analysis_service."""
        from app.services.analysis_service import analysis_service

        return analysis_service.run_analysis(dataset_id, config)

    def get_latest_analysis(self, dataset_id: str) -> Optional[UnifiedAnalysisResult]:
        """Retrieve the latest completed analysis for a dataset, if any."""
        from app.services.analysis_service import analysis_service

        return analysis_service.get_latest_analysis_for_dataset(dataset_id)

    def assess_quality(self, dataset_id: str, force_refresh: bool = False):
        """Execute comprehensive quality assessment on a dataset via data_quality_service."""
        from app.services.data_quality_service import data_quality_service

        return data_quality_service.assess_dataset(dataset_id, force_refresh=force_refresh)

    def get_latest_quality_assessment(self, dataset_id: str):
        """Retrieve the latest quality assessment report for a dataset, if any."""
        from app.services.data_quality_service import data_quality_service

        return data_quality_service.get_latest_assessment_for_dataset(dataset_id)

    def run_eda(self, dataset_id: str, force_refresh: bool = False):
        """Execute EDA on a dataset via eda_service."""
        from app.services.eda_service import eda_service

        return eda_service.run_eda(dataset_id, force_refresh=force_refresh)

    def get_latest_eda_report(self, dataset_id: str):
        """Retrieve the latest EDA report for a dataset, if any."""
        from app.services.eda_service import eda_service

        return eda_service.get_latest_report_for_dataset(dataset_id)

    # -------------------------------------------------------------------------
    # M6 — Dynamic Registration, Versioning & Upload Lifecycle
    # -------------------------------------------------------------------------

    def register_dataset(self, req: DatasetRegisterRequest) -> DatasetMetadata:
        """Register a new dynamic evaluator dataset."""
        existing = self.get_dataset(req.id)
        if existing:
            raise DatasetAlreadyExistsError(req.id)

        now = datetime.now(timezone.utc).isoformat()
        dataset = DatasetMetadata(
            id=req.id,
            name=req.name,
            slug=req.id,
            description=req.description or f"Dynamically registered dataset '{req.name}'.",
            source=req.source,
            is_curated=False,
            is_uploaded=True,
            created_at=now,
            updated_at=now,
            crops=req.crops,
            tags=req.tags,
            status=DatasetStatus.REGISTERED,
            total_images=None,
            total_classes=None,
            validated_image_files=None,
            corrupted_image_files=None,
            storage_relative_path=None,
            total_versions=0,
        )

        storage_backend.save_dataset_metadata(dataset.id, dataset.model_dump())
        self._dynamic_registry[dataset.id] = dataset

        event_bus.emit(
            DatasetEventType.DATASET_UPLOADED,
            dataset_id=dataset.id,
            payload={"name": dataset.name, "created_at": now},
        )
        return dataset

    def create_version(
        self,
        dataset_id: str,
        storage_relative_path: str,
        content_fingerprint: str,
    ) -> Tuple[DatasetVersion, bool]:
        """
        Create a new version for a dataset.
        If content fingerprint matches the latest version, reuses the existing version without re-analyzing.
        """
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        existing_versions = self.list_versions(dataset_id)
        if existing_versions:
            latest = existing_versions[0]
            if latest.content_fingerprint == content_fingerprint and latest.status in (
                DatasetStatus.READY, DatasetStatus.REGISTERED, DatasetStatus.ANALYZING
            ):
                logger.info(
                    f"Content fingerprint {content_fingerprint[:8]} matches active version {latest.version_id}. Reusing."
                )
                return latest, True

        next_ver_num = len(existing_versions) + 1
        version_id = f"ver-{dataset_id}-{next_ver_num}-{content_fingerprint[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        version = DatasetVersion(
            version_id=version_id,
            version_number=next_ver_num,
            dataset_id=dataset_id,
            content_fingerprint=content_fingerprint,
            created_at=now,
            storage_relative_path=storage_relative_path,
            status=DatasetStatus.REGISTERED,
            image_count=None,
            class_count=None,
        )

        storage_backend.save_dataset_version(dataset_id, version_id, version.model_dump())

        if dataset_id not in self._versions:
            self._versions[dataset_id] = {}
        self._versions[dataset_id][version_id] = version

        # Update dataset metadata with new version pointer
        dataset.storage_relative_path = storage_relative_path
        dataset.current_version_id = version_id
        dataset.current_version_number = next_ver_num
        dataset.total_versions = len(self._versions[dataset_id])
        dataset.content_fingerprint = content_fingerprint
        dataset.status = DatasetStatus.REGISTERED
        dataset.updated_at = now

        storage_backend.save_dataset_metadata(dataset_id, dataset.model_dump())

        event_bus.emit(
            DatasetEventType.DATASET_VERSION_CREATED,
            dataset_id=dataset_id,
            version_id=version_id,
            payload={
                "version_number": next_ver_num,
                "content_fingerprint": content_fingerprint,
            },
        )

        return version, False

    def get_version(self, dataset_id: str, version_id: str) -> Optional[DatasetVersion]:
        """Retrieve a specific dataset version."""
        if dataset_id in self._versions and version_id in self._versions[dataset_id]:
            return self._versions[dataset_id][version_id]

        data = storage_backend.load_dataset_version(dataset_id, version_id)
        if data:
            try:
                ver = DatasetVersion.model_validate(data)
                if dataset_id not in self._versions:
                    self._versions[dataset_id] = {}
                self._versions[dataset_id][version_id] = ver
                return ver
            except Exception:
                pass
        return None

    def list_versions(self, dataset_id: str) -> List[DatasetVersion]:
        """List all versions for a dataset, sorted newest first."""
        records = storage_backend.list_persisted_dataset_versions(dataset_id)
        results: List[DatasetVersion] = []
        for r in records:
            try:
                v = DatasetVersion.model_validate(r)
                results.append(v)
                if dataset_id not in self._versions:
                    self._versions[dataset_id] = {}
                self._versions[dataset_id][v.version_id] = v
            except Exception:
                pass

        # If disk was empty, fallback to memory
        if not results and dataset_id in self._versions:
            results = list(self._versions[dataset_id].values())

        results.sort(key=lambda x: (x.version_number, x.created_at), reverse=True)
        return results

    def get_latest_version(self, dataset_id: str) -> Optional[DatasetVersion]:
        """Retrieve latest successful ready version, or latest version overall."""
        scoped = self._version_scope.get()
        if scoped and scoped[0] == dataset_id:
            return self.get_version(dataset_id, scoped[1])
        versions = self.list_versions(dataset_id)
        if not versions:
            return None
        # Prefer ready versions
        ready_versions = [v for v in versions if v.status == DatasetStatus.READY]
        if ready_versions:
            return ready_versions[0]
        return versions[0]

    def mark_version_ready(
        self,
        dataset_id: str,
        version_id: str,
        source_analysis_id: Optional[str],
        source_quality_id: str,
        source_eda_id: str,
        image_count: Optional[int],
        class_count: Optional[int],
    ) -> None:
        """Mark dataset version and active dataset state as completed and ready."""
        ver = self.get_version(dataset_id, version_id)
        if ver:
            ver.status = DatasetStatus.READY
            ver.source_analysis_id = source_analysis_id
            ver.source_quality_id = source_quality_id
            ver.source_eda_id = source_eda_id
            ver.image_count = image_count
            ver.class_count = class_count
            storage_backend.save_dataset_version(dataset_id, version_id, ver.model_dump())

        dataset = self._dynamic_registry.get(dataset_id) or next(
            (item for item in self._curated_registry if item.id == dataset_id), None
        )
        if dataset and dataset.current_version_id == version_id:
            dataset.status = DatasetStatus.READY
            dataset.validated_image_files = image_count
            dataset.total_images = image_count
            dataset.total_classes = class_count
            storage_backend.save_dataset_metadata(dataset_id, dataset.model_dump())

    def mark_version_analyzing(self, dataset_id: str, version_id: str) -> None:
        """Mark only the requested snapshot as actively processing."""
        version = self.get_version(dataset_id, version_id)
        if version:
            version.status = DatasetStatus.ANALYZING
            storage_backend.save_dataset_version(dataset_id, version_id, version.model_dump())
        dataset = self._dynamic_registry.get(dataset_id) or next(
            (item for item in self._curated_registry if item.id == dataset_id), None
        )
        if dataset and dataset.current_version_id == version_id:
            dataset.status = DatasetStatus.ANALYZING
            storage_backend.save_dataset_metadata(dataset_id, dataset.model_dump())

    def mark_version_failed(
        self, dataset_id: str, version_id: str, error_message: str
    ) -> None:
        """Mark version as failed. Preserves previous successful version if present."""
        ver = self.get_version(dataset_id, version_id)
        if ver:
            ver.status = DatasetStatus.ERROR
            ver.error_message = error_message
            storage_backend.save_dataset_version(dataset_id, version_id, ver.model_dump())

        dataset = self._dynamic_registry.get(dataset_id) or next(
            (item for item in self._curated_registry if item.id == dataset_id), None
        )
        if dataset and dataset.current_version_id == version_id:
            # Check if there is a previous ready version
            versions = self.list_versions(dataset_id)
            ready_versions = [v for v in versions if v.status == DatasetStatus.READY and v.version_id != version_id]
            if ready_versions:
                last_good = ready_versions[0]
                dataset.status = DatasetStatus.READY
                dataset.current_version_id = last_good.version_id
                dataset.current_version_number = last_good.version_number
                dataset.storage_relative_path = last_good.storage_relative_path
            else:
                dataset.status = DatasetStatus.ERROR

            storage_backend.save_dataset_metadata(dataset_id, dataset.model_dump())

    def handle_archive_upload(
        self,
        dataset_id: str,
        archive_path: Path,
        filename: str,
        dataset_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DatasetUploadResponse:
        """
        Coordinates full upload pipeline:
        1. Ensures dataset is registered.
        2. Safely extracts archive into an isolated version extraction directory.
        3. Computes deterministic content fingerprint.
        4. Detects identical duplicate content; if duplicate, skips analysis and reuses version.
        5. Creates new dataset version.
        6. Enqueues asynchronous analysis job.
        """
        from app.services.upload_service import upload_service
        from app.services.job_service import job_service

        dataset = self.get_dataset(dataset_id)
        if not dataset:
            # Auto-register dynamic dataset
            dataset = self.register_dataset(
                DatasetRegisterRequest(
                    id=dataset_id,
                    name=dataset_name or dataset_id,
                    description=description or f"Dataset {dataset_id}",
                    source=DatasetSource.EVALUATOR_UPLOAD,
                )
            )

        # Temporary extraction path to verify contents and fingerprint
        temp_extract_token = f"tmp_{uuid.uuid4().hex[:8]}"
        temp_extract_dir = storage_backend.get_extract_path(dataset_id) / temp_extract_token

        try:
            extraction_res = upload_service.extract_archive(archive_path, temp_extract_dir)
            if extraction_res.total_files == 0:
                raise DatasetEmptyError(f"Archive '{filename}' contains 0 extracted files.")

            # Compute fingerprint
            fingerprint = upload_service.compute_content_fingerprint(temp_extract_dir)

            # Create version (or detect duplicate)
            existing_versions = self.list_versions(dataset_id)
            next_num = len(existing_versions) + 1

            # Final version-specific extraction directory
            version_slug = f"v{next_num}"
            final_extract_dir = storage_backend.get_extract_path(dataset_id) / version_slug
            final_extract_rel = storage_backend.sanitize_relative_path(final_extract_dir)

            version, is_duplicate = self.create_version(
                dataset_id=dataset_id,
                storage_relative_path=final_extract_rel,
                content_fingerprint=fingerprint,
            )

            if is_duplicate:
                # Cleanup temp extraction
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
                return DatasetUploadResponse(
                    dataset_id=dataset_id,
                    version_id=version.version_id,
                    version_number=version.version_number,
                    job_id="",
                    status=dataset.status,
                    message="Dataset content is identical to active version. Existing version and analysis reused.",
                    is_duplicate_content=True,
                )

            # Move temp extract to final version directory
            if final_extract_dir.exists():
                shutil.rmtree(final_extract_dir, ignore_errors=True)
            temp_extract_dir.rename(final_extract_dir)

            # Enqueue asynchronous analysis job
            job = job_service.create_job(dataset_id, version.version_id)
            job_service.enqueue_job(job.job_id)

            return DatasetUploadResponse(
                dataset_id=dataset_id,
                version_id=version.version_id,
                version_number=version.version_number,
                job_id=job.job_id,
                status=DatasetStatus.REGISTERED,
                message="Dataset uploaded successfully. Asynchronous analysis pipeline enqueued.",
                is_duplicate_content=False,
            )

        except Exception:
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
            raise

    def reanalyze_dataset(self, dataset_id: str, version_id: Optional[str] = None) -> Any:
        """Trigger a fresh asynchronous analysis job for the exact requested version."""
        from app.services.job_service import job_service

        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        if version_id is None:
            dataset = self.get_dataset(dataset_id)
            version_id = dataset.current_version_id if dataset and dataset.current_version_id else None
        if version_id is None:
            latest_version = self.get_latest_version(dataset_id)
            version_id = latest_version.version_id if latest_version else "v1"
        if not self.get_version(dataset_id, version_id):
            raise VersionNotFoundError(dataset_id, version_id)

        job = job_service.create_job(dataset_id, version_id)
        job_service.enqueue_job(job.job_id)
        return job


dataset_service = DatasetService()
