"""
M5 — Dataset Comparison Service.

Produces deterministic pairwise comparison reports between two datasets by consuming
persisted M2 (unified analysis), M3 (quality assessment), and M4 (EDA) reports.
Never re-runs upstream pipelines and never trains models.
"""
from __future__ import annotations

import datetime
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.errors import (
    ComparisonNotFoundError,
    ComparisonPrerequisiteError,
    DatasetNotFoundError,
    SelfComparisonError,
)
from app.schemas.comparison import (
    ClassAlignmentSummary,
    ClassDistributionComparison,
    ComparisonFinding,
    ComparisonFindingCategory,
    ComparisonFreshness,
    ComparisonFreshnessResponse,
    ComparisonSeverity,
    ComparisonSourceRefs,
    ComparisonStatus,
    ComparisonStatusResponse,
    DataQualityComparison,
    DatasetComparisonListResponse,
    DatasetComparisonReport,
    DatasetComparisonSummary,
    DatasetOverviewComparison,
    ImageCharacteristicsComparison,
    MetricComparison,
    SharedClassComparison,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.storage.base import StorageBackend
from app.storage.local import get_storage_backend

logger = logging.getLogger(__name__)


class ComparisonService:
    """Service orchestrating pairwise dataset comparisons."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or get_storage_backend()
        self._comparisons: Dict[str, DatasetComparisonReport] = {}
        self._rehydrate_from_storage()

    def _rehydrate_from_storage(self) -> None:
        """Load all previously persisted comparison reports from disk into memory."""
        try:
            persisted = self.storage.list_persisted_comparisons()
            for record in persisted:
                try:
                    report = DatasetComparisonReport.model_validate(record)
                    self._comparisons[report.id] = report
                except Exception as exc:
                    logger.warning(
                        f"Failed to rehydrate comparison report {record.get('id')}: {exc}"
                    )
            logger.info(
                f"Rehydrated {len(self._comparisons)} comparison reports from storage."
            )
        except Exception as exc:
            logger.error(f"Error during comparison rehydration: {exc}")

    # -------------------------------------------------------------------------
    # Core Comparison Execution
    # -------------------------------------------------------------------------

    def run_comparison(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        force_refresh: bool = False,
    ) -> DatasetComparisonReport:
        """
        Compare two datasets side-by-side using their latest upstream artifacts.
        """
        if dataset_a_id == dataset_b_id:
            raise SelfComparisonError()

        # Local imports to prevent circular dependencies
        from app.services.dataset_service import dataset_service
        from app.services.analysis_service import analysis_service
        from app.services.data_quality_service import data_quality_service
        from app.services.eda_service import eda_service

        # 1. Validate both datasets exist
        ds_a = dataset_service.get_dataset(dataset_a_id)
        if not ds_a:
            raise DatasetNotFoundError(dataset_a_id)

        ds_b = dataset_service.get_dataset(dataset_b_id)
        if not ds_b:
            raise DatasetNotFoundError(dataset_b_id)

        # 2. Check cache if force_refresh is False
        if not force_refresh:
            latest_id = self.storage.get_latest_comparison_id_for_pair(
                dataset_a_id, dataset_b_id
            )
            if latest_id and latest_id in self._comparisons:
                cached = self._comparisons[latest_id]
                # Match direction
                if (
                    cached.dataset_a_id == dataset_a_id
                    and cached.dataset_b_id == dataset_b_id
                    and cached.status == ComparisonStatus.COMPLETED
                    and cached.freshness_status != ComparisonFreshness.STALE
                ):
                    # Verify upstream analyses haven't changed
                    ana_a_check = analysis_service.get_latest_analysis_for_dataset(dataset_a_id)
                    ana_b_check = analysis_service.get_latest_analysis_for_dataset(dataset_b_id)
                    if (
                        ana_a_check
                        and ana_b_check
                        and cached.source_refs.analysis_a_id == ana_a_check.id
                        and cached.source_refs.analysis_b_id == ana_b_check.id
                    ):
                        logger.info(
                            f"Returning cached comparison {cached.id} for pair {dataset_a_id} vs {dataset_b_id}"
                        )
                        return cached
                    else:
                        cached.freshness_status = ComparisonFreshness.STALE

        # 3. Load M2 analyses (mandatory prerequisite)
        analysis_a = analysis_service.get_latest_analysis_for_dataset(dataset_a_id)
        if not analysis_a:
            raise ComparisonPrerequisiteError(
                dataset_a_id,
                "No completed M2 unified analysis found. Run dataset analysis first.",
            )

        analysis_b = analysis_service.get_latest_analysis_for_dataset(dataset_b_id)
        if not analysis_b:
            raise ComparisonPrerequisiteError(
                dataset_b_id,
                "No completed M2 unified analysis found. Run dataset analysis first.",
            )

        # 4. Load M3 quality assessments (optional)
        quality_a = data_quality_service.get_latest_assessment_for_dataset(dataset_a_id)
        quality_b = data_quality_service.get_latest_assessment_for_dataset(dataset_b_id)

        # 5. Load M4 EDA reports (optional)
        eda_a = eda_service.get_latest_report_for_dataset(dataset_a_id)
        eda_b = eda_service.get_latest_report_for_dataset(dataset_b_id)

        # 6. Prepare comparison metadata
        pair_slug = f"{min(dataset_a_id, dataset_b_id)}-vs-{max(dataset_a_id, dataset_b_id)}"
        comparison_id = f"cmp-{pair_slug}-{uuid.uuid4().hex[:10]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        start_time = time.perf_counter()

        warnings: List[str] = []
        if not quality_a or not quality_b:
            missing_qual = []
            if not quality_a:
                missing_qual.append(dataset_a_id)
            if not quality_b:
                missing_qual.append(dataset_b_id)
            warnings.append(
                f"Data quality assessment unavailable for: {', '.join(missing_qual)}. Quality score comparison is partial or omitted."
            )

        if not eda_a or not eda_b:
            missing_eda = []
            if not eda_a:
                missing_eda.append(dataset_a_id)
            if not eda_b:
                missing_eda.append(dataset_b_id)
            warnings.append(
                f"EDA report unavailable for: {', '.join(missing_eda)}. Statistical distribution metrics are partial or omitted."
            )

        source_refs = ComparisonSourceRefs(
            analysis_a_id=analysis_a.id,
            analysis_b_id=analysis_b.id,
            quality_a_id=quality_a.id if quality_a else None,
            quality_b_id=quality_b.id if quality_b else None,
            eda_a_id=eda_a.id if eda_a else None,
            eda_b_id=eda_b.id if eda_b else None,
        )

        # 7. Compute comparison dimensions
        overview = self._compare_overview(analysis_a, analysis_b)
        class_distribution = self._compare_class_distribution(
            analysis_a, analysis_b, eda_a, eda_b
        )
        image_characteristics = self._compare_image_characteristics(
            analysis_a, analysis_b, eda_a, eda_b
        )
        data_quality = self._compare_data_quality(
            analysis_a, analysis_b, quality_a, quality_b
        )

        # 8. Generate findings
        findings = self._generate_findings(
            overview=overview,
            class_dist=class_distribution,
            img_chars=image_characteristics,
            data_quality=data_quality,
            analysis_a=analysis_a,
            analysis_b=analysis_b,
            quality_a=quality_a,
            quality_b=quality_b,
            eda_a=eda_a,
            eda_b=eda_b,
        )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        report = DatasetComparisonReport(
            id=comparison_id,
            dataset_a_id=dataset_a_id,
            dataset_b_id=dataset_b_id,
            dataset_a_name=ds_a.name if hasattr(ds_a, "name") else dataset_a_id,
            dataset_b_name=ds_b.name if hasattr(ds_b, "name") else dataset_b_id,
            status=ComparisonStatus.COMPLETED,
            freshness_status=ComparisonFreshness.CURRENT,
            source_version_a=getattr(ds_a, "current_version_id", None),
            source_version_b=getattr(ds_b, "current_version_id", None),
            created_at=created_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            methodology_version="v1.0",
            source_refs=source_refs,
            overview=overview,
            class_distribution=class_distribution,
            image_characteristics=image_characteristics,
            data_quality=data_quality,
            findings=findings,
            warnings=warnings,
        )

        # 9. Persist and cache
        try:
            self.storage.save_comparison(
                comparison_id=comparison_id,
                data=report.model_dump(),
                dataset_a_id=dataset_a_id,
                dataset_b_id=dataset_b_id,
            )
        except Exception as exc:
            logger.error(f"Failed to persist comparison report {comparison_id}: {exc}")

        self._comparisons[comparison_id] = report
        return report

    # -------------------------------------------------------------------------
    # Helper: Metric Comparison Primitive
    # -------------------------------------------------------------------------

    @staticmethod
    def _make_metric_comparison(
        val_a: Optional[float], val_b: Optional[float]
    ) -> MetricComparison:
        """Create a side-by-side MetricComparison with zero-denominator safety."""
        if val_a is None or val_b is None:
            return MetricComparison(
                dataset_a_value=val_a,
                dataset_b_value=val_b,
                absolute_diff=None,
                pct_change=None,
                is_available=(val_a is not None or val_b is not None),
            )

        abs_diff = round(val_b - val_a, 4)
        pct_change = None
        if val_a != 0:
            pct_change = round(((val_b - val_a) / abs(val_a)) * 100.0, 2)

        return MetricComparison(
            dataset_a_value=val_a,
            dataset_b_value=val_b,
            absolute_diff=abs_diff,
            pct_change=pct_change,
            is_available=True,
        )

    # -------------------------------------------------------------------------
    # Comparison Dimensions
    # -------------------------------------------------------------------------

    def _compare_overview(
        self, analysis_a: Any, analysis_b: Any
    ) -> DatasetOverviewComparison:
        """Compare high-level size and class structure."""
        ma = analysis_a.metrics
        mb = analysis_b.metrics

        tot_img_a = (
            float(ma.total_files_discovered)
            if ma and ma.total_files_discovered is not None
            else None
        )
        tot_img_b = (
            float(mb.total_files_discovered)
            if mb and mb.total_files_discovered is not None
            else None
        )

        val_img_a = (
            float(ma.total_validated_images)
            if ma and ma.total_validated_images is not None
            else None
        )
        val_img_b = (
            float(mb.total_validated_images)
            if mb and mb.total_validated_images is not None
            else None
        )

        cor_img_a = (
            float(ma.total_corrupted_images)
            if ma and ma.total_corrupted_images is not None
            else None
        )
        cor_img_b = (
            float(mb.total_corrupted_images)
            if mb and mb.total_corrupted_images is not None
            else None
        )

        classes_a = analysis_a.discovery.classes if analysis_a.discovery else []
        classes_b = analysis_b.discovery.classes if analysis_b.discovery else []

        tot_cls_a = float(len(classes_a)) if classes_a is not None else None
        tot_cls_b = float(len(classes_b)) if classes_b is not None else None

        ipc_a = (
            round(val_img_a / tot_cls_a, 2)
            if val_img_a is not None and tot_cls_a and tot_cls_a > 0
            else None
        )
        ipc_b = (
            round(val_img_b / tot_cls_b, 2)
            if val_img_b is not None and tot_cls_b and tot_cls_b > 0
            else None
        )

        dup_pct_a = (
            float(ma.exact_duplicate_percentage)
            if ma and ma.exact_duplicate_percentage is not None
            else None
        )
        dup_pct_b = (
            float(mb.exact_duplicate_percentage)
            if mb and mb.exact_duplicate_percentage is not None
            else None
        )

        ndup_pct_a = (
            float(ma.near_duplicate_percentage)
            if ma and ma.near_duplicate_percentage is not None
            else None
        )
        ndup_pct_b = (
            float(mb.near_duplicate_percentage)
            if mb and mb.near_duplicate_percentage is not None
            else None
        )

        return DatasetOverviewComparison(
            total_images=self._make_metric_comparison(tot_img_a, tot_img_b),
            valid_images=self._make_metric_comparison(val_img_a, val_img_b),
            corrupted_images=self._make_metric_comparison(cor_img_a, cor_img_b),
            total_classes=self._make_metric_comparison(tot_cls_a, tot_cls_b),
            images_per_class_mean=self._make_metric_comparison(ipc_a, ipc_b),
            exact_duplicate_pct=self._make_metric_comparison(dup_pct_a, dup_pct_b),
            near_duplicate_pct=self._make_metric_comparison(ndup_pct_a, ndup_pct_b),
        )

    def _compare_class_distribution(
        self,
        analysis_a: Any,
        analysis_b: Any,
        eda_a: Optional[Any],
        eda_b: Optional[Any],
    ) -> ClassDistributionComparison:
        """Compare class namespaces and frequency distributions."""
        classes_a_list = analysis_a.discovery.classes if analysis_a.discovery else []
        classes_b_list = analysis_b.discovery.classes if analysis_b.discovery else []

        counts_a = {c.class_name: c.image_count for c in classes_a_list}
        counts_b = {c.class_name: c.image_count for c in classes_b_list}

        set_a = set(counts_a.keys())
        set_b = set(counts_b.keys())

        shared = sorted(list(set_a.intersection(set_b)))
        only_a = sorted(list(set_a - set_b))
        only_b = sorted(list(set_b - set_a))
        union = set_a.union(set_b)

        overlap_pct = (
            round((len(shared) / len(union)) * 100.0, 2) if len(union) > 0 else None
        )

        shared_comparisons: List[SharedClassComparison] = []
        for cname in shared:
            ca = counts_a[cname]
            cb = counts_b[cname]
            diff = cb - ca
            pct = round((diff / ca) * 100.0, 2) if ca != 0 else None
            shared_comparisons.append(
                SharedClassComparison(
                    class_name=cname,
                    count_a=ca,
                    count_b=cb,
                    absolute_diff=diff,
                    pct_change=pct,
                )
            )

        empty_a = sum(1 for c, cnt in counts_a.items() if cnt == 0)
        empty_b = sum(1 for c, cnt in counts_b.items() if cnt == 0)

        alignment = ClassAlignmentSummary(
            total_classes_a=len(set_a),
            total_classes_b=len(set_b),
            shared_classes=shared,
            only_in_a=only_a,
            only_in_b=only_b,
            shared_class_comparisons=shared_comparisons,
            class_overlap_pct=overlap_pct,
            empty_classes_a=empty_a,
            empty_classes_b=empty_b,
        )

        # EDA-derived statistics
        c_eda_a = eda_a.class_distribution if eda_a else None
        c_eda_b = eda_b.class_distribution if eda_b else None

        ent_a = float(c_eda_a.entropy) if c_eda_a and c_eda_a.entropy is not None else None
        ent_b = float(c_eda_b.entropy) if c_eda_b and c_eda_b.entropy is not None else None

        gini_a = (
            float(c_eda_a.gini_coefficient)
            if c_eda_a and c_eda_a.gini_coefficient is not None
            else None
        )
        gini_b = (
            float(c_eda_b.gini_coefficient)
            if c_eda_b and c_eda_b.gini_coefficient is not None
            else None
        )

        imb_a = (
            float(c_eda_a.imbalance_ratio)
            if c_eda_a and c_eda_a.imbalance_ratio is not None
            else None
        )
        imb_b = (
            float(c_eda_b.imbalance_ratio)
            if c_eda_b and c_eda_b.imbalance_ratio is not None
            else None
        )

        cv_a = (
            float(c_eda_a.coefficient_of_variation)
            if c_eda_a and c_eda_a.coefficient_of_variation is not None
            else None
        )
        cv_b = (
            float(c_eda_b.coefficient_of_variation)
            if c_eda_b and c_eda_b.coefficient_of_variation is not None
            else None
        )

        nent_a = (
            float(c_eda_a.normalized_entropy)
            if c_eda_a and c_eda_a.normalized_entropy is not None
            else None
        )
        nent_b = (
            float(c_eda_b.normalized_entropy)
            if c_eda_b and c_eda_b.normalized_entropy is not None
            else None
        )

        has_eda = (c_eda_a is not None) and (c_eda_b is not None)
        fallback = None if has_eda else "EDA report missing for one or both datasets; statistical distribution metrics are partial or unavailable."

        return ClassDistributionComparison(
            alignment=alignment,
            entropy_a=self._make_metric_comparison(ent_a, ent_b),
            entropy_b=self._make_metric_comparison(ent_a, ent_b),
            gini_coefficient=self._make_metric_comparison(gini_a, gini_b),
            imbalance_ratio=self._make_metric_comparison(imb_a, imb_b),
            coefficient_of_variation=self._make_metric_comparison(cv_a, cv_b),
            normalized_entropy=self._make_metric_comparison(nent_a, nent_b),
            is_available=has_eda,
            fallback_note=fallback,
        )

    def _compare_image_characteristics(
        self,
        analysis_a: Any,
        analysis_b: Any,
        eda_a: Optional[Any],
        eda_b: Optional[Any],
    ) -> ImageCharacteristicsComparison:
        """Compare dimensions, aspect ratios, file sizes, formats, and color modes."""
        dim_a = eda_a.dimension_analysis if eda_a else None
        dim_b = eda_b.dimension_analysis if eda_b else None

        ar_a = eda_a.aspect_ratio_analysis if eda_a else None
        ar_b = eda_b.aspect_ratio_analysis if eda_b else None

        fs_a = eda_a.file_size_analysis if eda_a else None
        fs_b = eda_b.file_size_analysis if eda_b else None

        med_w_a = float(dim_a.median_width) if dim_a and dim_a.median_width is not None else None
        med_w_b = float(dim_b.median_width) if dim_b and dim_b.median_width is not None else None

        med_h_a = (
            float(dim_a.median_height) if dim_a and dim_a.median_height is not None else None
        )
        med_h_b = (
            float(dim_b.median_height) if dim_b and dim_b.median_height is not None else None
        )

        mean_ar_a = (
            float(ar_a.mean_ar)
            if ar_a and getattr(ar_a, "mean_ar", None) is not None
            else None
        )
        mean_ar_b = (
            float(ar_b.mean_ar)
            if ar_b and getattr(ar_b, "mean_ar", None) is not None
            else None
        )

        med_fs_a = (
            float(fs_a.median_bytes) if fs_a and fs_a.median_bytes is not None else None
        )
        med_fs_b = (
            float(fs_b.median_bytes) if fs_b and fs_b.median_bytes is not None else None
        )

        mean_fs_a = (
            float(fs_a.mean_bytes) if fs_a and fs_a.mean_bytes is not None else None
        )
        mean_fs_b = (
            float(fs_b.mean_bytes) if fs_b and fs_b.mean_bytes is not None else None
        )

        # Dominant color mode & format
        dom_color_a = None
        if eda_a and eda_a.color_analysis and eda_a.color_analysis.color_mode_distribution:
            dom_color_a = max(eda_a.color_analysis.color_mode_distribution.items(), key=lambda kv: kv[1])[0]
        dom_color_b = None
        if eda_b and eda_b.color_analysis and eda_b.color_analysis.color_mode_distribution:
            dom_color_b = max(eda_b.color_analysis.color_mode_distribution.items(), key=lambda kv: kv[1])[0]

        dom_fmt_a = (
            getattr(eda_a.format_analysis, "most_common_format", None)
            if eda_a and eda_a.format_analysis
            else None
        )
        dom_fmt_b = (
            getattr(eda_b.format_analysis, "most_common_format", None)
            if eda_b and eda_b.format_analysis
            else None
        )

        # Fallback to M2 validation if EDA is missing
        if not dom_color_a and analysis_a.validation:
            c_dist = getattr(analysis_a.validation, "color_mode_distribution", {})
            if c_dist:
                dom_color_a = max(c_dist.items(), key=lambda kv: kv[1])[0]
        if not dom_color_b and analysis_b.validation:
            c_dist = getattr(analysis_b.validation, "color_mode_distribution", {})
            if c_dist:
                dom_color_b = max(c_dist.items(), key=lambda kv: kv[1])[0]

        if not dom_fmt_a and analysis_a.validation:
            f_dist = getattr(analysis_a.validation, "format_distribution", {})
            if f_dist:
                dom_fmt_a = max(f_dist.items(), key=lambda kv: kv[1])[0]
        if not dom_fmt_b and analysis_b.validation:
            f_dist = getattr(analysis_b.validation, "format_distribution", {})
            if f_dist:
                dom_fmt_b = max(f_dist.items(), key=lambda kv: kv[1])[0]

        has_eda = (dim_a is not None) and (dim_b is not None)
        fallback = None if has_eda else "EDA report missing for one or both datasets; dimension and file size statistics are partial or unavailable."

        return ImageCharacteristicsComparison(
            median_width=self._make_metric_comparison(med_w_a, med_w_b),
            median_height=self._make_metric_comparison(med_h_a, med_h_b),
            mean_aspect_ratio=self._make_metric_comparison(mean_ar_a, mean_ar_b),
            median_file_size_bytes=self._make_metric_comparison(med_fs_a, med_fs_b),
            mean_file_size_bytes=self._make_metric_comparison(mean_fs_a, mean_fs_b),
            dominant_color_mode_a=dom_color_a,
            dominant_color_mode_b=dom_color_b,
            dominant_format_a=dom_fmt_a,
            dominant_format_b=dom_fmt_b,
            is_available=has_eda,
            fallback_note=fallback,
        )

    def _compare_data_quality(
        self,
        analysis_a: Any,
        analysis_b: Any,
        quality_a: Optional[Any],
        quality_b: Optional[Any],
    ) -> DataQualityComparison:
        """Compare duplicate metrics (M2) and quality assessment scores (M3)."""
        ma = analysis_a.metrics
        mb = analysis_b.metrics

        edup_grp_a = (
            float(ma.exact_duplicate_groups)
            if ma and ma.exact_duplicate_groups is not None
            else None
        )
        edup_grp_b = (
            float(mb.exact_duplicate_groups)
            if mb and mb.exact_duplicate_groups is not None
            else None
        )

        ndup_grp_a = (
            float(ma.near_duplicate_groups)
            if ma and ma.near_duplicate_groups is not None
            else None
        )
        ndup_grp_b = (
            float(mb.near_duplicate_groups)
            if mb and mb.near_duplicate_groups is not None
            else None
        )

        red_img_a = (
            float(ma.total_redundant_images)
            if ma and ma.total_redundant_images is not None
            else None
        )
        red_img_b = (
            float(mb.total_redundant_images)
            if mb and mb.total_redundant_images is not None
            else None
        )

        clean_img_a = (
            float(ma.clean_unique_images)
            if ma and ma.clean_unique_images is not None
            else None
        )
        clean_img_b = (
            float(mb.clean_unique_images)
            if mb and mb.clean_unique_images is not None
            else None
        )

        # M3 metrics
        qs_a = quality_a.quality_score if quality_a else None
        qs_b = quality_b.quality_score if quality_b else None

        score_a = float(qs_a.overall_score) if qs_a and qs_a.overall_score is not None else None
        score_b = float(qs_b.overall_score) if qs_b and qs_b.overall_score is not None else None

        tier_a = str(qs_a.quality_tier) if qs_a and qs_a.quality_tier else None
        tier_b = str(qs_b.quality_tier) if qs_b and qs_b.quality_tier else None

        integ_a = (
            float(quality_a.integrity.integrity_rate)
            if quality_a and quality_a.integrity and quality_a.integrity.integrity_rate is not None
            else None
        )
        integ_b = (
            float(quality_b.integrity.integrity_rate)
            if quality_b and quality_b.integrity and quality_b.integrity.integrity_rate is not None
            else None
        )

        crit_a = None
        if quality_a and quality_a.findings is not None:
            crit_a = float(sum(1 for f in quality_a.findings if str(getattr(f, "severity", "")).lower() == "critical"))
        crit_b = None
        if quality_b and quality_b.findings is not None:
            crit_b = float(sum(1 for f in quality_b.findings if str(getattr(f, "severity", "")).lower() == "critical"))

        is_qual_avail = (quality_a is not None) or (quality_b is not None)
        fallback = None if (quality_a and quality_b) else "M3 quality assessment missing for one or both datasets; score comparison is partial or unavailable."

        return DataQualityComparison(
            exact_duplicate_groups=self._make_metric_comparison(edup_grp_a, edup_grp_b),
            near_duplicate_groups=self._make_metric_comparison(ndup_grp_a, ndup_grp_b),
            total_redundant_images=self._make_metric_comparison(red_img_a, red_img_b),
            clean_unique_images=self._make_metric_comparison(clean_img_a, clean_img_b),
            overall_quality_score=self._make_metric_comparison(score_a, score_b),
            integrity_rate=self._make_metric_comparison(integ_a, integ_b),
            quality_tier_a=tier_a,
            quality_tier_b=tier_b,
            critical_findings_count=self._make_metric_comparison(crit_a, crit_b),
            is_quality_available=is_qual_avail,
            is_duplicate_available=True,
            fallback_note=fallback,
        )

    # -------------------------------------------------------------------------
    # Findings Generation
    # -------------------------------------------------------------------------

    def _generate_findings(
        self,
        overview: DatasetOverviewComparison,
        class_dist: ClassDistributionComparison,
        img_chars: ImageCharacteristicsComparison,
        data_quality: DataQualityComparison,
        analysis_a: Any,
        analysis_b: Any,
        quality_a: Optional[Any],
        quality_b: Optional[Any],
        eda_a: Optional[Any],
        eda_b: Optional[Any],
    ) -> List[ComparisonFinding]:
        """Generate deterministic, evidence-backed comparison findings."""
        findings: List[ComparisonFinding] = []

        # 1. Scale differences
        val_img = overview.valid_images
        if val_img.pct_change is not None:
            if abs(val_img.pct_change) > 50.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-size-difference",
                        category=ComparisonFindingCategory.SCALE,
                        severity=ComparisonSeverity.LOW,
                        title="Significant Dataset Scale Disparity",
                        explanation=(
                            f"Dataset B valid image count ({val_img.dataset_b_value:g}) differs by "
                            f"{val_img.pct_change:+.1f}% relative to Dataset A ({val_img.dataset_a_value:g})."
                        ),
                        metric_name="valid_images",
                        value_a=val_img.dataset_a_value,
                        value_b=val_img.dataset_b_value,
                        absolute_diff=val_img.absolute_diff,
                        pct_change=val_img.pct_change,
                        threshold_used=50.0,
                        recommended_action="Account for sample volume disparities when conducting comparative modeling or data aggregation.",
                        evidence_references=["overview.valid_images"],
                    )
                )

        if val_img.dataset_a_value and val_img.dataset_b_value and val_img.dataset_a_value > 0:
            ratio = val_img.dataset_b_value / val_img.dataset_a_value
            if ratio >= 10.0 or ratio <= 0.1:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-size-large-gap",
                        category=ComparisonFindingCategory.SCALE,
                        severity=ComparisonSeverity.MEDIUM,
                        title="Extreme Scale Imbalance (>10x Difference)",
                        explanation=(
                            f"One dataset is an order of magnitude larger than the other "
                            f"({val_img.dataset_a_value:g} vs {val_img.dataset_b_value:g} images)."
                        ),
                        metric_name="valid_images",
                        value_a=val_img.dataset_a_value,
                        value_b=val_img.dataset_b_value,
                        absolute_diff=val_img.absolute_diff,
                        pct_change=val_img.pct_change,
                        threshold_used=10.0,
                        recommended_action="Downsample larger dataset or augment smaller dataset prior to joint training.",
                        evidence_references=["overview.valid_images"],
                    )
                )

        # 2. Class alignment
        align = class_dist.alignment
        if align.class_overlap_pct is not None:
            if align.class_overlap_pct == 0.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-no-shared-classes",
                        category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                        severity=ComparisonSeverity.INFO,
                        title="Disjoint Class Namespaces (Zero Overlap)",
                        explanation="The two datasets share zero class labels. Their class taxonomies are entirely disjoint.",
                        metric_name="class_overlap_pct",
                        value_a=float(align.total_classes_a),
                        value_b=float(align.total_classes_b),
                        absolute_diff=float(align.total_classes_b - align.total_classes_a),
                        pct_change=None,
                        threshold_used=0.0,
                        recommended_action="Verify class labeling taxonomy and mapping dictionaries before attempting any cross-dataset tasks.",
                        evidence_references=["class_distribution.alignment.class_overlap_pct"],
                    )
                )
            elif align.class_overlap_pct < 50.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-low-class-overlap",
                        category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                        severity=ComparisonSeverity.INFO,
                        title="Low Class Taxonomy Overlap (<50%)",
                        explanation=(
                            f"Only {len(align.shared_classes)} classes are shared between the datasets, "
                            f"yielding a {align.class_overlap_pct:.1f}% Jaccard overlap."
                        ),
                        metric_name="class_overlap_pct",
                        value_a=float(align.total_classes_a),
                        value_b=float(align.total_classes_b),
                        absolute_diff=float(align.total_classes_b - align.total_classes_a),
                        pct_change=None,
                        threshold_used=50.0,
                        recommended_action="Review unmatched classes to ensure labeling nomenclature is harmonized.",
                        evidence_references=["class_distribution.alignment.class_overlap_pct"],
                    )
                )

        if len(align.only_in_a) > 0:
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-classes-only-in-a",
                    category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                    severity=ComparisonSeverity.INFO,
                    title="Classes Exclusive to Dataset A",
                    explanation=f"Dataset A contains {len(align.only_in_a)} classes not present in Dataset B: {', '.join(align.only_in_a[:5])}{'...' if len(align.only_in_a) > 5 else ''}.",
                    metric_name="only_in_a_count",
                    value_a=float(len(align.only_in_a)),
                    value_b=0.0,
                    absolute_diff=-float(len(align.only_in_a)),
                    pct_change=None,
                    threshold_used=1.0,
                    recommended_action="Ensure domain coverage expectations align with the excluded classes.",
                    evidence_references=["class_distribution.alignment.only_in_a"],
                )
            )

        if len(align.only_in_b) > 0:
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-classes-only-in-b",
                    category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                    severity=ComparisonSeverity.INFO,
                    title="Classes Exclusive to Dataset B",
                    explanation=f"Dataset B contains {len(align.only_in_b)} classes not present in Dataset A: {', '.join(align.only_in_b[:5])}{'...' if len(align.only_in_b) > 5 else ''}.",
                    metric_name="only_in_b_count",
                    value_a=0.0,
                    value_b=float(len(align.only_in_b)),
                    absolute_diff=float(len(align.only_in_b)),
                    pct_change=None,
                    threshold_used=1.0,
                    recommended_action="Ensure downstream systems are prepared for the novel classes in Dataset B.",
                    evidence_references=["class_distribution.alignment.only_in_b"],
                )
            )

        # 3. Class distribution entropy / gini / imbalance
        if class_dist.entropy_a.absolute_diff is not None:
            if abs(class_dist.entropy_a.absolute_diff) > 1.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-entropy-difference",
                        category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                        severity=ComparisonSeverity.LOW,
                        title="Noticeable Class Distribution Entropy Difference",
                        explanation=(
                            f"Shannon entropy differs by {class_dist.entropy_a.absolute_diff:+.2f} "
                            f"({class_dist.entropy_a.dataset_a_value:.2f} vs {class_dist.entropy_a.dataset_b_value:.2f}), "
                            "indicating divergent class balance uniformity."
                        ),
                        metric_name="entropy",
                        value_a=class_dist.entropy_a.dataset_a_value,
                        value_b=class_dist.entropy_a.dataset_b_value,
                        absolute_diff=class_dist.entropy_a.absolute_diff,
                        pct_change=class_dist.entropy_a.pct_change,
                        threshold_used=1.0,
                        recommended_action="Check class frequencies to understand which dataset exhibits higher skew.",
                        evidence_references=["class_distribution.entropy_a"],
                    )
                )

        if class_dist.gini_coefficient.absolute_diff is not None:
            if abs(class_dist.gini_coefficient.absolute_diff) > 0.2:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-gini-difference",
                        category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                        severity=ComparisonSeverity.LOW,
                        title="Disparate Gini Concentration",
                        explanation=(
                            f"Gini coefficient differs by {class_dist.gini_coefficient.absolute_diff:+.3f} "
                            f"({class_dist.gini_coefficient.dataset_a_value:.3f} vs {class_dist.gini_coefficient.dataset_b_value:.3f})."
                        ),
                        metric_name="gini_coefficient",
                        value_a=class_dist.gini_coefficient.dataset_a_value,
                        value_b=class_dist.gini_coefficient.dataset_b_value,
                        absolute_diff=class_dist.gini_coefficient.absolute_diff,
                        pct_change=class_dist.gini_coefficient.pct_change,
                        threshold_used=0.2,
                        recommended_action="Inspect the more concentrated dataset for under-represented tail classes.",
                        evidence_references=["class_distribution.gini_coefficient"],
                    )
                )

        imb_a = class_dist.imbalance_ratio.dataset_a_value
        imb_b = class_dist.imbalance_ratio.dataset_b_value
        if imb_a and imb_b and imb_a > 0 and imb_b > 0:
            imb_mult = imb_b / imb_a if imb_b > imb_a else imb_a / imb_b
            if imb_mult > 5.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-imbalance-gap",
                        category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                        severity=ComparisonSeverity.MEDIUM,
                        title="Substantial Imbalance Ratio Divergence (>5x)",
                        explanation=(
                            f"Class imbalance ratio differs by {imb_mult:.1f}x "
                            f"({imb_a:.1f}:1 vs {imb_b:.1f}:1)."
                        ),
                        metric_name="imbalance_ratio",
                        value_a=imb_a,
                        value_b=imb_b,
                        absolute_diff=class_dist.imbalance_ratio.absolute_diff,
                        pct_change=class_dist.imbalance_ratio.pct_change,
                        threshold_used=5.0,
                        recommended_action="Apply class weighting or targeted augmentation to harmonize training loss landscape.",
                        evidence_references=["class_distribution.imbalance_ratio"],
                    )
                )

        # 4. Image characteristics
        if img_chars.median_width.pct_change is not None:
            if abs(img_chars.median_width.pct_change) > 50.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-dimension-median-difference",
                        category=ComparisonFindingCategory.IMAGE_CHARACTERISTICS,
                        severity=ComparisonSeverity.LOW,
                        title="Median Image Resolution Disparity (>50%)",
                        explanation=(
                            f"Median image width changes by {img_chars.median_width.pct_change:+.1f}% "
                            f"({img_chars.median_width.dataset_a_value:g}px vs {img_chars.median_width.dataset_b_value:g}px)."
                        ),
                        metric_name="median_width",
                        value_a=img_chars.median_width.dataset_a_value,
                        value_b=img_chars.median_width.dataset_b_value,
                        absolute_diff=img_chars.median_width.absolute_diff,
                        pct_change=img_chars.median_width.pct_change,
                        threshold_used=50.0,
                        recommended_action="Ensure image resizing or crop preprocessing is calibrated appropriately.",
                        evidence_references=["image_characteristics.median_width"],
                    )
                )

        if (
            img_chars.dominant_format_a
            and img_chars.dominant_format_b
            and img_chars.dominant_format_a != img_chars.dominant_format_b
        ):
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-format-difference",
                    category=ComparisonFindingCategory.IMAGE_CHARACTERISTICS,
                    severity=ComparisonSeverity.INFO,
                    title="Divergent Dominant File Formats",
                    explanation=(
                        f"Dataset A primarily uses {img_chars.dominant_format_a} while "
                        f"Dataset B primarily uses {img_chars.dominant_format_b}."
                    ),
                    metric_name="dominant_format",
                    value_a=None,
                    value_b=None,
                    absolute_diff=None,
                    pct_change=None,
                    threshold_used=None,
                    recommended_action="Standardize compression artifacts and decoding libraries across datasets.",
                    evidence_references=["image_characteristics.dominant_format_a", "image_characteristics.dominant_format_b"],
                )
            )

        # 5. Duplicates
        dup_a = overview.exact_duplicate_pct.dataset_a_value
        dup_b = overview.exact_duplicate_pct.dataset_b_value
        if dup_a is not None and dup_b is not None:
            dup_gap = abs(dup_b - dup_a)
            if dup_gap > 5.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-duplicate-rate-gap",
                        category=ComparisonFindingCategory.DUPLICATE_IMPACT,
                        severity=ComparisonSeverity.LOW,
                        title="Disparate Exact Duplicate Prevalence (>5%)",
                        explanation=(
                            f"Exact duplicate percentage differs by {dup_gap:.2f}% "
                            f"({dup_a:.2f}% in A vs {dup_b:.2f}% in B)."
                        ),
                        metric_name="exact_duplicate_percentage",
                        value_a=dup_a,
                        value_b=dup_b,
                        absolute_diff=overview.exact_duplicate_pct.absolute_diff,
                        pct_change=overview.exact_duplicate_pct.pct_change,
                        threshold_used=5.0,
                        recommended_action="Deduplicate datasets prior to model validation or benchmarking.",
                        evidence_references=["overview.exact_duplicate_pct"],
                    )
                )

        m_a = analysis_a.metrics
        m_b = analysis_b.metrics
        cc_a = (
            (m_a.cross_class_exact_duplicate_groups or 0)
            + (m_a.cross_class_near_duplicate_groups or 0)
            if m_a
            else 0
        )
        cc_b = (
            (m_b.cross_class_exact_duplicate_groups or 0)
            + (m_b.cross_class_near_duplicate_groups or 0)
            if m_b
            else 0
        )
        if cc_b > 0 and cc_b > cc_a:
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-cross-class-dups-b",
                    category=ComparisonFindingCategory.DUPLICATE_IMPACT,
                    severity=ComparisonSeverity.MEDIUM,
                    title="Elevated Cross-Class Duplicate Leakage in Dataset B",
                    explanation=f"Dataset B contains {cc_b} cross-class duplicate groups (compared to {cc_a} in Dataset A), indicating label leakage risks.",
                    metric_name="cross_class_duplicate_groups",
                    value_a=float(cc_a),
                    value_b=float(cc_b),
                    absolute_diff=float(cc_b - cc_a),
                    pct_change=None,
                    threshold_used=1.0,
                    recommended_action="Audit and resolve cross-class duplicate pairs in Dataset B to avoid confusing classifiers.",
                    evidence_references=["data_quality.cross_class_duplicates"],
                )
            )

        # 6. Quality score
        score_a = data_quality.overall_quality_score.dataset_a_value
        score_b = data_quality.overall_quality_score.dataset_b_value
        if score_a is not None and score_b is not None:
            score_diff = score_b - score_a
            if abs(score_diff) > 10.0:
                findings.append(
                    ComparisonFinding(
                        id="cmp-finding-quality-score-gap",
                        category=ComparisonFindingCategory.DATA_QUALITY,
                        severity=ComparisonSeverity.LOW,
                        title="Substantial Quality Score Gap (>10 points)",
                        explanation=(
                            f"Overall data quality score differs by {score_diff:+.1f} points "
                            f"({score_a:.1f}/100 in A vs {score_b:.1f}/100 in B)."
                        ),
                        metric_name="overall_quality_score",
                        value_a=score_a,
                        value_b=score_b,
                        absolute_diff=data_quality.overall_quality_score.absolute_diff,
                        pct_change=data_quality.overall_quality_score.pct_change,
                        threshold_used=10.0,
                        recommended_action="Investigate the lower scoring dataset for corrupted files, severe duplicates, or extreme imbalance.",
                        evidence_references=["data_quality.overall_quality_score"],
                    )
                )

        if (
            data_quality.quality_tier_a
            and data_quality.quality_tier_b
            and data_quality.quality_tier_a != data_quality.quality_tier_b
        ):
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-quality-tier-difference",
                    category=ComparisonFindingCategory.DATA_QUALITY,
                    severity=ComparisonSeverity.INFO,
                    title="Divergent Quality Tiers",
                    explanation=(
                        f"Dataset A is tiered as '{data_quality.quality_tier_a.upper()}' whereas "
                        f"Dataset B is tiered as '{data_quality.quality_tier_b.upper()}'."
                    ),
                    metric_name="quality_tier",
                    value_a=None,
                    value_b=None,
                    absolute_diff=None,
                    pct_change=None,
                    threshold_used=None,
                    recommended_action="Consult M3 Quality Lab assessment reports for detailed dimension breakdowns.",
                    evidence_references=["data_quality.quality_tier_a", "data_quality.quality_tier_b"],
                )
            )

        # 7. Missing upstream findings
        if quality_a is None or quality_b is None:
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-m3-unavailable",
                    category=ComparisonFindingCategory.DATA_QUALITY,
                    severity=ComparisonSeverity.INFO,
                    title="Incomplete M3 Quality Data",
                    explanation="One or both datasets lack an M3 Data Quality Assessment. Quality score metrics are partially omitted.",
                    metric_name="m3_availability",
                    value_a=1.0 if quality_a else 0.0,
                    value_b=1.0 if quality_b else 0.0,
                    absolute_diff=None,
                    pct_change=None,
                    threshold_used=None,
                    recommended_action="Execute POST /api/v1/datasets/{id}/quality-assessments for both datasets to unlock full quality comparison.",
                    evidence_references=["source_refs.quality_a_id", "source_refs.quality_b_id"],
                )
            )

        if eda_a is None or eda_b is None:
            findings.append(
                ComparisonFinding(
                    id="cmp-finding-m4-unavailable",
                    category=ComparisonFindingCategory.CLASS_DISTRIBUTION,
                    severity=ComparisonSeverity.INFO,
                    title="Incomplete M4 EDA Data",
                    explanation="One or both datasets lack an M4 EDA report. Distribution entropy and image dimension stats are partially omitted.",
                    metric_name="m4_availability",
                    value_a=1.0 if eda_a else 0.0,
                    value_b=1.0 if eda_b else 0.0,
                    absolute_diff=None,
                    pct_change=None,
                    threshold_used=None,
                    recommended_action="Execute POST /api/v1/datasets/{id}/eda for both datasets to unlock full statistical EDA comparison.",
                    evidence_references=["source_refs.eda_a_id", "source_refs.eda_b_id"],
                )
            )

        return findings

    # -------------------------------------------------------------------------
    # Retrieval and Status Endpoints
    # -------------------------------------------------------------------------

    def get_comparison(self, comparison_id: str) -> Optional[DatasetComparisonReport]:
        """Retrieve comparison report by ID, checking memory cache then disk."""
        if comparison_id in self._comparisons:
            return self._comparisons[comparison_id]

        data = self.storage.load_comparison(comparison_id)
        if data:
            try:
                report = DatasetComparisonReport.model_validate(data)
                self._comparisons[comparison_id] = report
                return report
            except Exception as exc:
                logger.error(
                    f"Failed to parse stored comparison report {comparison_id}: {exc}"
                )
        return None

    def get_latest_comparison_for_pair(
        self, dataset_a_id: str, dataset_b_id: str
    ) -> Optional[DatasetComparisonReport]:
        """Retrieve the latest comparison for a specific dataset pair."""
        latest_id = self.storage.get_latest_comparison_id_for_pair(
            dataset_a_id, dataset_b_id
        )
        if latest_id:
            return self.get_comparison(latest_id)
        return None

    def get_comparison_status(
        self, comparison_id: str
    ) -> Optional[ComparisonStatusResponse]:
        """Return high-level status for a comparison."""
        report = self.get_comparison(comparison_id)
        if not report:
            return None
        return ComparisonStatusResponse(
            comparison_id=report.id,
            dataset_a_id=report.dataset_a_id,
            dataset_b_id=report.dataset_b_id,
            status=report.status,
            created_at=report.created_at,
            completed_at=report.completed_at,
            duration_ms=report.duration_ms,
            methodology_version=report.methodology_version,
            error_message=report.error_message,
        )

    def list_comparisons(self) -> DatasetComparisonListResponse:
        """List all comparisons, sorted newest first."""
        # Refresh from disk to capture anything saved externally
        persisted = self.storage.list_persisted_comparisons()
        for record in persisted:
            cid = record.get("id")
            if cid and cid not in self._comparisons:
                try:
                    self._comparisons[cid] = DatasetComparisonReport.model_validate(record)
                except Exception:
                    pass

        summaries: List[DatasetComparisonSummary] = []
        for report in sorted(
            self._comparisons.values(), key=lambda r: r.created_at, reverse=True
        ):
            val_a = None
            val_b = None
            if report.overview and report.overview.valid_images:
                val_a = (
                    int(report.overview.valid_images.dataset_a_value)
                    if report.overview.valid_images.dataset_a_value is not None
                    else None
                )
                val_b = (
                    int(report.overview.valid_images.dataset_b_value)
                    if report.overview.valid_images.dataset_b_value is not None
                    else None
                )

            summaries.append(
                DatasetComparisonSummary(
                    id=report.id,
                    dataset_a_id=report.dataset_a_id,
                    dataset_b_id=report.dataset_b_id,
                    dataset_a_name=report.dataset_a_name,
                    dataset_b_name=report.dataset_b_name,
                    status=report.status,
                    freshness_status=report.freshness_status,
                    created_at=report.created_at,
                    completed_at=report.completed_at,
                    duration_ms=report.duration_ms,
                    findings_count=len(report.findings),
                    dataset_a_valid_images=val_a,
                    dataset_b_valid_images=val_b,
                )
            )

        return DatasetComparisonListResponse(
            total=len(summaries),
            items=summaries,
            note=None,
        )

    def check_freshness(self, comparison_id: str) -> ComparisonFreshnessResponse:
        """Check whether a comparison report is current or stale relative to latest analyses."""
        report = self.get_comparison(comparison_id)
        if not report:
            raise ComparisonNotFoundError(comparison_id)

        from app.services.analysis_service import analysis_service

        latest_a = analysis_service.get_latest_analysis_for_dataset(report.dataset_a_id)
        latest_b = analysis_service.get_latest_analysis_for_dataset(report.dataset_b_id)

        current_a_id = latest_a.id if latest_a else None
        current_b_id = latest_b.id if latest_b else None

        source_a_id = report.source_refs.analysis_a_id if report.source_refs else None
        source_b_id = report.source_refs.analysis_b_id if report.source_refs else None

        is_stale = False
        reasons = []

        if current_a_id and source_a_id and current_a_id != source_a_id:
            is_stale = True
            reasons.append(
                f"Dataset A ({report.dataset_a_id}) has a newer analysis ({current_a_id}) than comparison source ({source_a_id})."
            )
        if current_b_id and source_b_id and current_b_id != source_b_id:
            is_stale = True
            reasons.append(
                f"Dataset B ({report.dataset_b_id}) has a newer analysis ({current_b_id}) than comparison source ({source_b_id})."
            )

        freshness = ComparisonFreshness.STALE if is_stale else report.freshness_status

        return ComparisonFreshnessResponse(
            comparison_id=comparison_id,
            dataset_a_id=report.dataset_a_id,
            dataset_b_id=report.dataset_b_id,
            freshness_status=freshness,
            is_stale=is_stale,
            source_analysis_a_id=source_a_id,
            current_analysis_a_id=current_a_id,
            source_analysis_b_id=source_b_id,
            current_analysis_b_id=current_b_id,
            reason="; ".join(reasons) if reasons else "Comparison is current and aligned with latest analysis.",
        )

    def invalidate_stale_comparisons(
        self, dataset_id: str, new_analysis_id: str
    ) -> List[str]:
        """
        Mark comparisons involving dataset_id as STALE if their source analysis is older than new_analysis_id.
        Emits dataset.comparison.stale events and persists state to storage.
        """
        invalidated_ids: List[str] = []
        for report in list(self._comparisons.values()):
            needs_invalidation = False
            if (
                report.dataset_a_id == dataset_id
                and report.source_refs
                and report.source_refs.analysis_a_id != new_analysis_id
            ):
                needs_invalidation = True
            elif (
                report.dataset_b_id == dataset_id
                and report.source_refs
                and report.source_refs.analysis_b_id != new_analysis_id
            ):
                needs_invalidation = True

            if needs_invalidation:
                report.freshness_status = ComparisonFreshness.STALE
                try:
                    self.storage.save_comparison(
                        report.id,
                        report.model_dump(),
                        report.dataset_a_id,
                        report.dataset_b_id,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to persist invalidated comparison {report.id}: {exc}"
                    )
                invalidated_ids.append(report.id)
                event_bus.emit(
                    DatasetEventType.DATASET_COMPARISON_STALE,
                    dataset_id=dataset_id,
                    payload={"comparison_id": report.id, "new_analysis_id": new_analysis_id},
                )

        if invalidated_ids:
            logger.info(
                f"Invalidated {len(invalidated_ids)} comparisons for dataset {dataset_id} due to new analysis {new_analysis_id}."
            )
        return invalidated_ids


# Global comparison service singleton
comparison_service = ComparisonService()
