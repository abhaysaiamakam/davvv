"""
M10 — Analytical Report Orchestration & Export Service.

Collects persisted artifacts across M2–M9, builds multi-section Analytical Reports,
executes readiness evaluations, generates reproducible methodology, and exports JSON/PDF.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.errors import (
    DatasetNotFoundError,
    ReportNotFoundError,
    VersionNotFoundError,
    ReportExportError,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.reports import (
    AnalyticalReport,
    DatasetOverviewSection,
    EdaSection,
    ExecutiveSummary,
    FeatureEngineeringSection,
    InsightsSection,
    MethodologySection,
    PreprocessingSection,
    QualitySection,
    ReportExportFormat,
    ReportGenerateRequest,
    ReportListResponse,
    ReportProvenance,
    ReportStatus,
)
from app.schemas.readiness import TaskContext
from app.storage.base import StorageBackend
from app.storage.local import storage_backend
from app.services.dataset_service import dataset_service
from app.services.readiness_service import readiness_service
from app.services.methodology_builder import methodology_builder
from app.services.pdf_export_service import pdf_export_service

logger = logging.getLogger(__name__)


class ReportService:
    """Orchestrates unified analytical report composition and export."""

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or storage_backend

    def generate_report(self, req: ReportGenerateRequest) -> AnalyticalReport:
        """Compose a unified, multi-section evidence-backed analytical report for a dataset version."""
        dataset = dataset_service.get_dataset(req.dataset_id)
        if not dataset:
            raise DatasetNotFoundError(req.dataset_id)

        # Resolve target version
        if req.version_id:
            version = dataset_service.get_version(req.dataset_id, req.version_id)
            if not version:
                raise VersionNotFoundError(req.dataset_id, req.version_id)
            target_version_id = version.version_id
            ver_num = version.version_number
        else:
            latest = dataset_service.get_latest_version(req.dataset_id)
            target_version_id = latest.version_id if latest else "v1"
            ver_num = latest.version_number if latest else 1

        # Check existing cached reports if not force_refresh
        if not req.force_refresh:
            existing_reports = self.storage.list_analytical_reports(req.dataset_id, target_version_id)
            if existing_reports:
                return AnalyticalReport.model_validate(existing_reports[0])

        dataset_dir = self.storage.resolve_dataset_path(dataset)
        from app.services.preprocessing.preprocessing_registry import preprocessing_registry
        modalities = preprocessing_registry.detect_modalities(dataset_dir)
        primary_modality = modalities[0].value if modalities else "tabular"

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_id = f"rep-{req.dataset_id}-{target_version_id}-{uuid.uuid4().hex[:6]}"

        # Collect artifacts across M2 - M9
        readiness_res = readiness_service.assess_readiness(req.dataset_id, target_version_id, req.task_context)
        quality_res = dataset_service.get_latest_quality_assessment(req.dataset_id)
        eda_res = dataset_service.get_latest_eda_report(req.dataset_id)
        
        # Insights (M7)
        try:
            from app.services.insights import insights_service
            insights_col = insights_service.get_insights(req.dataset_id, target_version_id)
            insights_list = [i.model_dump() for i in insights_col.insights]
            category_counts = insights_col.category_counts
        except Exception:
            insights_list = []
            category_counts = {}

        # Visualizations (M4 engine)
        try:
            from app.services.visualizations import visualization_service
            vis_col = visualization_service.get_visualizations(req.dataset_id, target_version_id)
            vis_refs = [v.id for v in vis_col.visualizations]
        except Exception:
            vis_refs = []

        # Preprocessing & Feature Engineering History (M8 & M9)
        prep_history = self.storage.list_persisted_preprocessing_history(req.dataset_id)
        
        try:
            from app.services.feature_engineering.feature_engineering_service import feature_engineering_service
            feat_history_res = feature_engineering_service.list_feature_history(req.dataset_id)
            feat_history = [item.model_dump() for item in feat_history_res.items]
        except Exception:
            feat_history = []

        # Discover columns / classes
        from app.services.feature_engineering.feature_registry import feature_registry
        discovered_feats = feature_registry.discover_features(dataset_dir)
        cols = [f.feature_name for f in discovered_feats]
        classes = dataset.discovery.classes if dataset.discovery else []
        class_names = [c.class_name for c in classes]

        # ---------------------------------------------------------------------
        # Construct Section Models
        # ---------------------------------------------------------------------
        exec_summary = ExecutiveSummary(
            dataset_name=dataset.name,
            dataset_modality=primary_modality,
            dataset_version=target_version_id,
            total_files=dataset.total_images or (val_res.total_discovered_images if (val_res := dataset.validation) else 0),
            total_bytes=sum(c.image_count * 1024 for c in classes) if classes else 1024 * 1024,
            main_objective=req.task_context.analytical_goal if req.task_context and req.task_context.analytical_goal else "Comprehensive dataset intelligence & preparation for machine learning",
            key_findings=readiness_res.key_strengths or ["Dataset cataloged and structural integrity verified."],
            quality_concerns=readiness_res.critical_blockers or [d.warnings[0] for d in readiness_res.dimensions if d.warnings] or ["No severe structural blockers identified."],
            readiness_status=readiness_res.overall_status,
            recommended_next_steps=readiness_res.recommendations or ["Proceed to model training or downstream processing."],
        )

        ds_overview = DatasetOverviewSection(
            dataset_id=req.dataset_id,
            dataset_name=dataset.name,
            version_id=target_version_id,
            version_number=ver_num,
            modality=primary_modality,
            is_curated=dataset.is_curated,
            is_uploaded=dataset.is_uploaded,
            created_at=dataset.created_at,
            total_files=exec_summary.total_files,
            total_bytes=exec_summary.total_bytes,
            classes=class_names,
            columns=cols,
            content_fingerprint=dataset.content_fingerprint,
        )

        q_score = None
        q_tier = None
        q_imb_ratio = None
        q_findings = []
        if quality_res:
            if hasattr(quality_res, "quality_score"):
                q_score = int(quality_res.quality_score.overall_score)
                q_tier = quality_res.quality_score.quality_tier
                q_imb_ratio = quality_res.imbalance.imbalance_ratio
                q_findings = [f.model_dump() if hasattr(f, "model_dump") else f for f in quality_res.findings]
            elif isinstance(quality_res, dict):
                q_score = quality_res.get("overall_quality_score") or quality_res.get("quality_score", {}).get("overall_score")
                q_tier = quality_res.get("quality_tier") or quality_res.get("quality_score", {}).get("quality_tier")
                q_imb_ratio = quality_res.get("class_imbalance_ratio")
                q_findings = quality_res.get("findings", [])

        q_section = QualitySection(
            quality_score=q_score,
            quality_tier=q_tier,
            missing_values_count=0,
            corrupted_files_count=dataset.corrupted_image_files or 0,
            duplicate_count=dataset.duplicates.exact_duplicate_groups if dataset.duplicates else 0,
            class_imbalance_ratio=q_imb_ratio,
            findings=q_findings,
            warnings=[d.warnings[0] for d in readiness_res.dimensions if d.warnings],
        )

        eda_summary = {}
        eda_findings = []
        if eda_res:
            if hasattr(eda_res, "model_dump"):
                eda_dict = eda_res.model_dump()
            elif isinstance(eda_res, dict):
                eda_dict = eda_res
            else:
                eda_dict = {}
            eda_summary = eda_dict.get("summary", {})
            eda_findings = eda_dict.get("findings", [])

        eda_section = EdaSection(
            distributions_summary=eda_summary,
            relationships_summary={},
            visualization_count=len(vis_refs),
            visualization_refs=vis_refs,
            eda_findings=eda_findings,
        )

        insights_section = InsightsSection(
            total_insights=len(insights_list),
            category_counts=category_counts,
            insights=insights_list,
        )

        prep_section = PreprocessingSection(
            operations_applied_count=sum(len(h.get("operations", [])) for h in prep_history),
            applied_operations=[op for h in prep_history for op in h.get("operations", [])],
            source_version_id=prep_history[0].get("source_version_id") if prep_history else None,
            derived_version_id=prep_history[0].get("derived_version_id") if prep_history else None,
            remaining_quality_concerns=[],
        )

        fe_section = FeatureEngineeringSection(
            generated_features_count=sum(len(h.get("generated_features", [])) for h in feat_history for op in h.get("operations", [])),
            features_generated=[f for h in feat_history for op in h.get("operations", []) for f in op.get("generated_features", [])],
            selected_features=[f for h in feat_history for op in h.get("operations", []) for f in op.get("source_features", [])],
            removed_features=[f for h in feat_history for op in h.get("operations", []) for f in op.get("removed_features", [])],
            feature_operations=[op for h in feat_history for op in h.get("operations", [])],
        )

        # Methodology (Section 5)
        methodology = methodology_builder.build_methodology(
            dataset_id=req.dataset_id,
            version_id=target_version_id,
            modality=primary_modality,
            analysis_artifact=dataset.discovery.model_dump() if dataset.discovery else None,
            quality_artifact=quality_res,
            eda_artifact=eda_res,
            preprocessing_history=prep_history,
            feature_history=feat_history,
            readiness_score=readiness_res.overall_score,
        )

        provenance = ReportProvenance(
            report_id=report_id,
            dataset_id=req.dataset_id,
            version_id=target_version_id,
            content_fingerprint=dataset.content_fingerprint,
            created_at=now_str,
            generator_status=ReportStatus.COMPLETED,
        )

        report = AnalyticalReport(
            report_id=report_id,
            dataset_id=req.dataset_id,
            version_id=target_version_id,
            title=req.title or f"CropLens Analytical Dossier & Readiness Report — {dataset.name}",
            provenance=provenance,
            executive_summary=exec_summary,
            dataset_overview=ds_overview,
            quality_section=q_section,
            eda_section=eda_section,
            insights_section=insights_section,
            preprocessing_section=prep_section,
            feature_engineering_section=fe_section,
            readiness_section=readiness_res,
            methodology_section=methodology,
            created_at=now_str,
        )

        self.storage.save_analytical_report(req.dataset_id, target_version_id, report_id, report.model_dump())

        event_bus.emit(
            DatasetEventType.DATASET_REPORT_GENERATED,
            dataset_id=req.dataset_id,
            version_id=target_version_id,
            payload={"report_id": report_id},
        )

        return report

    def get_report(self, report_id: str) -> AnalyticalReport:
        data = self.storage.load_analytical_report(report_id)
        if not data:
            raise ReportNotFoundError(report_id)
        return AnalyticalReport.model_validate(data)

    def list_reports(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> ReportListResponse:
        items_data = self.storage.list_analytical_reports(dataset_id, version_id)
        items = [AnalyticalReport.model_validate(d) for d in items_data]
        return ReportListResponse(total=len(items), items=items)

    def download_report(
        self,
        dataset_id: str,
        report_id: str,
        export_format: ReportExportFormat = ReportExportFormat.JSON,
    ) -> Tuple[bytes, str, str]:
        report = self.get_report(report_id)

        if export_format == ReportExportFormat.PDF:
            pdf_bytes = pdf_export_service.generate_pdf_report(report)
            filename = f"report-{dataset_id}-{report.version_id}.pdf"
            self.storage.save_report_export_file(dataset_id, report_id, filename, pdf_bytes)
            return pdf_bytes, "application/pdf", filename

        else:
            json_bytes = json.dumps(report.model_dump(), indent=2, default=str).encode("utf-8")
            filename = f"report-{dataset_id}-{report.version_id}.json"
            self.storage.save_report_export_file(dataset_id, report_id, filename, json_bytes)
            return json_bytes, "application/json", filename


report_service = ReportService()
