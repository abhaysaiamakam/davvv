"""
M9 — Feature Engineering Service and Orchestrator.

Manages feature previews, derived version generation, history persistence,
and re-analysis pipeline integration.
"""
from __future__ import annotations

import datetime
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.errors import (
    DatasetNotFoundError,
    VersionNotFoundError,
    PreprocessingError,
    PreprocessingValidationError,
    PreprocessingHistoryNotFoundError,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.feature_engineering import (
    AppliedFeatureOperationRecord,
    AvailableFeaturesResponse,
    FeatureApplyRequest,
    FeatureApplyResponse,
    FeatureHistoryListResponse,
    FeatureHistoryRecord,
    FeatureModality,
    FeatureOperationConfig,
    FeaturePreviewRequest,
    FeaturePreviewResponse,
    FeaturePreviewResult,
)
from app.storage.base import StorageBackend
from app.storage.local import storage_backend
from app.services.feature_engineering.feature_registry import feature_registry
from app.services.dataset_service import dataset_service
from app.services.upload_service import upload_service

logger = logging.getLogger(__name__)


class FeatureEngineeringService:
    """Orchestrates feature engineering simulations, derived version creation, and audit logging."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or storage_backend

    def get_available_features(self, dataset_id: str) -> AvailableFeaturesResponse:
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        dataset_dir = self.storage.resolve_dataset_path(dataset)
        from app.services.preprocessing.preprocessing_registry import preprocessing_registry
        modalities = [
            FeatureModality(m.value) for m in preprocessing_registry.detect_modalities(dataset_dir)
        ]
        features = feature_registry.discover_features(dataset_dir)
        operations = feature_registry.list_operations()

        return AvailableFeaturesResponse(
            dataset_id=dataset_id,
            detected_modalities=modalities,
            current_features=features,
            operations=operations,
        )

    def preview_features(self, req: FeaturePreviewRequest) -> FeaturePreviewResponse:
        dataset = dataset_service.get_dataset(req.dataset_id)
        if not dataset:
            raise DatasetNotFoundError(req.dataset_id)

        if req.version_id:
            version = dataset_service.get_version(req.dataset_id, req.version_id)
            if not version:
                raise VersionNotFoundError(req.dataset_id, req.version_id)
            source_version_id = version.version_id
            source_path = self.storage.base_dir / version.storage_relative_path
        else:
            latest = dataset_service.get_latest_version(req.dataset_id)
            source_version_id = latest.version_id if latest else "v1"
            source_path = self.storage.resolve_dataset_path(dataset)

        if not source_path.exists():
            raise FileNotFoundError(f"Source path {source_path} does not exist.")

        temp_dir = self.storage.results_dir / "temp_feat_preview" / uuid.uuid4().hex[:8]
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            if source_path.is_dir():
                for item in source_path.iterdir():
                    dest = temp_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore_dangling_symlinks=True)
                    else:
                        shutil.copy2(item, dest)
            else:
                shutil.copy2(source_path, temp_dir / source_path.name)

            results: List[FeaturePreviewResult] = []
            can_apply = True
            global_warnings: List[str] = []

            for op_config in req.operations:
                op_handler = feature_registry.get_operation(op_config.operation_type)
                if op_config.modality is None:
                    op_config.modality = op_handler.modality
                preview_res = op_handler.preview(temp_dir, op_config)
                results.append(preview_res)

                if preview_res.status != "valid":
                    can_apply = False
                if preview_res.warnings:
                    global_warnings.extend(preview_res.warnings)

                if preview_res.status == "valid":
                    try:
                        op_handler.apply(temp_dir, op_config)
                    except Exception as exc:
                        logger.warning(f"Feature preview step failed for {op_config.operation_type}: {exc}")

            return FeaturePreviewResponse(
                dataset_id=req.dataset_id,
                source_version_id=source_version_id,
                operations=results,
                total_operations=len(results),
                warnings=global_warnings,
                can_apply=can_apply,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def apply_features(self, req: FeatureApplyRequest) -> FeatureApplyResponse:
        dataset = dataset_service.get_dataset(req.dataset_id)
        if not dataset:
            raise DatasetNotFoundError(req.dataset_id)

        if req.version_id:
            version = dataset_service.get_version(req.dataset_id, req.version_id)
            if not version:
                raise VersionNotFoundError(req.dataset_id, req.version_id)
            source_version_id = version.version_id
            source_path = self.storage.base_dir / version.storage_relative_path
        else:
            latest = dataset_service.get_latest_version(req.dataset_id)
            source_version_id = latest.version_id if latest else "v1"
            source_path = self.storage.resolve_dataset_path(dataset)

        if not source_path.exists():
            raise FileNotFoundError(f"Source path {source_path} does not exist.")

        input_fingerprint = upload_service.compute_content_fingerprint(source_path)

        temp_work_dir = self.storage.results_dir / "temp_feat_work" / uuid.uuid4().hex[:8]
        temp_work_dir.mkdir(parents=True, exist_ok=True)

        try:
            if source_path.is_dir():
                for item in source_path.iterdir():
                    dest = temp_work_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore_dangling_symlinks=True)
                    else:
                        shutil.copy2(item, dest)
            else:
                shutil.copy2(source_path, temp_work_dir / source_path.name)

            applied_records: List[AppliedFeatureOperationRecord] = []
            total_gen_features = 0
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

            for op_config in req.operations:
                op_handler = feature_registry.get_operation(op_config.operation_type)
                if op_config.modality is None:
                    op_config.modality = op_handler.modality
                val_errs = op_handler.validate_parameters(op_config)
                if val_errs:
                    raise PreprocessingValidationError("; ".join(val_errs))

                exec_stats = op_handler.apply(temp_work_dir, op_config)
                gen_feats = exec_stats.get("generated_features", [])
                total_gen_features += len(gen_feats)

                record = AppliedFeatureOperationRecord(
                    operation_id=op_config.operation_id or f"fe-{uuid.uuid4().hex[:6]}",
                    operation_type=op_config.operation_type,
                    modality=op_config.modality,
                    parameters=op_config.parameters,
                    source_features=exec_stats.get("source_features", []),
                    generated_features=gen_feats,
                    removed_features=exec_stats.get("removed_features", []),
                    status="applied",
                    warnings=exec_stats.get("warnings", []),
                    executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
                applied_records.append(record)

            output_fingerprint = upload_service.compute_content_fingerprint(temp_work_dir)

            existing_versions = dataset_service.list_versions(req.dataset_id)
            next_ver_num = len(existing_versions) + 1
            derived_version_id = f"ver-{req.dataset_id}-{next_ver_num}-{output_fingerprint[:8]}"
            version_slug = f"v{next_ver_num}"
            final_derived_dir = self.storage.get_extract_path(req.dataset_id) / version_slug
            final_derived_rel = self.storage.sanitize_relative_path(final_derived_dir)

            derived_version, is_duplicate = dataset_service.create_version(
                dataset_id=req.dataset_id,
                storage_relative_path=final_derived_rel,
                content_fingerprint=output_fingerprint,
            )

            if is_duplicate:
                shutil.rmtree(temp_work_dir, ignore_errors=True)
                return FeatureApplyResponse(
                    dataset_id=req.dataset_id,
                    source_version_id=source_version_id,
                    derived_version_id=derived_version.version_id,
                    version_number=derived_version.version_number,
                    job_id="",
                    status="completed",
                    message="Engineered content is identical to an existing version. Existing version reused.",
                    operations_applied=len(applied_records),
                    new_features_count=total_gen_features,
                    is_duplicate_content=True,
                )

            if final_derived_dir.exists():
                shutil.rmtree(final_derived_dir, ignore_errors=True)
            temp_work_dir.rename(final_derived_dir)

            history_record = FeatureHistoryRecord(
                id=f"fe-hist-{derived_version.version_id}",
                dataset_id=req.dataset_id,
                source_version_id=source_version_id,
                derived_version_id=derived_version.version_id,
                version_number=derived_version.version_number,
                operations=applied_records,
                input_fingerprint=input_fingerprint,
                output_fingerprint=output_fingerprint,
                status="completed",
                created_at=now_str,
                completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            self.storage.save_preprocessing_history(
                req.dataset_id, f"fe-{derived_version.version_id}", history_record.model_dump()
            )

            job = dataset_service.reanalyze_dataset(req.dataset_id, derived_version.version_id)
            history_record.job_id = job.job_id
            self.storage.save_preprocessing_history(
                req.dataset_id, f"fe-{derived_version.version_id}", history_record.model_dump()
            )

            return FeatureApplyResponse(
                dataset_id=req.dataset_id,
                source_version_id=source_version_id,
                derived_version_id=derived_version.version_id,
                version_number=derived_version.version_number,
                job_id=job.job_id,
                status="completed",
                message="Feature engineering applied successfully. Derived version and re-analysis enqueued.",
                operations_applied=len(applied_records),
                new_features_count=total_gen_features,
                is_duplicate_content=False,
            )

        except Exception as exc:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
            logger.error(f"Feature engineering apply failed: {exc}", exc_info=True)
            raise PreprocessingError(str(exc))

    def list_feature_history(self, dataset_id: str) -> FeatureHistoryListResponse:
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)
        items_data = self.storage.list_persisted_preprocessing_history(dataset_id)
        feat_items = [
            FeatureHistoryRecord.model_validate(d)
            for d in items_data
            if "fe-" in d.get("id", "") or any(op.get("operation_type") in [t.value for t in FeatureOperationType.__members__.values()] for op in d.get("operations", []))
        ]
        return FeatureHistoryListResponse(total=len(feat_items), items=feat_items)


feature_engineering_service = FeatureEngineeringService()
