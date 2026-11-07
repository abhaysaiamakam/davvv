"""
Base interface for CropLens preprocessing operations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from app.schemas.preprocessing import (
    OperationDefinition,
    OperationPreviewResult,
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingOperationType,
)


class BasePreprocessingOperation(ABC):
    """Abstract base class for all CropLens preprocessing operations."""

    @property
    @abstractmethod
    def operation_type(self) -> PreprocessingOperationType:
        """Canonical operation type identifier."""
        pass

    @property
    @abstractmethod
    def modality(self) -> PreprocessingModality:
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
        """Detailed description of the operation behavior and semantics."""
        pass

    @property
    def supported_file_types(self) -> List[str]:
        """Supported file extensions."""
        return []

    @property
    def known_limitations(self) -> List[str]:
        """Documented limitations, boundaries, or assumptions."""
        return []

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema dictionary describing required and optional parameters."""
        return {}

    def get_definition(self) -> OperationDefinition:
        """Return the public catalog descriptor for this operation."""
        return OperationDefinition(
            operation_type=self.operation_type,
            display_name=self.display_name,
            description=self.description,
            modality=self.modality,
            parameters_schema=self.parameters_schema,
            supported_file_types=self.supported_file_types,
            known_limitations=self.known_limitations,
        )

    @abstractmethod
    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        """
        Validate operation configuration parameters.
        Returns a list of validation error messages (empty list if valid).
        """
        pass

    @abstractmethod
    def preview(
        self, dataset_root: Path, config: PreprocessingOperationConfig
    ) -> OperationPreviewResult:
        """
        Simulate the operation against the dataset directory without modifying disk.
        Returns detailed before/after counts, metrics, and samples.
        """
        pass

    @abstractmethod
    def apply(
        self, dataset_root: Path, config: PreprocessingOperationConfig
    ) -> Dict[str, Any]:
        """
        Execute the transformation in-place on the provided isolated dataset directory.
        Returns execution statistics (e.g. affected_rows, affected_files, warnings).
        """
        pass

