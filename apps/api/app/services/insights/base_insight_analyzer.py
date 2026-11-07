"""
Base interface for M7 insight analyzers.

Each analyzer inspects a specific facet of the dataset context and returns
a list of evidence-backed DatasetInsight objects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.schemas.insights import DatasetInsight


class BaseInsightAnalyzer(ABC):
    """Abstract base class for all M7 insight analyzers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this analyzer."""
        pass

    @abstractmethod
    def can_handle(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> bool:
        """
        Determine whether this analyzer has sufficient context to run.
        Return False if required upstream artifacts are absent.
        """
        pass

    @abstractmethod
    def analyze(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[DatasetInsight]:
        """
        Generate and return a list of insights for this dataset.
        Must never raise — catch internal exceptions and return an empty list.
        """
        pass

