"""
M9 — Feature Engineering Registry.

Maintains the authoritative catalog of supported feature engineering, transformation,
and feature selection operations across all modalities.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.core.errors import PreprocessingOperationNotFoundError
from app.schemas.feature_engineering import (
    FeatureOperationDefinition,
    FeatureModality,
    FeatureOperationType,
    FeatureMetadata,
)
from app.services.feature_engineering.base_feature_operation import BaseFeatureOperation
from app.services.feature_engineering.tabular_feature_operations import (
    MathematicalTransformOperation,
    DateTimeExtractionOperation,
    VarianceThresholdSelectionOperation,
    CorrelationRedundancyOperation,
    PrincipalComponentAnalysisOperation,
)
from app.services.feature_engineering.image_time_series_feature_operations import (
    LagFeaturesOperation,
    ImageMetadataExtractionOperation,
    AnnotationMetadataExtractionOperation,
)
from app.services.preprocessing.preprocessing_registry import preprocessing_registry

logger = logging.getLogger(__name__)


class FeatureRegistry:
    """Central registry for feature engineering and selection operations."""

    def __init__(self):
        self._operations: Dict[FeatureOperationType, BaseFeatureOperation] = {}
        self._register_default_operations()

    def register(self, operation: BaseFeatureOperation) -> None:
        self._operations[operation.operation_type] = operation

    def _register_default_operations(self) -> None:
        self.register(MathematicalTransformOperation())
        self.register(DateTimeExtractionOperation())
        self.register(VarianceThresholdSelectionOperation())
        self.register(CorrelationRedundancyOperation())
        self.register(PrincipalComponentAnalysisOperation())
        self.register(LagFeaturesOperation())
        self.register(ImageMetadataExtractionOperation())
        self.register(AnnotationMetadataExtractionOperation())

    def get_operation(self, operation_type: FeatureOperationType) -> BaseFeatureOperation:
        op = self._operations.get(operation_type)
        if not op:
            raise PreprocessingOperationNotFoundError(operation_type.value)
        return op

    def list_operations(self, modality: Optional[FeatureModality] = None) -> List[FeatureOperationDefinition]:
        ops = list(self._operations.values())
        if modality:
            ops = [o for o in ops if o.modality == modality]
        return [o.get_definition() for o in ops]

    def discover_features(self, dataset_root: Path) -> List[FeatureMetadata]:
        """Inspect dataset files (tabular headers, image stats) to discover existing features."""
        features: List[FeatureMetadata] = []
        if not dataset_root.exists():
            return features

        from app.services.preprocessing.tabular_preprocessing import _resolve_tabular_files, _read_table, _is_column_numeric
        tab_files = _resolve_tabular_files(dataset_root)
        if tab_files:
            try:
                headers, rows = _read_table(tab_files[0])
                now = "2026-01-01T00:00:00Z"
                for h in headers:
                    is_num = _is_column_numeric(rows, h)
                    ftype = "numeric" if is_num else "categorical"
                    dtype = "float64" if is_num else "object"
                    features.append(
                        FeatureMetadata(
                            feature_id=f"feat-{h}",
                            feature_name=h,
                            source_columns=[h],
                            feature_type=ftype,
                            data_type=dtype,
                            created_at=now,
                            description=f"Discovered column '{h}' from tabular source",
                        )
                    )
            except Exception:
                pass

        return features


feature_registry = FeatureRegistry()
