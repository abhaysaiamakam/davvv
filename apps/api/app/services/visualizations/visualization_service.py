"""
Visualization Service for CropLens.

Coordinates the generation, validation, persistence, retrieval, and lifecycle events
for dataset visualization specifications.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.core.errors import (
    DatasetNotFoundError,
    DatasetVisualizationsNotFoundError,
    VisualizationNotFoundError,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.visualization import (
    ChartType,
    VisualizationCategory,
    VisualizationCollection,
    VisualizationCollectionResponse,
    VisualizationSpecification,
)
from app.services.visualizations.registry import chart_selection_registry
from app.storage.base import StorageBackend
from app.storage.local import get_storage_backend

logger = logging.getLogger(__name__)


class VisualizationService:
    """Service managing visualization generation and lifecycle for CropLens datasets."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or get_storage_backend()

    def generate_visualizations(
        self,
        dataset_id: str,
        version_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> VisualizationCollection:
        """
        Generate visualization specifications from existing M2, M3, and M4 analytical artifacts
        and actual dataset files. Persists the collection to disk and emits lifecycle events.
        """
        # Local imports to prevent circular dependencies
        from app.services.dataset_service import dataset_service
        from app.services.analysis_service import analysis_service
        from app.services.data_quality_service import data_quality_service
        from app.services.eda_service import eda_service

        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        # Resolve version
        if not version_id:
            latest_v = dataset_service.get_latest_version(dataset_id)
            ver = latest_v.version_id if latest_v else "v1"
        else:
            ver = version_id

        # Check existing collection unless force_refresh
        if not force_refresh:
            existing_data = self.storage.load_visualizations(dataset_id, ver)
            if existing_data and existing_data.get("status") == "completed":
                try:
                    return VisualizationCollection.model_validate(existing_data)
                except Exception:
                    pass

        # Build context
        context: Dict[str, Any] = {
            "dataset": dataset,
            "version_id": ver,
        }

        # Upstream M2 analysis
        try:
            context["analysis"] = analysis_service.get_latest_analysis_for_dataset(dataset_id)
        except Exception:
            context["analysis"] = None

        # Upstream M3 quality assessment
        try:
            context["quality"] = data_quality_service.get_latest_assessment_for_dataset(dataset_id)
        except Exception:
            context["quality"] = None

        # Upstream M4 EDA report
        try:
            context["eda"] = eda_service.get_latest_report_for_dataset(dataset_id)
        except Exception:
            context["eda"] = None

        # Resolve dataset directory for file-based visualizers (tabular, annotations)
        try:
            resolved_path = self.storage.resolve_dataset_path(dataset)
            if resolved_path and resolved_path.exists():
                context["dataset_dir"] = resolved_path
        except Exception:
            context["dataset_dir"] = None

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        collection_id = f"vis-col-{dataset_id}-{ver}-{uuid.uuid4().hex[:8]}"

        try:
            # Generate specifications via registry
            specs = chart_selection_registry.select_and_generate(dataset_id, ver, context)

            collection = VisualizationCollection(
                id=collection_id,
                dataset_id=dataset_id,
                dataset_version=ver,
                total=len(specs),
                status="completed",
                items=specs,
                error_message=None,
                generated_at=now,
            )

            # Persist to disk
            self.storage.save_visualizations(dataset_id, ver, collection.model_dump())

            # Emit completion event
            event_bus.emit(
                DatasetEventType.DATASET_VISUALIZATION_COMPLETED,
                dataset_id=dataset_id,
                version_id=ver,
                payload={
                    "collection_id": collection_id,
                    "total_visualizations": len(specs),
                    "generated_at": now,
                },
            )
            return collection

        except Exception as exc:
            logger.error(f"Failed to generate visualizations for {dataset_id}/{ver}: {exc}", exc_info=True)
            failed_col = VisualizationCollection(
                id=collection_id,
                dataset_id=dataset_id,
                dataset_version=ver,
                total=0,
                status="failed",
                items=[],
                error_message=str(exc),
                generated_at=now,
            )
            self.storage.save_visualizations(dataset_id, ver, failed_col.model_dump())
            event_bus.emit(
                DatasetEventType.DATASET_VISUALIZATION_FAILED,
                dataset_id=dataset_id,
                version_id=ver,
                payload={"error_message": str(exc)},
            )
            return failed_col

    def get_visualizations(
        self,
        dataset_id: str,
        version_id: Optional[str] = None,
        category: Optional[VisualizationCategory] = None,
        chart_type: Optional[ChartType] = None,
    ) -> VisualizationCollectionResponse:
        """
        Retrieve visualizations for a dataset, optionally filtered by category or chart type.
        If no visualizations are persisted yet, generates them on demand if analytics exist.
        """
        # Local import to prevent circular dependency
        from app.services.dataset_service import dataset_service

        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        target_ver = version_id
        if not target_ver:
            latest_v = dataset_service.get_latest_version(dataset_id)
            target_ver = latest_v.version_id if latest_v else "v1"

        data = self.storage.load_visualizations(dataset_id, target_ver)
        if not data:
            # Attempt on-demand generation
            collection = self.generate_visualizations(dataset_id, version_id=target_ver)
        else:
            collection = VisualizationCollection.model_validate(data)

        items = collection.items
        if category:
            items = [item for item in items if item.category == category]
        if chart_type:
            items = [item for item in items if item.chart_type == chart_type]

        return VisualizationCollectionResponse(
            dataset_id=dataset_id,
            dataset_version=target_ver,
            total=len(items),
            status=collection.status,
            items=items,
            error_message=collection.error_message,
        )

    def get_visualization(
        self, dataset_id: str, visualization_id: str
    ) -> VisualizationSpecification:
        """Retrieve a single visualization specification by ID."""
        response = self.get_visualizations(dataset_id)
        for item in response.items:
            if item.visualization_id == visualization_id:
                return item

        raise VisualizationNotFoundError(visualization_id)

    def regenerate_visualizations(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> VisualizationCollectionResponse:
        """Force recomputation of all visualizations for a dataset version."""
        collection = self.generate_visualizations(dataset_id, version_id=version_id, force_refresh=True)
        return VisualizationCollectionResponse(
            dataset_id=dataset_id,
            dataset_version=collection.dataset_version,
            total=collection.total,
            status=collection.status,
            items=collection.items,
            error_message=collection.error_message,
        )


# Global visualization service singleton
visualization_service = VisualizationService()

