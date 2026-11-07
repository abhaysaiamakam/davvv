"""
Chart Selection Registry for CropLens.

Coordinates extensible visualizer plugins, determines applicable visualizers
based on actual dataset characteristics, and generates specifications.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.schemas.visualization import VisualizationSpecification
from app.services.visualizations.base import BaseVisualizer
from app.services.visualizations.image_visualizer import ImageClassificationVisualizer
from app.services.visualizations.tabular_visualizer import TabularVisualizer
from app.services.visualizations.time_series_visualizer import TimeSeriesVisualizer
from app.services.visualizations.annotation_visualizer import AnnotationVisualizer

logger = logging.getLogger(__name__)


class ChartSelectionRegistry:
    """Registry maintaining active visualization plugins and orchestrating selection."""

    def __init__(self):
        self._visualizers: List[BaseVisualizer] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in domain visualizers."""
        self.register(ImageClassificationVisualizer())
        self.register(TabularVisualizer())
        self.register(TimeSeriesVisualizer())
        self.register(AnnotationVisualizer())

    def register(self, visualizer: BaseVisualizer) -> None:
        """Register a new visualizer provider."""
        self._visualizers.append(visualizer)
        logger.debug(f"Registered visualizer: {visualizer.name}")

    def select_and_generate(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[VisualizationSpecification]:
        """
        Evaluate dataset context across all registered visualizers and generate specifications.
        Prevents duplicate visualization IDs and isolates individual visualizer failures.
        """
        all_specs: List[VisualizationSpecification] = []
        seen_ids = set()

        for viz in self._visualizers:
            try:
                if viz.can_handle(dataset_id, version_id, context):
                    logger.info(f"Visualizer '{viz.name}' selected for dataset '{dataset_id}' ({version_id})")
                    specs = viz.generate(dataset_id, version_id, context)
                    for s in specs:
                        if s.visualization_id not in seen_ids:
                            seen_ids.add(s.visualization_id)
                            all_specs.append(s)
            except Exception as exc:
                logger.error(f"Visualizer '{viz.name}' encountered error on dataset '{dataset_id}': {exc}", exc_info=True)

        return all_specs


# Global chart selection registry singleton
chart_selection_registry = ChartSelectionRegistry()

