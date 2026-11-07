"""
M7 — Image Classification Insight Analyzer.

Generates insights from M2 Unified Analysis, M3 Data Quality Assessment,
and M4 EDA Report for image classification datasets.

Image clarity / blur / sharpness / contrast are NOT computed by CropLens and
are explicitly deferred to a future milestone. No fabricated metrics are produced.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from app.schemas.insights import (
    DatasetInsight,
    InsightCategory,
    InsightConfidence,
    InsightEvidence,
    InsightSeverity,
)
from app.services.insights.base_insight_analyzer import BaseInsightAnalyzer

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {
    InsightSeverity.CRITICAL: 0,
    InsightSeverity.HIGH: 1,
    InsightSeverity.MEDIUM: 2,
    InsightSeverity.LOW: 3,
    InsightSeverity.INFO: 4,
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_id(dataset_id: str, version_id: str, rule_id: str) -> str:
    safe_ds = dataset_id.replace("/", "-")[:40]
    safe_ver = version_id.replace("/", "-")[:20]
    return f"ins-{safe_ds}-{safe_ver}-{rule_id}"


class ImageInsightAnalyzer(BaseInsightAnalyzer):
    """
    Produces evidence-backed insights for image classification datasets.

    Reads from:
    - context["analysis"]  → UnifiedAnalysisResult (M2)
    - context["quality"]   → DataQualityAssessment (M3)
    - context["eda"]       → EdaReport (M4)
    """

    @property
    def name(self) -> str:
        return "image_insight_analyzer"

    def can_handle(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> bool:
        analysis = context.get("analysis")
        quality = context.get("quality")
        eda = context.get("eda")
        return any(x is not None for x in [analysis, quality, eda])

    def analyze(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[DatasetInsight]:
        insights: List[DatasetInsight] = []

        analysis = context.get("analysis")
        quality = context.get("quality")
        eda = context.get("eda")

        try:
            insights.extend(self._class_imbalance_insights(dataset_id, version_id, quality, eda))
        except Exception as exc:
            logger.warning(f"[{self.name}] class_imbalance rule failed: {exc}")

        try:
            insights.extend(self._empty_class_insights(dataset_id, version_id, quality, eda))
        except Exception as exc:
            logger.warning(f"[{self.name}] empty_class rule failed: {exc}")

        try:
            insights.extend(self._underrepresented_class_insights(dataset_id, version_id, quality, eda))
        except Exception as exc:
            logger.warning(f"[{self.name}] underrepresented_class rule failed: {exc}")

        try:
            insights.extend(self._duplicate_insights(dataset_id, version_id, analysis, quality))
        except Exception as exc:
            logger.warning(f"[{self.name}] duplicate rule failed: {exc}")

        try:
            insights.extend(self._corrupted_image_insights(dataset_id, version_id, analysis, quality))
        except Exception as exc:
            logger.warning(f"[{self.name}] corrupted_image rule failed: {exc}")

        try:
            insights.extend(self._dimension_inconsistency_insights(dataset_id, version_id, eda, quality))
        except Exception as exc:
            logger.warning(f"[{self.name}] dimension_inconsistency rule failed: {exc}")

        try:
            insights.extend(self._color_mode_insights(dataset_id, version_id, eda, quality))
        except Exception as exc:
            logger.warning(f"[{self.name}] color_mode rule failed: {exc}")

        try:
            insights.extend(self._readiness_insight(dataset_id, version_id, analysis, quality, eda, insights))
        except Exception as exc:
            logger.warning(f"[{self.name}] readiness rule failed: {exc}")

        return insights

    # ------------------------------------------------------------------
    # Individual rules
    # ------------------------------------------------------------------

    def _class_imbalance_insights(
        self,
        dataset_id: str,
        version_id: str,
        quality: Any,
        eda: Any,
    ) -> List[DatasetInsight]:
        """Rule: class imbalance based on imbalance_ratio."""
        ratio: Optional[float] = None
        source = "unknown"

        if quality is not None:
            try:
                ratio = quality.imbalance.imbalance_ratio
                source = "quality"
            except AttributeError:
                pass

        if ratio is None and eda is not None:
            try:
                ratio = eda.class_distribution.imbalance_ratio
                source = "eda"
            except AttributeError:
                pass

        if ratio is None:
            return []

        if ratio >= 10:
            severity = InsightSeverity.CRITICAL
            threshold = 10.0
        elif ratio >= 5:
            severity = InsightSeverity.HIGH
            threshold = 5.0
        elif ratio >= 3:
            severity = InsightSeverity.MEDIUM
            threshold = 3.0
        else:
            return []

        rule_id = "class_imbalance"
        evidence = InsightEvidence(
            metric="imbalance_ratio",
            value=round(ratio, 2),
            unit="ratio",
            threshold=threshold,
            source_artifact=f"{source}_assessment" if source == "quality" else f"{source}_report",
            source_path="imbalance.imbalance_ratio" if source == "quality" else "class_distribution.imbalance_ratio",
            explanation=(
                f"The most populated class has {round(ratio, 2)}x as many images as the least populated class. "
                f"Ratios above {threshold:.0f}x are classified as {severity.value} imbalance."
            ),
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.CLASS_DISTRIBUTION,
                severity=severity,
                confidence=InsightConfidence.HIGH,
                title="Severe class imbalance detected",
                summary=f"The dataset has an imbalance ratio of {round(ratio, 2):.1f}x between the largest and smallest classes.",
                explanation=(
                    f"Class imbalance of {round(ratio, 2):.1f}x will cause a classifier trained on this dataset to be "
                    "biased toward majority classes. Models will exhibit poor recall on minority classes and "
                    "inflated accuracy that does not reflect real-world performance."
                ),
                evidence=[evidence],
                impact=(
                    "Training on a severely imbalanced dataset leads to biased classifiers. "
                    "Minority classes will be under-predicted, reducing recall and practical utility."
                ),
                recommended_action=(
                    "Apply class-aware sampling: oversample minority classes (e.g. SMOTE for tabular, "
                    "augmentation for images) or undersample majority classes. "
                    "Alternatively, use class-weighted loss functions during training."
                ),
                limitations="",
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _empty_class_insights(
        self,
        dataset_id: str,
        version_id: str,
        quality: Any,
        eda: Any,
    ) -> List[DatasetInsight]:
        """Rule: classes with zero images."""
        empty: List[str] = []

        if quality is not None:
            try:
                empty = list(quality.imbalance.empty_classes)
            except AttributeError:
                pass

        if not empty and eda is not None:
            try:
                # EdaReport class_distribution may expose empty_classes
                dist = eda.class_distribution.class_counts if hasattr(eda, "class_distribution") else {}
                if hasattr(eda.class_distribution, "empty_classes"):
                    empty = list(eda.class_distribution.empty_classes)
                elif isinstance(dist, dict):
                    empty = [k for k, v in dist.items() if v == 0]
            except AttributeError:
                pass

        if not empty:
            return []

        rule_id = "empty_classes"
        source = "quality_assessment" if quality is not None else "eda_report"
        path = "imbalance.empty_classes" if quality is not None else "class_distribution.empty_classes"
        evidence = InsightEvidence(
            metric="empty_class_count",
            value=len(empty),
            unit="classes",
            source_artifact=source,
            source_path=path,
            explanation=f"{len(empty)} class director(ies) contain zero images and cannot contribute to training.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.CLASS_DISTRIBUTION,
                severity=InsightSeverity.HIGH,
                confidence=InsightConfidence.HIGH,
                title=f"{len(empty)} empty class(es) detected",
                summary=f"{len(empty)} class(es) have zero images and will be excluded from training.",
                explanation=(
                    f"The following classes have no images: {', '.join(empty[:10])}{'...' if len(empty) > 10 else ''}. "
                    "Empty classes cannot be learned by a classifier and will cause evaluation metrics to be misleading."
                ),
                evidence=[evidence],
                affected_classes=list(empty),
                impact="Empty classes will prevent training or cause misleading evaluation results.",
                recommended_action=(
                    "Collect and label images for empty classes, or remove them from the class taxonomy "
                    "if they are no longer relevant."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _underrepresented_class_insights(
        self,
        dataset_id: str,
        version_id: str,
        quality: Any,
        eda: Any,
    ) -> List[DatasetInsight]:
        """Rule: classes significantly below the dataset mean."""
        underrepresented: List[Dict] = []

        if quality is not None:
            try:
                underrepresented = list(quality.imbalance.underrepresented_classes)
            except AttributeError:
                pass

        if not underrepresented:
            return []

        rule_id = "underrepresented_classes"
        class_names = [
            c.get("class") or c.get("class_name") or str(c)
            for c in underrepresented
            if isinstance(c, dict)
        ][:20]

        evidence = InsightEvidence(
            metric="underrepresented_class_count",
            value=len(underrepresented),
            unit="classes",
            source_artifact="quality_assessment",
            source_path="imbalance.underrepresented_classes",
            explanation=(
                f"{len(underrepresented)} classes have image counts significantly below the dataset mean, "
                "increasing the risk of under-learning for those classes."
            ),
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.CLASS_DISTRIBUTION,
                severity=InsightSeverity.MEDIUM,
                confidence=InsightConfidence.HIGH,
                title=f"{len(underrepresented)} underrepresented class(es) detected",
                summary=f"{len(underrepresented)} classes have fewer images than expected relative to the dataset mean.",
                explanation=(
                    f"{len(underrepresented)} class(es) have image counts significantly below the mean. "
                    "Under-represented classes are at risk of being under-learned by classifiers, "
                    "leading to lower recall for those specific classes."
                ),
                evidence=[evidence],
                affected_classes=class_names,
                impact="Models may exhibit reduced recall for underrepresented classes.",
                recommended_action=(
                    "Collect additional images for underrepresented classes, or apply data augmentation "
                    "selectively. Consider using class-weighted loss functions."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _duplicate_insights(
        self,
        dataset_id: str,
        version_id: str,
        analysis: Any,
        quality: Any,
    ) -> List[DatasetInsight]:
        """Rule: exact and near duplicate presence."""
        results = []

        # Exact duplicates
        exact_groups: Optional[int] = None
        exact_pct: Optional[float] = None

        if quality is not None:
            try:
                exact_groups = quality.duplicate_impact.exact_duplicate_groups
                exact_pct = quality.duplicate_impact.exact_duplicate_percentage
            except AttributeError:
                pass

        if exact_groups and exact_groups > 0:
            rule_id = "exact_duplicates"
            evidence = InsightEvidence(
                metric="exact_duplicate_groups",
                value=exact_groups,
                unit="groups",
                source_artifact="quality_assessment",
                source_path="duplicate_impact.exact_duplicate_groups",
                explanation=(
                    f"{exact_groups} exact duplicate group(s) detected via SHA-256 hash comparison. "
                    + (f"Approximately {round(exact_pct, 1)}% of validated images are redundant copies." if exact_pct else "")
                ),
            )
            severity = InsightSeverity.HIGH if (exact_pct or 0) >= 10 else InsightSeverity.MEDIUM
            results.append(
                DatasetInsight(
                    insight_id=_make_id(dataset_id, version_id, rule_id),
                    dataset_id=dataset_id,
                    version_id=version_id,
                    category=InsightCategory.DUPLICATE_DATA,
                    severity=severity,
                    confidence=InsightConfidence.HIGH,
                    title=f"{exact_groups} exact duplicate group(s) found",
                    summary=f"SHA-256 exact duplicate detection identified {exact_groups} redundant image group(s).",
                    explanation=(
                        f"{exact_groups} groups of byte-identical images were detected. "
                        "Exact duplicates inflate dataset size without adding information "
                        "and can cause train/test leakage if splits are not deduplicated first."
                    ),
                    evidence=[evidence],
                    impact="Exact duplicates cause train/test leakage and inflate evaluation metrics.",
                    recommended_action=(
                        "Remove redundant duplicate copies before splitting into train/validation/test sets. "
                        "Keep one representative per duplicate group."
                    ),
                    created_at=_now(),
                    analyzer_id=self.name,
                    rule_id=rule_id,
                )
            )

        # Near duplicates
        near_groups: Optional[int] = None
        near_pct: Optional[float] = None

        if quality is not None:
            try:
                near_groups = quality.duplicate_impact.near_duplicate_groups
                near_pct = quality.duplicate_impact.near_duplicate_percentage
            except AttributeError:
                pass

        if near_groups and near_groups > 0:
            rule_id = "near_duplicates"
            evidence = InsightEvidence(
                metric="near_duplicate_groups",
                value=near_groups,
                unit="groups",
                source_artifact="quality_assessment",
                source_path="duplicate_impact.near_duplicate_groups",
                explanation=(
                    f"{near_groups} perceptually similar image group(s) detected via perceptual hashing. "
                    + (f"Approximately {round(near_pct, 1)}% of images are near-duplicates." if near_pct else "")
                ),
            )
            severity = InsightSeverity.MEDIUM if (near_pct or 0) < 20 else InsightSeverity.HIGH
            results.append(
                DatasetInsight(
                    insight_id=_make_id(dataset_id, version_id, rule_id),
                    dataset_id=dataset_id,
                    version_id=version_id,
                    category=InsightCategory.DUPLICATE_DATA,
                    severity=severity,
                    confidence=InsightConfidence.MEDIUM,
                    title=f"{near_groups} near-duplicate group(s) found",
                    summary=f"Perceptual hashing identified {near_groups} group(s) of visually similar images.",
                    explanation=(
                        f"{near_groups} groups of perceptually similar images were detected. "
                        "Near-duplicates may represent augmented copies or slight variations that could cause "
                        "leakage between train and test sets if not handled carefully."
                    ),
                    evidence=[evidence],
                    impact=(
                        "Near-duplicates may cause optimistic evaluation if they appear in both train and test sets."
                    ),
                    recommended_action=(
                        "Review near-duplicate groups and decide whether to merge, remove, or retain them. "
                        "Ensure near-duplicates are assigned to the same dataset split."
                    ),
                    created_at=_now(),
                    analyzer_id=self.name,
                    rule_id=rule_id,
                )
            )

        return results

    def _corrupted_image_insights(
        self,
        dataset_id: str,
        version_id: str,
        analysis: Any,
        quality: Any,
    ) -> List[DatasetInsight]:
        """Rule: corrupted or unreadable images."""
        corrupted: Optional[int] = None
        integrity_rate: Optional[float] = None

        if quality is not None:
            try:
                corrupted = (quality.integrity.total_corrupted_images or 0) + (
                    quality.integrity.total_unreadable_images or 0
                )
                integrity_rate = quality.integrity.integrity_rate
            except AttributeError:
                pass

        if not corrupted or corrupted == 0:
            return []

        severity = InsightSeverity.HIGH if (integrity_rate or 100) < 95 else InsightSeverity.MEDIUM
        rule_id = "corrupted_images"
        evidence = InsightEvidence(
            metric="corrupted_or_unreadable_images",
            value=corrupted,
            unit="images",
            threshold=0.0,
            source_artifact="quality_assessment",
            source_path="integrity.total_corrupted_images",
            explanation=f"{corrupted} image(s) could not be decoded and are unsuitable for training.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.IMAGE_QUALITY,
                severity=severity,
                confidence=InsightConfidence.HIGH,
                title=f"{corrupted} corrupted or unreadable image(s) detected",
                summary=f"{corrupted} image(s) failed integrity checks and cannot be used for training.",
                explanation=(
                    f"{corrupted} image file(s) are corrupt, truncated, or unreadable. "
                    "These files cannot be decoded by standard image libraries and will cause "
                    "training errors if not removed."
                ),
                evidence=[evidence],
                impact="Corrupted images cause training pipeline errors or silently reduce effective dataset size.",
                recommended_action=(
                    "Remove or replace corrupted image files before training. "
                    "Re-collect corrupted images from the original source if possible."
                ),
                limitations=(
                    "Image clarity, blur, sharpness, brightness, and contrast metrics are not yet computed by CropLens. "
                    "Deferred to a future milestone."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _dimension_inconsistency_insights(
        self,
        dataset_id: str,
        version_id: str,
        eda: Any,
        quality: Any,
    ) -> List[DatasetInsight]:
        """Rule: high number of unique image dimensions."""
        unique_dims: Optional[int] = None
        small_dim_count: Optional[int] = None
        source = "unknown"

        if eda is not None:
            try:
                unique_dims = eda.dimension_analysis.unique_dimensions
                source = "eda_report"
            except AttributeError:
                pass

        if quality is not None and small_dim_count is None:
            try:
                small_dim_count = quality.metadata_consistency.small_dimension_images_count
            except AttributeError:
                pass

        results = []

        if unique_dims is not None and unique_dims > 10:
            severity = InsightSeverity.MEDIUM if unique_dims <= 50 else InsightSeverity.HIGH
            rule_id = "dimension_inconsistency"
            evidence = InsightEvidence(
                metric="unique_dimensions",
                value=unique_dims,
                unit="distinct (width, height) pairs",
                threshold=10.0,
                source_artifact=source,
                source_path="dimension_analysis.unique_dimensions",
                explanation=f"{unique_dims} distinct image dimension combinations found; more than 10 suggests inconsistent preprocessing.",
            )
            results.append(
                DatasetInsight(
                    insight_id=_make_id(dataset_id, version_id, rule_id),
                    dataset_id=dataset_id,
                    version_id=version_id,
                    category=InsightCategory.IMAGE_QUALITY,
                    severity=severity,
                    confidence=InsightConfidence.MEDIUM,
                    title=f"Inconsistent image dimensions ({unique_dims} unique sizes)",
                    summary=f"The dataset contains images in {unique_dims} different dimension combinations.",
                    explanation=(
                        f"{unique_dims} distinct (width, height) combinations were found. "
                        "Most deep learning frameworks require a fixed input size. "
                        "Mixed dimensions indicate inconsistent preprocessing or data collection from multiple sources."
                    ),
                    evidence=[evidence],
                    impact="Mixed dimensions require runtime resizing, which may distort aspect ratios and degrade model quality.",
                    recommended_action=(
                        "Standardize image dimensions to a consistent size (e.g. 224×224 or 256×256) "
                        "using center-crop, padding, or resizing with preserved aspect ratio."
                    ),
                    created_at=_now(),
                    analyzer_id=self.name,
                    rule_id=rule_id,
                )
            )

        if small_dim_count and small_dim_count > 0:
            rule_id = "small_dimension_images"
            evidence = InsightEvidence(
                metric="small_dimension_images_count",
                value=small_dim_count,
                unit="images",
                threshold=224.0,
                source_artifact="quality_assessment",
                source_path="metadata_consistency.small_dimension_images_count",
                explanation=f"{small_dim_count} images have width or height below 224px, which is below the common minimum for modern CNNs.",
            )
            results.append(
                DatasetInsight(
                    insight_id=_make_id(dataset_id, version_id, rule_id),
                    dataset_id=dataset_id,
                    version_id=version_id,
                    category=InsightCategory.IMAGE_QUALITY,
                    severity=InsightSeverity.MEDIUM,
                    confidence=InsightConfidence.HIGH,
                    title=f"{small_dim_count} low-resolution image(s) detected",
                    summary=f"{small_dim_count} images have at least one dimension below 224px.",
                    explanation=(
                        f"{small_dim_count} images have width or height below 224 pixels. "
                        "Many modern CNN architectures expect at minimum 224×224 input. "
                        "Upscaling very small images causes quality loss and can degrade feature extraction."
                    ),
                    evidence=[evidence],
                    impact="Low-resolution images may degrade model performance when upscaled to match network input requirements.",
                    recommended_action=(
                        "Review and replace low-resolution images with higher quality alternatives, "
                        "or use a model architecture designed for smaller inputs."
                    ),
                    created_at=_now(),
                    analyzer_id=self.name,
                    rule_id=rule_id,
                )
            )

        return results

    def _color_mode_insights(
        self,
        dataset_id: str,
        version_id: str,
        eda: Any,
        quality: Any,
    ) -> List[DatasetInsight]:
        """Rule: mixed color modes (e.g. RGB and grayscale)."""
        color_modes: Dict[str, int] = {}

        if quality is not None:
            try:
                color_modes = dict(quality.metadata_consistency.color_mode_distribution)
            except AttributeError:
                pass

        if not color_modes and eda is not None:
            try:
                color_modes = dict(eda.color_analysis.color_mode_distribution)
            except AttributeError:
                pass

        if len(color_modes) <= 1:
            return []

        rule_id = "mixed_color_modes"
        total = sum(color_modes.values())
        mode_summary = ", ".join(f"{m}: {c}" for m, c in color_modes.items())
        evidence = InsightEvidence(
            metric="color_mode_count",
            value=len(color_modes),
            unit="distinct color modes",
            threshold=1.0,
            source_artifact="quality_assessment" if quality else "eda_report",
            source_path="metadata_consistency.color_mode_distribution",
            explanation=f"Dataset contains images in {len(color_modes)} different color modes: {mode_summary}.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.IMAGE_QUALITY,
                severity=InsightSeverity.MEDIUM,
                confidence=InsightConfidence.HIGH,
                title=f"Mixed color modes detected ({len(color_modes)} modes)",
                summary=f"Dataset images use {len(color_modes)} different color modes ({mode_summary}).",
                explanation=(
                    f"The dataset contains images in {len(color_modes)} color modes: {mode_summary}. "
                    "Most CNN architectures expect a single consistent color mode (typically RGB). "
                    "Mixing grayscale (L) and color (RGB) images requires runtime conversion "
                    "and may introduce channel mismatches."
                ),
                evidence=[evidence],
                impact="Mixed color modes require runtime normalization; grayscale images converted to RGB lose no information but require preprocessing.",
                recommended_action=(
                    "Convert all images to a single color mode (preferably RGB) during preprocessing. "
                    "Verify that grayscale images are intentional and not corruption artifacts."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _readiness_insight(
        self,
        dataset_id: str,
        version_id: str,
        analysis: Any,
        quality: Any,
        eda: Any,
        existing_insights: List[DatasetInsight],
    ) -> List[DatasetInsight]:
        """Rule: overall dataset readiness summary."""
        critical_count = sum(1 for i in existing_insights if i.severity == InsightSeverity.CRITICAL)
        high_count = sum(1 for i in existing_insights if i.severity == InsightSeverity.HIGH)

        total_images: Optional[int] = None
        quality_tier: Optional[str] = None

        if analysis is not None:
            try:
                total_images = analysis.metrics.total_validated_images
            except AttributeError:
                pass

        if quality is not None:
            try:
                quality_tier = quality.quality_score.quality_tier
            except AttributeError:
                pass

        if critical_count > 0:
            severity = InsightSeverity.CRITICAL
            readiness = "not ready for training"
        elif high_count > 0:
            severity = InsightSeverity.HIGH
            readiness = "requires remediation before training"
        elif quality_tier in ("fair", "poor", "critical"):
            severity = InsightSeverity.MEDIUM
            readiness = "has quality concerns that should be addressed"
        else:
            severity = InsightSeverity.INFO
            readiness = "appears suitable for initial training"

        evidence_list = []
        if quality_tier:
            evidence_list.append(
                InsightEvidence(
                    metric="quality_tier",
                    value=quality_tier,
                    source_artifact="quality_assessment",
                    source_path="quality_score.quality_tier",
                    explanation=f"Overall quality tier assessed as '{quality_tier}' by M3 Data Quality Lab.",
                )
            )
        if total_images is not None:
            evidence_list.append(
                InsightEvidence(
                    metric="total_validated_images",
                    value=total_images,
                    unit="images",
                    source_artifact="analysis",
                    source_path="metrics.total_validated_images",
                    explanation=f"Dataset contains {total_images} validated images.",
                )
            )

        rule_id = "dataset_readiness"
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.DATASET_READINESS,
                severity=severity,
                confidence=InsightConfidence.MEDIUM,
                title=f"Dataset {readiness}",
                summary=f"Based on {len(existing_insights)} finding(s), this dataset {readiness}.",
                explanation=(
                    f"M7 analysis identified {critical_count} critical and {high_count} high-severity finding(s). "
                    + (f"M3 quality tier: '{quality_tier}'. " if quality_tier else "")
                    + (f"Total validated images: {total_images}. " if total_images is not None else "")
                    + f"Overall readiness assessment: {readiness}."
                ),
                evidence=evidence_list,
                impact=(
                    "Unresolved critical or high-severity issues will degrade model performance "
                    "or cause training pipeline failures."
                ),
                recommended_action=(
                    "Address critical and high-severity findings first, then re-run analysis to verify improvement. "
                    "Consider using the M3 quality score trend over versions to track progress."
                ),
                limitations=(
                    "Image clarity, blur, sharpness, brightness, and contrast are not computed by CropLens "
                    "and are excluded from this readiness assessment. Deferred to a future milestone."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

