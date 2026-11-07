"""
M7 — Insight Registry.

Coordinates extensible insight analyzers, determines applicable analyzers
based on dataset context, and aggregates their outputs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.schemas.insights import DatasetInsight
from app.services.insights.base_insight_analyzer import BaseInsightAnalyzer
from app.services.insights.image_insights import ImageInsightAnalyzer
from app.services.insights.tabular_insights import TabularInsightAnalyzer
from app.services.insights.time_series_insights import TimeSeriesInsightAnalyzer
from app.services.insights.annotation_insights import AnnotationInsightAnalyzer

logger = logging.getLogger(__name__)


class InsightRegistry:
    """Registry coordinating active insight analyzers for the M7 engine."""

    def __init__(self):
        self._analyzers: List[BaseInsightAnalyzer] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in domain analyzers."""
        self.register(ImageInsightAnalyzer())
        self.register(TabularInsightAnalyzer())
        self.register(TimeSeriesInsightAnalyzer())
        self.register(AnnotationInsightAnalyzer())

    def register(self, analyzer: BaseInsightAnalyzer) -> None:
        """Register an additional insight analyzer."""
        self._analyzers.append(analyzer)
        logger.debug(f"Registered insight analyzer: {analyzer.name}")

    def analyze_all(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[DatasetInsight]:
        """
        Evaluate all registered analyzers against the dataset context.
        Individual analyzer failures are isolated — a single crash does not stop others.
        Returns deduplicated insights ordered by severity.
        """
        all_insights: List[DatasetInsight] = []
        seen_ids: set = set()

        for analyzer in self._analyzers:
            try:
                if analyzer.can_handle(dataset_id, version_id, context):
                    logger.info(
                        f"[InsightRegistry] Analyzer '{analyzer.name}' selected for "
                        f"dataset '{dataset_id}' ({version_id})"
                    )
                    results = analyzer.analyze(dataset_id, version_id, context)
                    for insight in results:
                        if insight.insight_id not in seen_ids:
                            seen_ids.add(insight.insight_id)
                            all_insights.append(insight)
            except Exception as exc:
                logger.error(
                    f"[InsightRegistry] Analyzer '{analyzer.name}' failed for "
                    f"dataset '{dataset_id}': {exc}",
                    exc_info=True,
                )

        return all_insights


# Global singleton
insight_registry = InsightRegistry()

