"""
M7 — Insights service package for CropLens.

Exports the insights service, registry, base class, and all built-in analyzers.
"""
from app.services.insights.base_insight_analyzer import BaseInsightAnalyzer
from app.services.insights.image_insights import ImageInsightAnalyzer
from app.services.insights.tabular_insights import TabularInsightAnalyzer
from app.services.insights.time_series_insights import TimeSeriesInsightAnalyzer
from app.services.insights.annotation_insights import AnnotationInsightAnalyzer
from app.services.insights.insights_registry import InsightRegistry, insight_registry
from app.services.insights.insights_service import InsightsService, insights_service

__all__ = [
    "BaseInsightAnalyzer",
    "ImageInsightAnalyzer",
    "TabularInsightAnalyzer",
    "TimeSeriesInsightAnalyzer",
    "AnnotationInsightAnalyzer",
    "InsightRegistry",
    "insight_registry",
    "InsightsService",
    "insights_service",
]

