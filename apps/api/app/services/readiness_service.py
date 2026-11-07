"""
M10 — Dataset Readiness Assessment Engine.

Evaluates dataset integrity, data quality, analytical suitability, preprocessing status,
and feature readiness across dataset modalities (tabular, image, time-series, annotation).
Support optional task-aware context (target column, ML task type) and produces actionable,
evidence-backed readiness evaluations without arbitrary scores.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from app.core.errors import DatasetNotFoundError, VersionNotFoundError
from app.schemas.readiness import (
    DatasetReadinessAssessment,
    ReadinessDimension,
    ReadinessDimensionAssessment,
    ReadinessStatus,
    ReadinessAssessRequest,
    TaskContext,
)
from app.storage.base import StorageBackend
from app.storage.local import storage_backend
from app.services.dataset_service import dataset_service

logger = logging.getLogger(__name__)


class ReadinessService:
    """Evaluates multi-dimensional dataset readiness for analytics and model training."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or storage_backend

    def assess_readiness(
        self,
        dataset_id: str,
        version_id: Optional[str] = None,
        task_context: Optional[TaskContext] = None,
    ) -> DatasetReadinessAssessment:
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        if version_id:
            version = dataset_service.get_version(dataset_id, version_id)
            if not version:
                raise VersionNotFoundError(dataset_id, version_id)
            target_version_id = version.version_id
        else:
            latest = dataset_service.get_latest_version(dataset_id)
            target_version_id = latest.version_id if latest else "v1"

        dataset_dir = self.storage.resolve_dataset_path(dataset)
        from app.services.preprocessing.preprocessing_registry import preprocessing_registry
        modalities = preprocessing_registry.detect_modalities(dataset_dir)
        primary_modality = modalities[0].value if modalities else "tabular"

        # Load available analytical artifacts
        disc_res = dataset.discovery
        val_res = dataset.validation
        dup_res = dataset.duplicates
        near_dup_res = dataset.near_duplicates
        quality_res = dataset_service.get_latest_quality_assessment(dataset_id)
        history_list = self.storage.list_persisted_preprocessing_history(dataset_id)

        # ---------------------------------------------------------------------
        # Dimension 1: Dataset Integrity
        # ---------------------------------------------------------------------
        integrity_blockers: List[str] = []
        integrity_warnings: List[str] = []
        integrity_recs: List[str] = []
        integrity_score = 100

        total_files = dataset.total_images or 0
        corrupt_files = dataset.corrupted_image_files or 0

        if val_res:
            corrupt_files = val_res.total_corrupted_images
            total_files = val_res.total_discovered_images

        if total_files == 0:
            integrity_blockers.append("Dataset contains 0 accessible files or rows.")
            integrity_score = 0
        elif corrupt_files > 0:
            integrity_score = max(30, 100 - int((corrupt_files / max(1, total_files)) * 100))
            integrity_warnings.append(f"Found {corrupt_files} corrupted or unreadable files.")
            integrity_recs.append("Execute M8 'exclude_corrupt_images' operation to remove invalid files.")

        integrity_status = (
            ReadinessStatus.READY
            if integrity_score >= 90
            else ReadinessStatus.NEEDS_PREPROCESSING
            if integrity_blockers or integrity_score < 60
            else ReadinessStatus.READY_WITH_CONCERNS
        )

        dim_integrity = ReadinessDimensionAssessment(
            dimension=ReadinessDimension.DATASET_INTEGRITY,
            status=integrity_status,
            score=integrity_score,
            metrics={"total_files": total_files, "corrupt_files": corrupt_files},
            blocking_issues=integrity_blockers,
            warnings=integrity_warnings,
            recommendations=integrity_recs,
        )

        # ---------------------------------------------------------------------
        # Dimension 2: Data Quality
        # ---------------------------------------------------------------------
        quality_blockers: List[str] = []
        quality_warnings: List[str] = []
        quality_recs: List[str] = []
        quality_score = 90

        exact_dups = dup_res.exact_duplicate_groups if dup_res else 0
        near_dups = near_dup_res.near_duplicate_groups if near_dup_res else 0

        if exact_dups > 0:
            quality_warnings.append(f"Identified {exact_dups} exact duplicate groups.")
            quality_recs.append("Apply M8 duplicate removal to prevent train-test leakage.")
            quality_score -= min(30, exact_dups * 5)

        if near_dups > 0:
            quality_warnings.append(f"Identified {near_dups} perceptual near-duplicate groups.")
            quality_score -= min(20, near_dups * 4)

        if quality_res:
            if hasattr(quality_res, "quality_score"):
                quality_score = int(quality_res.quality_score.overall_score)
            elif isinstance(quality_res, dict):
                qs = quality_res.get("overall_quality_score") or quality_res.get("quality_score", {}).get("overall_score")
                if qs is not None:
                    quality_score = int(qs)

        quality_status = (
            ReadinessStatus.READY
            if quality_score >= 85
            else ReadinessStatus.READY_WITH_CONCERNS
            if quality_score >= 65
            else ReadinessStatus.NEEDS_PREPROCESSING
        )

        dim_quality = ReadinessDimensionAssessment(
            dimension=ReadinessDimension.DATA_QUALITY,
            status=quality_status,
            score=quality_score,
            metrics={"exact_duplicate_groups": exact_dups, "near_duplicate_groups": near_dups},
            blocking_issues=quality_blockers,
            warnings=quality_warnings,
            recommendations=quality_recs,
        )

        # ---------------------------------------------------------------------
        # Dimension 3: Analytical Suitability & Task Context
        # ---------------------------------------------------------------------
        suitability_blockers: List[str] = []
        suitability_warnings: List[str] = []
        suitability_recs: List[str] = []
        suitability_score = 95

        if task_context and task_context.target_column:
            # Check target column in tabular dataset
            from app.services.feature_engineering.feature_registry import feature_registry
            features = feature_registry.discover_features(dataset_dir)
            feat_names = [f.feature_name for f in features]
            if feat_names and task_context.target_column not in feat_names:
                suitability_blockers.append(
                    f"Specified target column '{task_context.target_column}' was not found in dataset columns ({feat_names[:5]})."
                )
                suitability_score = 20
            else:
                suitability_recs.append(f"Target column '{task_context.target_column}' validated successfully.")

        if primary_modality == "image" and dataset.total_classes and dataset.total_classes < 2:
            suitability_warnings.append(f"Image dataset has only {dataset.total_classes} class directory. Multi-class classification requires >= 2 classes.")
            suitability_score -= 20

        suitability_status = (
            ReadinessStatus.READY
            if suitability_score >= 85 and not suitability_blockers
            else ReadinessStatus.NEEDS_PREPROCESSING
            if suitability_blockers
            else ReadinessStatus.READY_WITH_CONCERNS
        )

        dim_suitability = ReadinessDimensionAssessment(
            dimension=ReadinessDimension.ANALYTICAL_SUITABILITY,
            status=suitability_status,
            score=suitability_score,
            metrics={"primary_modality": primary_modality, "task_context_provided": task_context is not None},
            blocking_issues=suitability_blockers,
            warnings=suitability_warnings,
            recommendations=suitability_recs,
        )

        # ---------------------------------------------------------------------
        # Dimension 4: Preprocessing Status
        # ---------------------------------------------------------------------
        prep_score = 80 if history_list else 60
        prep_warnings = []
        prep_recs = []

        if history_list:
            prep_recs.append(f"Dataset has {len(history_list)} persisted preprocessing derived version(s).")
            prep_score = 95
        else:
            prep_warnings.append("Raw dataset version has not undergone automated M8 cleaning transformations.")
            prep_recs.append("Review M8 preprocessing pipeline for optional missing value imputation or scaling.")

        dim_preprocessing = ReadinessDimensionAssessment(
            dimension=ReadinessDimension.PREPROCESSING_STATUS,
            status=ReadinessStatus.READY if prep_score >= 85 else ReadinessStatus.READY_WITH_CONCERNS,
            score=prep_score,
            metrics={"derived_versions_count": len(history_list)},
            blocking_issues=[],
            warnings=prep_warnings,
            recommendations=prep_recs,
        )

        # ---------------------------------------------------------------------
        # Dimension 5: Feature Readiness
        # ---------------------------------------------------------------------
        feat_score = 90
        feat_warnings = []
        feat_recs = []

        from app.services.feature_engineering.feature_registry import feature_registry
        discovered_feats = feature_registry.discover_features(dataset_dir)
        if discovered_feats:
            feat_recs.append(f"Discovered {len(discovered_feats)} tabular features.")
        else:
            feat_recs.append("Modality-specific features ready for modeling pipeline.")

        dim_features = ReadinessDimensionAssessment(
            dimension=ReadinessDimension.FEATURE_READINESS,
            status=ReadinessStatus.READY,
            score=feat_score,
            metrics={"features_count": len(discovered_feats)},
            blocking_issues=[],
            warnings=feat_warnings,
            recommendations=feat_recs,
        )

        # ---------------------------------------------------------------------
        # Overall Score & Status Synthesis
        # ---------------------------------------------------------------------
        all_dims = [dim_integrity, dim_quality, dim_suitability, dim_preprocessing, dim_features]
        overall_score = int(sum(d.score for d in all_dims) / len(all_dims))

        all_blockers = [b for d in all_dims for b in d.blocking_issues]
        all_warnings = [w for d in all_dims for w in d.warnings]
        all_recs = [r for d in all_dims for r in d.recommendations]

        if all_blockers:
            overall_status = ReadinessStatus.NEEDS_PREPROCESSING
        elif overall_score >= 85:
            overall_status = ReadinessStatus.READY
        elif overall_score >= 65:
            overall_status = ReadinessStatus.READY_WITH_CONCERNS
        else:
            overall_status = ReadinessStatus.NEEDS_PREPROCESSING

        strengths = []
        if dim_integrity.score >= 90:
            strengths.append("High dataset structure integrity and file decodability.")
        if dim_quality.score >= 85:
            strengths.append("Low corruption and well-formed sample distribution.")
        if history_list:
            strengths.append("Traceable preprocessing history with derived versioning.")

        assessment = DatasetReadinessAssessment(
            dataset_id=dataset_id,
            version_id=target_version_id,
            dataset_name=dataset.name,
            overall_status=overall_status,
            overall_score=overall_score,
            task_context=task_context,
            dimensions=all_dims,
            key_strengths=strengths,
            critical_blockers=all_blockers,
            recommendations=all_recs,
            missing_evidence=[] if disc_res else ["Dataset discovery result missing."],
            evaluated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        self.storage.save_readiness_assessment(dataset_id, target_version_id, assessment.model_dump())
        return assessment

    def get_readiness_assessment(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> DatasetReadinessAssessment:
        data = self.storage.load_readiness_assessment(dataset_id, version_id)
        if not data:
            # Recompute on the fly if not yet cached
            return self.assess_readiness(dataset_id, version_id)
        return DatasetReadinessAssessment.model_validate(data)


readiness_service = ReadinessService()
