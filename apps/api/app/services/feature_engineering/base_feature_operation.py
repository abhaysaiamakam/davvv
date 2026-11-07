"""
Base interface for CropLens feature engineering operations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from app.schemas.feature_engineering import (
    FeatureModality,
    FeatureOperationConfig,
    FeatureOperationDefinition,
    FeatureOperationType,
    FeaturePreviewResult,
)


class BaseFeatureOperation(ABC):
    """Abstract base class for all CropLens feature engineering operations."""

    @property
    @abstractmethod
    def operation_type(self) -> FeatureOperationType:
        """Canonical operation type identifier."""
        pass

    @property
    @abstractmethod
    def modality(self) -> FeatureModality:
        """Target dataset modality."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable title."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description of operation semantics."""
        pass

    @property
    def supported_file_types(self) -> List[str]:
        return []

    @property
    def known_limitations(self) -> List[str]:
        return []

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {}

    def get_definition(self) -> FeatureOperationDefinition:
        return FeatureOperationDefinition(
            operation_type=self.operation_type,
            display_name=self.display_name,
            description=self.description,
            modality=self.modality,
            parameters_schema=self.parameters_schema,
            supported_file_types=self.supported_file_types,
            known_limitations=self.known_limitations,
        )

    @abstractmethod
    def validate_parameters(self, config: FeatureOperationConfig) -> List[str]:
        """Validate parameter configuration."""
        pass

    @abstractmethod
    def preview(
        self, dataset_root: Path, config: FeatureOperationConfig
    ) -> FeaturePreviewResult:
        """Simulate feature transformation without mutating disk."""
        pass

    @abstractmethod
    def apply(
        self, dataset_root: Path, config: FeatureOperationConfig
    ) -> Dict[str, Any]:
        """Execute feature transformation in-place on dataset files."""
        pass
