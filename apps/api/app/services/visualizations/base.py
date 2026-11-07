"""
Base visualizer interface for CropLens Visualization Specification Engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.schemas.visualization import VisualizationSpecification


class BaseVisualizer(ABC):
    """Abstract visualizer provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this visualizer provider."""
        pass

    @abstractmethod
    def can_handle(self, dataset_id: str, version_id: str, context: Dict[str, Any]) -> bool:
        """Determine whether this visualizer is applicable for the given dataset context."""
        pass

    @abstractmethod
    def generate(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[VisualizationSpecification]:
        """Generate structured visualization specifications for the dataset."""
        pass

