"""
M8 — Preprocessing Service and Orchestrator.

Manages preprocessing previews, derived version generation, asynchronous execution,
history persistence, and downstream pipeline integration (re-analysis, quality, EDA, insights).
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
from app.schemas.preprocessing import (
    AppliedOperationRecord,
    AvailableOperationsResponse,
    PreprocessingApplyRequest,
    PreprocessingApplyResponse,
    PreprocessingHistoryRecord,
    PreprocessingHistoryListResponse,
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingPreviewRequest,
    PreprocessingPreviewResponse,
    OperationPreviewResult,
    OperationStatus,
    PreprocessingOperationType,
)
from app.schemas.dataset import DatasetStatus
from app.storage.base import StorageBackend
from app.storage.local import storage_backend
from app.services.preprocessing.preprocessing_registry import preprocessing_registry
from app.services.dataset_service import dataset_service
from app.services.upload_service import upload_service
from app.services.preprocessing.annotation_preprocessing import _find_coco_files, _find_yolo_files

logger = logging.getLogger(__name__)


class PreprocessingService:
    """Orchestrates dataset preprocessing, preview simulation, version derivation, and history."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or storage_backend

    @staticmethod
    def _validate_annotation_linked_image_operations(dataset_root: Path, operations) -> None:
        unsafe = {
            PreprocessingOperationType.RESIZE_IMAGES,
            PreprocessingOperationType.CONVERT_FORMAT,
        }
        if not any(operation.operation_type in unsafe for operation in operations):
            return
        if _find_coco_files(dataset_root) or _find_yolo_files(dataset_root):
            raise PreprocessingValidationError(
                "Resize and format conversion are unavailable for COCO/YOLO-linked images until the linked annotations can be updated safely."
            )

    def get_available_operations(self, dataset_id: str) -> AvailableOperationsResponse:
        """List all preprocessing operations applicable to the dataset's detected modalities."""
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        dataset_dir = self.storage.resolve_dataset_path(dataset)
        modalities = preprocessing_registry.detect_modalities(dataset_dir)
        operations = preprocessing_registry.get_available_operations_for_dataset(dataset_dir)

        return AvailableOperationsResponse(
            dataset_id=dataset_id,
            detected_modalities=modalities,
            operations=operations,
        )

    def preview_operations(self, req: PreprocessingPreviewRequest) -> PreprocessingPreviewResponse:
        """Simulate a sequence of preprocessing operations against a dataset version without mutating disk."""
        dataset = dataset_service.get_dataset(req.dataset_id)
        if not dataset:
            raise DatasetNotFoundError(req.dataset_id)

        # Determine source version root path
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
            raise FileNotFoundError(f"Source dataset path {source_path} does not exist.")
        self._validate_annotation_linked_image_operations(source_path, req.operations)

        # Create temporary sandbox directory for preview simulations
        temp_preview_dir = self.storage.results_dir / "temp_preview" / uuid.uuid4().hex[:8]
        temp_preview_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Copy source dataset contents into temp sandbox
            if source_path.is_dir():
                for item in source_path.iterdir():
                    dest = temp_preview_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore_dangling_symlinks=True)
                    else:
                        shutil.copy2(item, dest)
            else:
                shutil.copy2(source_path, temp_preview_dir / source_path.name)

            results: List[OperationPreviewResult] = []
            can_apply = True
            global_warnings: List[str] = []

            for op_config in req.operations:
                op_handler = preprocessing_registry.get_operation(op_config.operation_type)
                if op_config.modality is None:
                    op_config.modality = op_handler.modality
                preview_res = op_handler.preview(temp_preview_dir, op_config)
                results.append(preview_res)

                if preview_res.status != "valid":
                    can_apply = False
                if preview_res.warnings:
                    global_warnings.extend(preview_res.warnings)

                # Execute op in sandbox so subsequent ops in chain preview correctly
                if preview_res.status == "valid":
                    try:
                        op_handler.apply(temp_preview_dir, op_config)
                    except Exception as exc:
                        logger.warning(f"Preview simulation step failed for {op_config.operation_type}: {exc}")

            return PreprocessingPreviewResponse(
                dataset_id=req.dataset_id,
                source_version_id=source_version_id,
                operations=results,
                total_operations=len(results),
                warnings=global_warnings,
                can_apply=can_apply,
            )

        finally:
            shutil.rmtree(temp_preview_dir, ignore_errors=True)

    def apply_operations(self, req: PreprocessingApplyRequest) -> PreprocessingApplyResponse:
        """
        Apply preprocessing operations to create a new derived dataset version,
        compute content fingerprint, save history, and trigger re-analysis.
        """
        dataset = dataset_service.get_dataset(req.dataset_id)
        if not dataset:
            raise DatasetNotFoundError(req.dataset_id)

        # Resolve source version
        if req.version_id:
            source_version = dataset_service.get_version(req.dataset_id, req.version_id)
            if not source_version:
                raise VersionNotFoundError(req.dataset_id, req.version_id)
            source_version_id = source_version.version_id
            source_path = self.storage.base_dir / source_version.storage_relative_path
        else:
            latest = dataset_service.get_latest_version(req.dataset_id)
            source_version_id = latest.version_id if latest else "v1"
            source_path = self.storage.resolve_dataset_path(dataset)

        if not source_path.exists():
            raise FileNotFoundError(f"Source dataset path {source_path} does not exist.")
        self._validate_annotation_linked_image_operations(source_path, req.operations)

        input_fingerprint = upload_service.compute_content_fingerprint(source_path)

        # Create isolated temporary directory for applying transformations
        temp_work_dir = self.storage.results_dir / "temp_preprocessing" / uuid.uuid4().hex[:8]
        temp_work_dir.mkdir(parents=True, exist_ok=True)

        event_bus.emit(
            DatasetEventType.DATASET_PREPROCESSING_STARTED,
            dataset_id=req.dataset_id,
            version_id=source_version_id,
            payload={"operations_count": len(req.operations)},
        )

        try:
            # Copy source dataset to work dir
            if source_path.is_dir():
                for item in source_path.iterdir():
                    dest = temp_work_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore_dangling_symlinks=True)
                    else:
                        shutil.copy2(item, dest)
            else:
                shutil.copy2(source_path, temp_work_dir / source_path.name)

            applied_records: List[AppliedOperationRecord] = []
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Execute each operation in order
            for op_config in req.operations:
                op_handler = preprocessing_registry.get_operation(op_config.operation_type)
                if op_config.modality is None:
                    op_config.modality = op_handler.modality
                
                # Validate parameters first
                val_errs = op_handler.validate_parameters(op_config)
                if val_errs:
                    raise PreprocessingValidationError("; ".join(val_errs))

                exec_stats = op_handler.apply(temp_work_dir, op_config)

                record = AppliedOperationRecord(
                    operation_id=op_config.operation_id or f"op-{uuid.uuid4().hex[:6]}",
                    operation_type=op_config.operation_type,
                    modality=op_config.modality,
                    parameters=op_config.parameters,
                    affected_columns=exec_stats.get("affected_columns", []),
                    affected_files=exec_stats.get("affected_files", []),
                    rows_before=exec_stats.get("rows_before"),
                    rows_after=exec_stats.get("rows_after"),
                    files_before=exec_stats.get("files_before"),
                    files_after=exec_stats.get("files_after"),
                    status=OperationStatus.APPLIED,
                    warnings=exec_stats.get("warnings", []),
                    executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
                applied_records.append(record)

            # Compute output fingerprint of derived dataset
            output_fingerprint = upload_service.compute_content_fingerprint(temp_work_dir)

            # Determine derived version number and path
            existing_versions = dataset_service.list_versions(req.dataset_id)
            next_ver_num = len(existing_versions) + 1
            derived_version_id = f"ver-{req.dataset_id}-{next_ver_num}-{output_fingerprint[:8]}"
            version_slug = f"v{next_ver_num}"
            final_derived_dir = self.storage.get_extract_path(req.dataset_id) / version_slug
            final_derived_rel = self.storage.sanitize_relative_path(final_derived_dir)

            # Create new dataset version (respecting deduplication if content unchanged)
            derived_version, is_duplicate = dataset_service.create_version(
                dataset_id=req.dataset_id,
                storage_relative_path=final_derived_rel,
                content_fingerprint=output_fingerprint,
            )

            if is_duplicate:
                shutil.rmtree(temp_work_dir, ignore_errors=True)
                return PreprocessingApplyResponse(
                    dataset_id=req.dataset_id,
                    source_version_id=source_version_id,
                    derived_version_id=derived_version.version_id,
                    version_number=derived_version.version_number,
                    job_id="",
                    status="completed",
                    message="Derived dataset content is identical to an existing version. Existing version reused.",
                    operations_applied=len(applied_records),
                    is_duplicate_content=True,
                )

            # Move temp work dir to final derived version directory
            if final_derived_dir.exists():
                shutil.rmtree(final_derived_dir, ignore_errors=True)
            temp_work_dir.rename(final_derived_dir)

            # Persist preprocessing history record
            history_record = PreprocessingHistoryRecord(
                id=f"hist-{derived_version.version_id}",
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
                req.dataset_id, derived_version.version_id, history_record.model_dump()
            )

            # Trigger asynchronous pipeline re-analysis for derived version
            job = dataset_service.reanalyze_dataset(req.dataset_id, derived_version.version_id)
            history_record.job_id = job.job_id
            self.storage.save_preprocessing_history(
                req.dataset_id, derived_version.version_id, history_record.model_dump()
            )

            event_bus.emit(
                DatasetEventType.DATASET_PREPROCESSING_COMPLETED,
                dataset_id=req.dataset_id,
                version_id=derived_version.version_id,
                job_id=job.job_id,
                payload={"operations_applied": len(applied_records)},
            )

            return PreprocessingApplyResponse(
                dataset_id=req.dataset_id,
                source_version_id=source_version_id,
                derived_version_id=derived_version.version_id,
                version_number=derived_version.version_number,
                job_id=job.job_id,
                status="completed",
                message="Preprocessing operations applied successfully. Derived version and re-analysis pipeline enqueued.",
                operations_applied=len(applied_records),
                is_duplicate_content=False,
            )

        except Exception as exc:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
            logger.error(f"Preprocessing apply failed for dataset {req.dataset_id}: {exc}", exc_info=True)
            event_bus.emit(
                DatasetEventType.DATASET_PREPROCESSING_FAILED,
                dataset_id=req.dataset_id,
                version_id=source_version_id,
                payload={"error": str(exc)},
            )
            raise PreprocessingError(str(exc))

    def get_preprocessing_history(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> PreprocessingHistoryRecord:
        """Retrieve preprocessing history record for a specific dataset version or latest."""
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        data = self.storage.load_preprocessing_history(dataset_id, version_id)
        if not data:
            raise PreprocessingHistoryNotFoundError(dataset_id, version_id)

        return PreprocessingHistoryRecord.model_validate(data)

    def list_preprocessing_history(self, dataset_id: str) -> PreprocessingHistoryListResponse:
        """List all historical preprocessing records for a dataset."""
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        items_data = self.storage.list_persisted_preprocessing_history(dataset_id)
        items = [PreprocessingHistoryRecord.model_validate(d) for d in items_data]
        return PreprocessingHistoryListResponse(total=len(items), items=items)


preprocessing_service = PreprocessingService()
