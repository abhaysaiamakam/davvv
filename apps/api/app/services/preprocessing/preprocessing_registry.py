"""
M8 — Preprocessing Operations Registry.

Maintains the authoritative catalog of supported data cleaning operations across all modalities.
Supports modular addition of new operations without modifying the core orchestration pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.core.errors import PreprocessingOperationNotFoundError
from app.schemas.preprocessing import (
    OperationDefinition,
    PreprocessingModality,
    PreprocessingOperationType,
)
from app.services.preprocessing.annotation_preprocessing import (
    FilterAnnotationClassesOperation,
    RescaleAnnotationsOperation,
    ValidateAndClipBoundingBoxesOperation,
    _find_coco_files,
    _find_yolo_files,
)
from app.services.preprocessing.base_operation import BasePreprocessingOperation
from app.services.preprocessing.image_preprocessing import (
    ConvertColorModeOperation,
    ConvertFormatOperation,
    ExcludeCorruptImagesOperation,
    FilterClassesOperation,
    RemoveExactDuplicatesOperation,
    ResizeImagesOperation,
    _find_image_files,
)
from app.services.preprocessing.tabular_preprocessing import (
    CategoricalEncodingOperation,
    ColumnSelectionOperation,
    DropMissingColumnsOperation,
    DropMissingRowsOperation,
    MissingValueImputationOperation,
    NumericScalingOperation,
    OutlierHandlingOperation,
    RemoveDuplicatesOperation,
    RowFilteringOperation,
    StringNormalizationOperation,
    TypeConversionOperation,
    ValueReplacementOperation,
    _read_table,
    _resolve_tabular_files,
)
from app.services.preprocessing.time_series_preprocessing import (
    HandleDuplicateTimestampsOperation,
    InterpolateMissingTimestampsOperation,
    ParseTimestampsOperation,
    SortTimestampsOperation,
    _parse_iso,
)

logger = logging.getLogger(__name__)


class PreprocessingRegistry:
    """Central registry maintaining and dispatching preprocessing operation handlers."""

    def __init__(self):
        self._operations: Dict[PreprocessingOperationType, BasePreprocessingOperation] = {}
        self._register_default_operations()

    def register(self, operation: BasePreprocessingOperation) -> None:
        """Register a new preprocessing operation implementation."""
        self._operations[operation.operation_type] = operation
        logger.debug(f"Registered preprocessing operation: {operation.operation_type.value}")

    def _register_default_operations(self) -> None:
        # Tabular operations
        self.register(MissingValueImputationOperation())
        self.register(DropMissingRowsOperation())
        self.register(DropMissingColumnsOperation())
        self.register(RemoveDuplicatesOperation())
        self.register(OutlierHandlingOperation())
        self.register(TypeConversionOperation())
        self.register(CategoricalEncodingOperation())
        self.register(NumericScalingOperation())
        self.register(ColumnSelectionOperation())
        self.register(RowFilteringOperation())
        self.register(ValueReplacementOperation())
        self.register(StringNormalizationOperation())

        # Image operations
        self.register(ResizeImagesOperation())
        self.register(ConvertFormatOperation())
        self.register(ConvertColorModeOperation())
        self.register(RemoveExactDuplicatesOperation())
        self.register(ExcludeCorruptImagesOperation())
        self.register(FilterClassesOperation())

        # Time-Series operations
        self.register(ParseTimestampsOperation())
        self.register(SortTimestampsOperation())
        self.register(HandleDuplicateTimestampsOperation())
        self.register(InterpolateMissingTimestampsOperation())

        # Annotation operations
        self.register(FilterAnnotationClassesOperation())
        self.register(ValidateAndClipBoundingBoxesOperation())
        self.register(RescaleAnnotationsOperation())

    def get_operation(self, operation_type: PreprocessingOperationType) -> BasePreprocessingOperation:
        """Lookup an operation implementation by canonical type."""
        op = self._operations.get(operation_type)
        if not op:
            raise PreprocessingOperationNotFoundError(operation_type.value)
        return op

    def list_operations(
        self, modality: Optional[PreprocessingModality] = None
    ) -> List[OperationDefinition]:
        """Return definitions for all registered operations or those matching a modality."""
        ops = list(self._operations.values())
        if modality:
            ops = [o for o in ops if o.modality == modality]
        return [o.get_definition() for o in ops]

    def detect_modalities(self, dataset_root: Path) -> List[PreprocessingModality]:
        """Inspect directory contents to detect present data modalities."""
        if not dataset_root.exists():
            return []

        modalities: Set[PreprocessingModality] = set()

        # Check for images
        images = _find_image_files(dataset_root)
        if images:
            modalities.add(PreprocessingModality.IMAGE)

        # Check for tabular files
        tabular_files = _resolve_tabular_files(dataset_root)
        if tabular_files:
            modalities.add(PreprocessingModality.TABULAR)

            # Check if any tabular file contains temporal columns
            for tf in tabular_files[:3]:
                try:
                    headers, rows = _read_table(tf)
                    for h in headers:
                        h_low = h.lower()
                        if any(k in h_low for k in ("time", "date", "year", "month", "day", "timestamp")):
                            # Check if values parse as date
                            sample_vals = [r.get(h, "") for r in rows[:5] if r.get(h, "")]
                            if sample_vals and any(_parse_iso(v) is not None for v in sample_vals):
                                modalities.add(PreprocessingModality.TIME_SERIES)
                                break
                except Exception:
                    pass

        # Check for annotations
        coco = _find_coco_files(dataset_root)
        yolo = _find_yolo_files(dataset_root)
        if coco or yolo:
            modalities.add(PreprocessingModality.ANNOTATION)

        # Sort for determinism
        order = [
            PreprocessingModality.IMAGE,
            PreprocessingModality.TABULAR,
            PreprocessingModality.TIME_SERIES,
            PreprocessingModality.ANNOTATION,
        ]
        return [m for m in order if m in modalities]

    def get_available_operations_for_dataset(self, dataset_root: Path) -> List[OperationDefinition]:
        """Return operation definitions suitable for the modalities detected in dataset_root."""
        modalities = self.detect_modalities(dataset_root)
        if not modalities:
            # Fallback: return tabular and image definitions
            modalities = [PreprocessingModality.TABULAR, PreprocessingModality.IMAGE]

        ops = [o for o in self._operations.values() if o.modality in modalities]
        return [o.get_definition() for o in ops]


preprocessing_registry = PreprocessingRegistry()
