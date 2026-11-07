"""
M7 — Time-Series Insight Analyzer.

Generates insights from temporal visualization specifications already produced
by the M6 Visualization Specification Engine. Does NOT re-read raw CSVs for
time-series analysis — instead reads from the visualization context if available.
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


class TimeSeriesInsightAnalyzer(BaseInsightAnalyzer):
    """
    Produces evidence-backed insights for time-series datasets.

    Reads from context["visualizations"] — a VisualizationCollection or
    list of VisualizationSpecification objects — to find time-series specs.
    """

    @property
    def name(self) -> str:
        return "time_series_insight_analyzer"

    def can_handle(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> bool:
        return self._get_time_series_specs(context) is not None

    def analyze(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[DatasetInsight]:
        ts_specs = self._get_time_series_specs(context)
        if not ts_specs:
            return []

        insights: List[DatasetInsight] = []

        for spec in ts_specs[:3]:  # Cap at 3 to avoid flooding
            try:
                data_points = self._extract_data_points(spec)
                if data_points is None:
                    continue

                label = self._spec_label(spec)
                suffix = f"-{label}"

                insights.extend(self._short_series_insight(dataset_id, version_id, data_points, label, suffix))
                insights.extend(self._trend_insight(dataset_id, version_id, data_points, label, suffix))

            except Exception as exc:
                logger.warning(f"[{self.name}] Error analyzing time-series spec: {exc}")

        return insights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_time_series_specs(self, context: Dict[str, Any]) -> Optional[List[Any]]:
        """Extract time-series visualization specs from the context."""
        visualizations = context.get("visualizations")
        if visualizations is None:
            return None

        specs = []
        try:
            # VisualizationCollection object
            if hasattr(visualizations, "items"):
                items = visualizations.items
            # dict form
            elif isinstance(visualizations, dict):
                items = visualizations.get("items", [])
            else:
                items = list(visualizations)

            for item in items:
                category = getattr(item, "category", None) or (item.get("category") if isinstance(item, dict) else None)
                if category and str(category).lower() in ("time_series", "time_series_trend"):
                    specs.append(item)
        except Exception:
            return None

        return specs if specs else None

    def _extract_data_points(self, spec: Any) -> Optional[List[Any]]:
        """Extract data points list from a spec object or dict."""
        try:
            chart_data = getattr(spec, "chart_data", None) or (spec.get("chart_data") if isinstance(spec, dict) else None)
            if chart_data is None:
                return None
            if isinstance(chart_data, dict):
                return chart_data.get("data_points") or chart_data.get("points") or chart_data.get("data")
            if isinstance(chart_data, list):
                return chart_data
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
        return "ts"

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def _short_series_insight(
        self,
        dataset_id: str,
        version_id: str,
        data_points: List[Any],
        label: str,
        suffix: str,
    ) -> List[DatasetInsight]:
        n = len(data_points)
        if n >= 10:
            return []

        rule_id = f"short_time_series{suffix}"
        evidence = InsightEvidence(
            metric="time_series_length",
            value=n,
            unit="data points",
            threshold=10.0,
            source_artifact="visualization_spec",
            source_path=f"time_series:{label}",
            explanation=f"Time series '{label}' has only {n} data points, insufficient for trend or seasonality analysis.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.TIME_SERIES,
                severity=InsightSeverity.MEDIUM,
                confidence=InsightConfidence.HIGH,
                title=f"Very short time series ({n} points) — trend inference unreliable",
                summary=f"Time series '{label}' has only {n} data points; trends and seasonality cannot be reliably inferred.",
                explanation=(
                    f"The time series '{label}' contains only {n} data points. "
                    "With fewer than 10 observations, trend detection has very high variance "
                    "and seasonality analysis is not meaningful. "
                    "CropLens does not claim seasonality or periodicity for short series."
                ),
                evidence=[evidence],
                impact="Short time series produce unreliable trend estimates and false seasonality signals.",
                recommended_action=(
                    "Collect additional temporal observations before applying trend or seasonality models. "
                    "Consider whether this is truly a time-series problem or a cross-sectional dataset."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _trend_insight(
        self,
        dataset_id: str,
        version_id: str,
        data_points: List[Any],
        label: str,
        suffix: str,
    ) -> List[DatasetInsight]:
        if len(data_points) < 3:
            return []

        # Extract values — handle both dict and scalar data points
        values = []
        for pt in data_points:
            try:
                if isinstance(pt, dict):
                    v = pt.get("y") or pt.get("value") or pt.get("count")
                else:
                    v = float(pt)
                if v is not None:
                    values.append(float(v))
            except (TypeError, ValueError):
                pass

        if len(values) < 3:
            return []

        first = values[0]
        last = values[-1]
        if first == 0:
            return []

        pct_change = (last - first) / abs(first) * 100

        if abs(pct_change) < 10:
            return []  # No meaningful trend

        direction = "increasing" if pct_change > 0 else "decreasing"
        severity = InsightSeverity.INFO

        rule_id = f"time_series_trend-{direction}{suffix}"
        evidence = InsightEvidence(
            metric="pct_change_first_to_last",
            value=round(pct_change, 1),
            unit="percent",
            source_artifact="visualization_spec",
            source_path=f"time_series:{label}",
            explanation=(
                f"First value: {first}, last value: {last}. "
                f"Change of {round(pct_change, 1)}% from start to end of series."
            ),
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.TIME_SERIES,
                severity=severity,
                confidence=InsightConfidence.LOW,
                title=f"Apparent {direction} trend in '{label}' ({round(pct_change, 1)}%)",
                summary=f"Time series '{label}' shows a {round(pct_change, 1)}% {direction} trend from first to last observation.",
                explanation=(
                    f"Time series '{label}' shows values moving from {first} to {last} "
                    f"({round(pct_change, 1)}% {direction}). "
                    "This is a simple first-to-last comparison and does not constitute statistical trend confirmation. "
                    "CropLens does not perform formal trend tests (e.g. Mann-Kendall) or seasonality decomposition."
                ),
                evidence=[evidence],
                impact="Apparent trends may reflect seasonal patterns, collection artifacts, or genuine changes.",
                recommended_action=(
                    "Apply a formal statistical trend test (e.g. Mann-Kendall) for confirmation. "
                    "Investigate whether the trend is due to data collection changes rather than a real signal."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

