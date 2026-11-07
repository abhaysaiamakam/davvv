"""
M7 — Insights Service.

Coordinates insight generation, persistence, retrieval, and lifecycle events
for CropLens datasets using the InsightRegistry and storage abstraction.
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.errors import DatasetInsightsNotFoundError, DatasetNotFoundError, InsightNotFoundError
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.insights import (
    DatasetInsight,
    InsightCategory,
    InsightCollection,
    InsightCollectionResponse,
    InsightSeverity,
)
from app.services.insights.insights_registry import insight_registry
from app.storage.base import StorageBackend
from app.storage.local import get_storage_backend

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {
    InsightSeverity.CRITICAL: 0,
    InsightSeverity.HIGH: 1,
    InsightSeverity.MEDIUM: 2,
    InsightSeverity.LOW: 3,
    InsightSeverity.INFO: 4,
}


class InsightsService:
    """Service managing insight generation and lifecycle for CropLens datasets."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or get_storage_backend()

    def generate_insights(
        self,
        dataset_id: str,
        version_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> InsightCollection:
        """
        Generate M7 insights for a dataset version. Persists the collection
        to disk and emits lifecycle events.
        """
        # Local imports to prevent circular dependencies
        from app.services.dataset_service import dataset_service
        from app.services.analysis_service import analysis_service
        from app.services.data_quality_service import data_quality_service
        from app.services.eda_service import eda_service
        from app.services.visualizations import visualization_service

        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        # Resolve version
        if not version_id:
            latest_v = dataset_service.get_latest_version(dataset_id)
            ver = latest_v.version_id if latest_v else "v1"
        else:
            ver = version_id

        # Return cached collection unless force_refresh
        if not force_refresh:
            existing = self.storage.load_insights(dataset_id, ver)
            if existing and existing.get("status") == "completed":
                try:
                    return InsightCollection.model_validate(existing)
                except Exception:
                    pass

        # Build context dict from upstream artifacts
        context: Dict[str, Any] = {
            "dataset": dataset,
            "version_id": ver,
        }

        source_analysis_id: Optional[str] = None
        source_quality_id: Optional[str] = None
        source_eda_id: Optional[str] = None

        try:
            analysis = analysis_service.get_latest_analysis_for_dataset(dataset_id)
            context["analysis"] = analysis
            if analysis:
                source_analysis_id = analysis.id
        except Exception:
            context["analysis"] = None

        try:
            quality = data_quality_service.get_latest_assessment_for_dataset(dataset_id)
            context["quality"] = quality
            if quality:
                source_quality_id = quality.id
        except Exception:
            context["quality"] = None

        try:
            eda = eda_service.get_latest_report_for_dataset(dataset_id)
            context["eda"] = eda
            if eda:
                source_eda_id = eda.id
        except Exception:
            context["eda"] = None

        try:
            vis_col = visualization_service.get_visualizations(dataset_id, version_id=ver)
            context["visualizations"] = vis_col
        except Exception:
            context["visualizations"] = None

        # Resolve dataset directory for file-based analyzers
        try:
            resolved_path = self.storage.resolve_dataset_path(dataset)
            if resolved_path and resolved_path.exists():
                context["dataset_dir"] = resolved_path
        except Exception:
            context["dataset_dir"] = None

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        collection_id = f"ins-col-{dataset_id}-{ver}-{uuid.uuid4().hex[:8]}"

        try:
            # Run all registered analyzers
            raw_insights = insight_registry.analyze_all(dataset_id, ver, context)

            # Sort by severity
            sorted_insights = sorted(
                raw_insights,
                key=lambda i: (_SEVERITY_ORDER.get(i.severity, 99), i.category.value),
            )

            collection = InsightCollection(
                id=collection_id,
                dataset_id=dataset_id,
                dataset_version=ver,
                status="completed",
                total=len(sorted_insights),
                items=sorted_insights,
                error_message=None,
                generated_at=now,
                source_analysis_id=source_analysis_id,
                source_quality_id=source_quality_id,
                source_eda_id=source_eda_id,
            )

            # Persist to disk
            self.storage.save_insights(dataset_id, ver, collection.model_dump())

            # Emit lifecycle event
            event_bus.emit(
                DatasetEventType.DATASET_INSIGHTS_COMPLETED,
                dataset_id=dataset_id,
                version_id=ver,
                payload={
                    "collection_id": collection_id,
                    "total_insights": len(sorted_insights),
                    "generated_at": now,
                },
            )

            logger.info(
                f"[InsightsService] Generated {len(sorted_insights)} insight(s) for {dataset_id}/{ver}"
            )
            return collection

        except Exception as exc:
            logger.error(
                f"[InsightsService] Failed to generate insights for {dataset_id}/{ver}: {exc}",
                exc_info=True,
            )
            failed_col = InsightCollection(
                id=collection_id,
                dataset_id=dataset_id,
                dataset_version=ver,
                status="failed",
                total=0,
                items=[],
                error_message=str(exc),
                generated_at=now,
                source_analysis_id=source_analysis_id,
                source_quality_id=source_quality_id,
                source_eda_id=source_eda_id,
            )
            self.storage.save_insights(dataset_id, ver, failed_col.model_dump())
            event_bus.emit(
                DatasetEventType.DATASET_INSIGHTS_FAILED,
                dataset_id=dataset_id,
                version_id=ver,
                payload={"error_message": str(exc)},
            )
            return failed_col

    def get_insights(
        self,
        dataset_id: str,
        version_id: Optional[str] = None,
        category: Optional[InsightCategory] = None,
        severity: Optional[InsightSeverity] = None,
    ) -> InsightCollectionResponse:
        """
        Retrieve insights for a dataset, optionally filtered by category or severity.
        Triggers on-demand generation if no insights are persisted yet.
        """
        from app.services.dataset_service import dataset_service

        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        target_ver = version_id
        if not target_ver:
            latest_v = dataset_service.get_latest_version(dataset_id)
            target_ver = latest_v.version_id if latest_v else "v1"

        data = self.storage.load_insights(dataset_id, target_ver)
        if not data:
            raise DatasetInsightsNotFoundError(dataset_id)

        collection = InsightCollection.model_validate(data)
        items = collection.items

        if category is not None:
            items = [i for i in items if i.category == category]
        if severity is not None:
            items = [i for i in items if i.severity == severity]

        return InsightCollectionResponse(
            dataset_id=dataset_id,
            dataset_version=target_ver,
            status=collection.status,
            total=len(items),
            items=items,
            error_message=collection.error_message,
            filtered_category=category.value if category else None,
            filtered_severity=severity.value if severity else None,
        )

    def get_insight_by_id(
        self, dataset_id: str, insight_id: str
    ) -> DatasetInsight:
        """Retrieve a single insight by its insight_id."""
        # Try item index first (fast path)
        item_data = self.storage.load_insight_by_id(insight_id)
        if item_data:
            insight = DatasetInsight.model_validate(item_data)
            if insight.dataset_id == dataset_id:
                return insight

        # Fallback: scan latest collection
        data = self.storage.load_insights(dataset_id)
        if data:
            try:
                collection = InsightCollection.model_validate(data)
                for item in collection.items:
                    if item.insight_id == insight_id:
                        return item
            except Exception:
                pass

        raise InsightNotFoundError(insight_id)

    def get_latest_insights_for_dataset(
        self, dataset_id: str
    ) -> Optional[InsightCollection]:
        """Return the latest InsightCollection for a dataset, or None."""
        data = self.storage.load_insights(dataset_id)
        if not data:
            return None
        try:
            return InsightCollection.model_validate(data)
        except Exception:
            return None

    def regenerate_insights(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> InsightCollectionResponse:
        """Force recomputation of insights for a dataset version."""
        collection = self.generate_insights(dataset_id, version_id=version_id, force_refresh=True)
        return InsightCollectionResponse(
            dataset_id=dataset_id,
            dataset_version=collection.dataset_version,
            status=collection.status,
            total=collection.total,
            items=collection.items,
            error_message=collection.error_message,
        )


# Global insights service singleton
insights_service = InsightsService()

