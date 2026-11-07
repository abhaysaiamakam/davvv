"""
M7 — Annotation Dataset Insight Analyzer.

Generates insights from annotation visualization specifications (COCO JSON / YOLO TXT)
already produced by the Visualization Specification Engine.
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


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_id(dataset_id: str, version_id: str, rule_id: str) -> str:
    safe_ds = dataset_id.replace("/", "-")[:40]
    safe_ver = version_id.replace("/", "-")[:20]
    return f"ins-{safe_ds}-{safe_ver}-{rule_id}"


class AnnotationInsightAnalyzer(BaseInsightAnalyzer):
    """
    Produces insights for object detection / segmentation annotation datasets.

    Reads from context["visualizations"] — looks for annotation category specs
    produced by AnnotationVisualizer.
    """

    @property
    def name(self) -> str:
        return "annotation_insight_analyzer"

    def can_handle(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> bool:
        return self._get_annotation_specs(context) is not None

    def analyze(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[DatasetInsight]:
        annotation_specs = self._get_annotation_specs(context)
        if not annotation_specs:
            return []

        insights: List[DatasetInsight] = []

        for spec in annotation_specs[:3]:
            try:
                class_counts = self._extract_class_counts(spec)
                if not class_counts:
                    continue

                label = self._spec_label(spec)
                suffix = f"-{label}"

                insights.extend(self._single_class_insight(dataset_id, version_id, class_counts, label, suffix))
                insights.extend(self._annotation_imbalance_insight(dataset_id, version_id, class_counts, label, suffix))
                insights.extend(self._sparse_class_insight(dataset_id, version_id, class_counts, label, suffix))

            except Exception as exc:
                logger.warning(f"[{self.name}] Error analyzing annotation spec: {exc}")

        return insights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_annotation_specs(self, context: Dict[str, Any]) -> Optional[List[Any]]:
        visualizations = context.get("visualizations")
        if visualizations is None:
            return None

        specs = []
        try:
            if hasattr(visualizations, "items"):
                items = visualizations.items
            elif isinstance(visualizations, dict):
                items = visualizations.get("items", [])
            else:
                items = list(visualizations)

            for item in items:
                category = getattr(item, "category", None) or (item.get("category") if isinstance(item, dict) else None)
                if category and str(category).lower() in ("annotation_distribution", "annotation"):
                    specs.append(item)
        except Exception:
            return None

        return specs if specs else None

    def _extract_class_counts(self, spec: Any) -> Optional[Dict[str, int]]:
        try:
            chart_data = getattr(spec, "chart_data", None) or (spec.get("chart_data") if isinstance(spec, dict) else None)
            if chart_data is None:
                return None
            if isinstance(chart_data, dict):
                # Look for label→count or category→count structures
                for key in ("class_counts", "category_counts", "label_counts", "data"):
                    val = chart_data.get(key)
                    if isinstance(val, dict):
                        return {str(k): int(v) for k, v in val.items() if isinstance(v, (int, float))}
                    if isinstance(val, list):
                        result = {}
                        for item in val:
                            if isinstance(item, dict):
                                name = item.get("name") or item.get("label") or item.get("category")
                                count = item.get("count") or item.get("value") or item.get("y")
                                if name and count is not None:
                                    result[str(name)] = int(count)
                        if result:
                            return result
        except Exception:
            pass
        return None

    def _spec_label(self, spec: Any) -> str:
        try:
            title = getattr(spec, "title", None) or (spec.get("title") if isinstance(spec, dict) else None)
            if title:
                return str(title)[:40].replace(" ", "_").lower()
        except Exception:
            pass
        return "annotations"

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def _single_class_insight(
        self,
        dataset_id: str,
        version_id: str,
        class_counts: Dict[str, int],
        label: str,
        suffix: str,
    ) -> List[DatasetInsight]:
        if len(class_counts) != 1:
            return []

        only_class = list(class_counts.keys())[0]
        rule_id = f"single_class_annotation{suffix}"
        evidence = InsightEvidence(
            metric="annotation_class_count",
            value=1,
            unit="classes",
            source_artifact="visualization_spec",
            source_path=f"annotation:{label}",
            explanation=f"Only one annotation class found: '{only_class}'.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.ANNOTATION_QUALITY,
                severity=InsightSeverity.INFO,
                confidence=InsightConfidence.HIGH,
                title=f"Single-class annotation dataset ('{only_class}')",
                summary=f"Only one annotation class ('{only_class}') is present. This is valid for binary detection tasks.",
                explanation=(
                    f"The annotation data contains only one class: '{only_class}'. "
                    "This is appropriate for binary detection tasks (foreground vs. background) "
                    "but may indicate incomplete labeling for multi-class objectives."
                ),
                evidence=[evidence],
                impact="Single-class datasets limit model applicability to binary detection tasks.",
                recommended_action=(
                    "Verify that only one class is intended. If multiple classes should be present, "
                    "check annotation completeness and labeling coverage."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _annotation_imbalance_insight(
        self,
        dataset_id: str,
        version_id: str,
        class_counts: Dict[str, int],
        label: str,
        suffix: str,
    ) -> List[DatasetInsight]:
        if len(class_counts) < 2:
            return []

        counts = list(class_counts.values())
        max_count = max(counts)
        min_count = min(counts)

        if min_count == 0:
            return []  # Handled by sparse class rule

        ratio = max_count / min_count
        if ratio < 5:
            return []

        severity = InsightSeverity.HIGH if ratio >= 10 else InsightSeverity.MEDIUM
        max_class = max(class_counts, key=class_counts.get)
        min_class = min(class_counts, key=class_counts.get)

        rule_id = f"annotation_imbalance{suffix}"
        evidence = InsightEvidence(
            metric="annotation_imbalance_ratio",
            value=round(ratio, 2),
            unit="ratio",
            threshold=5.0,
            source_artifact="visualization_spec",
            source_path=f"annotation:{label}",
            explanation=(
                f"Most frequent class '{max_class}' ({max_count} annotations) vs "
                f"least frequent class '{min_class}' ({min_count} annotations) — ratio: {round(ratio, 2):.1f}x."
            ),
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.ANNOTATION_QUALITY,
                severity=severity,
                confidence=InsightConfidence.HIGH,
                title=f"Annotation class imbalance ({round(ratio, 2):.1f}x ratio)",
                summary=f"Annotation data shows a {round(ratio, 2):.1f}x imbalance between most and least frequent classes.",
                explanation=(
                    f"Class '{max_class}' has {max_count} annotations while '{min_class}' has only {min_count}. "
                    f"This {round(ratio, 2):.1f}x ratio will bias detectors toward dominant classes."
                ),
                evidence=[evidence],
                impact="Imbalanced annotations cause detectors to under-detect rare classes.",
                recommended_action=(
                    "Balance annotation counts through additional labeling of underrepresented classes, "
                    "or use class-balanced sampling during training."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _sparse_class_insight(
        self,
        dataset_id: str,
        version_id: str,
        class_counts: Dict[str, int],
        label: str,
        suffix: str,
    ) -> List[DatasetInsight]:
        sparse = {cls: cnt for cls, cnt in class_counts.items() if cnt < 10}
        if not sparse:
            return []

        rule_id = f"sparse_annotation_classes{suffix}"
        evidence = InsightEvidence(
            metric="sparse_annotation_class_count",
            value=len(sparse),
            unit="classes",
            threshold=10.0,
            source_artifact="visualization_spec",
            source_path=f"annotation:{label}",
            explanation=f"{len(sparse)} class(es) have fewer than 10 annotation instances.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.ANNOTATION_QUALITY,
                severity=InsightSeverity.HIGH,
                confidence=InsightConfidence.HIGH,
                title=f"{len(sparse)} annotation class(es) with fewer than 10 instances",
                summary=f"{len(sparse)} class(es) have too few annotations for reliable detection training.",
                explanation=(
                    f"The following classes have fewer than 10 annotation instances: "
                    f"{', '.join(list(sparse.keys())[:10])}. "
                    "Object detectors typically need at minimum hundreds of instances per class "
                    "for reliable learning."
                ),
                evidence=[evidence],
                affected_classes=list(sparse.keys())[:20],
                impact="Sparse annotation classes result in detectors that cannot reliably recognize those classes.",
                recommended_action=(
                    "Collect and label additional instances for sparse classes. "
                    "Consider using data augmentation or few-shot detection approaches for rare classes."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

