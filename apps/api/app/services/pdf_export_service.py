"""
M10 — PDF Report Export Service.

Generates clean, multi-page PDF document analytical reports using ReportLab.
Integrates executive summary, dataset metadata, quality findings, EDA, insights,
preprocessing history, feature engineering, dataset readiness, and reproducible methodology.
"""
from __future__ import annotations

import datetime
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.reports import AnalyticalReport

logger = logging.getLogger(__name__)


class PdfExportService:
    """Generates PDF documents from unified AnalyticalReport schema objects."""

    def generate_pdf_report(self, report: AnalyticalReport) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        
        # Custom palette
        primary_color = colors.HexColor("#065F46")     # Emerald-800
        secondary_color = colors.HexColor("#047857")   # Emerald-700
        accent_color = colors.HexColor("#059669")      # Emerald-600
        dark_text = colors.HexColor("#1F2937")         # Zinc-800
        muted_text = colors.HexColor("#4B5563")        # Zinc-600
        bg_card = colors.HexColor("#F3F4F6")           # Zinc-100
        border_color = colors.HexColor("#D1D5DB")      # Zinc-300

        # Custom Paragraph Styles
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=primary_color,
            spaceAfter=4,
        )

        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=muted_text,
            spaceAfter=12,
        )

        h2_style = ParagraphStyle(
            "SectionH2",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=secondary_color,
            spaceBefore=14,
            spaceAfter=6,
        )

        body_style = ParagraphStyle(
            "BodyDark",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=dark_text,
            spaceAfter=4,
        )

        badge_style = ParagraphStyle(
            "BadgeStyle",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
            textColor=colors.white,
            alignment=1, # Center
        )

        story = []

        # ---------------------------------------------------------------------
        # Header / Title Block
        # ---------------------------------------------------------------------
        story.append(Paragraph(f"CropLens Analytical Report", title_style))
        story.append(
            Paragraph(
                f"<b>Dataset:</b> {report.dataset_overview.dataset_name} &nbsp;|&nbsp; "
                f"<b>Modality:</b> {report.dataset_overview.modality.upper()} &nbsp;|&nbsp; "
                f"<b>Version:</b> {report.dataset_overview.version_id}",
                subtitle_style,
            )
        )
        story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=12))

        # ---------------------------------------------------------------------
        # 1. Executive Summary
        # ---------------------------------------------------------------------
        story.append(Paragraph("1. Executive Summary", h2_style))
        exec_data = [
            [
                Paragraph("<b>Overall Readiness Status:</b>", body_style),
                Paragraph(f"<b>{report.executive_summary.readiness_status.value.upper()}</b>", body_style),
                Paragraph("<b>Readiness Score:</b>", body_style),
                Paragraph(f"<b>{report.readiness_section.overall_score} / 100</b>", body_style),
            ],
            [
                Paragraph("<b>Dataset Files / Size:</b>", body_style),
                Paragraph(f"{report.executive_summary.total_files} files ({round(report.executive_summary.total_bytes / (1024*1024), 2)} MB)", body_style),
                Paragraph("<b>Primary Objective:</b>", body_style),
                Paragraph(report.executive_summary.main_objective, body_style),
            ],
        ]
        t_exec = Table(exec_data, colWidths=[120, 150, 120, 150])
        t_exec.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg_card),
                ("BOX", (0, 0), (-1, -1), 0.5, border_color),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(t_exec)
        story.append(Spacer(1, 8))

        if report.executive_summary.key_findings:
            story.append(Paragraph("<b>Key Analytical Findings:</b>", body_style))
            for kf in report.executive_summary.key_findings[:5]:
                story.append(Paragraph(f"• {kf}", body_style))
            story.append(Spacer(1, 4))

        # ---------------------------------------------------------------------
        # 2. Data Quality Assessment (M3)
        # ---------------------------------------------------------------------
        story.append(Paragraph("2. Data Quality Assessment", h2_style))
        q_score_str = f"{report.quality_section.quality_score}/100" if report.quality_section.quality_score is not None else "N/A"
        q_tier_str = report.quality_section.quality_tier.upper() if report.quality_section.quality_tier else "N/A"
        
        q_table_data = [
            [Paragraph("<b>Quality Score</b>", body_style), Paragraph("<b>Quality Tier</b>", body_style), Paragraph("<b>Missing Values</b>", body_style), Paragraph("<b>Corrupt Files</b>", body_style), Paragraph("<b>Duplicates</b>", body_style)],
            [Paragraph(q_score_str, body_style), Paragraph(q_tier_str, body_style), Paragraph(str(report.quality_section.missing_values_count), body_style), Paragraph(str(report.quality_section.corrupted_files_count), body_style), Paragraph(str(report.quality_section.duplicate_count), body_style)],
        ]
        t_q = Table(q_table_data, colWidths=[100, 100, 110, 110, 110])
        t_q.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), secondary_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(t_q)
        story.append(Spacer(1, 8))

        # ---------------------------------------------------------------------
        # 3. Exploratory Data Analysis & Visualizations (M4)
        # ---------------------------------------------------------------------
        story.append(Paragraph("3. Exploratory Data Analysis (EDA)", h2_style))
        story.append(Paragraph(f"<b>Persisted Visualization Specifications:</b> {report.eda_section.visualization_count} charts generated", body_style))
        if report.eda_section.eda_findings:
            for eda_f in report.eda_section.eda_findings[:4]:
                title = eda_f.get("title", eda_f.get("type", "Finding"))
                desc = eda_f.get("description", "")
                story.append(Paragraph(f"• <b>{title}:</b> {desc}", body_style))
        story.append(Spacer(1, 8))

        # ---------------------------------------------------------------------
        # 4. Dataset Insights & Anomalies (M7)
        # ---------------------------------------------------------------------
        story.append(Paragraph("4. Dataset Insights & Anomaly Log", h2_style))
        if report.insights_section.insights:
            ins_rows = [[Paragraph("<b>Severity</b>", body_style), Paragraph("<b>Category</b>", body_style), Paragraph("<b>Insight Summary</b>", body_style)]]
            for ins in report.insights_section.insights[:6]:
                sev = str(ins.get("severity", "info")).upper()
                cat = str(ins.get("category", "general"))
                title = ins.get("title", ins.get("explanation", ""))
                ins_rows.append([Paragraph(f"<b>{sev}</b>", body_style), Paragraph(cat, body_style), Paragraph(title, body_style)])
            
            t_ins = Table(ins_rows, colWidths=[80, 120, 340])
            t_ins.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), bg_card),
                    ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ])
            )
            story.append(t_ins)
        else:
            story.append(Paragraph("No severe anomalies or dataset critique items detected.", body_style))
        story.append(Spacer(1, 8))

        # ---------------------------------------------------------------------
        # 5. Preprocessing & Feature Engineering Summary (M8 & M9)
        # ---------------------------------------------------------------------
        story.append(Paragraph("5. Preprocessing & Feature Engineering Summary", h2_style))
        story.append(Paragraph(f"<b>M8 Preprocessing Operations Applied:</b> {report.preprocessing_section.operations_applied_count}", body_style))
        story.append(Paragraph(f"<b>M9 Generated Features Count:</b> {report.feature_engineering_section.generated_features_count}", body_style))
        if report.feature_engineering_section.pca_component_count:
            story.append(Paragraph(f"<b>PCA Dimensionality Reduction:</b> {report.feature_engineering_section.pca_component_count} components fitted", body_style))
        story.append(Spacer(1, 8))

        # ---------------------------------------------------------------------
        # 6. Dataset Readiness Assessment
        # ---------------------------------------------------------------------
        story.append(Paragraph("6. Dataset Readiness Assessment", h2_style))
        r_rows = [[Paragraph("<b>Dimension</b>", body_style), Paragraph("<b>Status</b>", body_style), Paragraph("<b>Score</b>", body_style), Paragraph("<b>Key Recommendation / Finding</b>", body_style)]]
        for dim in report.readiness_section.dimensions:
            dim_name = dim.dimension.value.replace("_", " ").title()
            rec_text = dim.recommendations[0] if dim.recommendations else (dim.blocking_issues[0] if dim.blocking_issues else "Satisfactory")
            r_rows.append([
                Paragraph(dim_name, body_style),
                Paragraph(dim.status.value.upper(), body_style),
                Paragraph(f"{dim.score}/100", body_style),
                Paragraph(rec_text, body_style),
            ])
        t_r = Table(r_rows, colWidths=[130, 90, 60, 260])
        t_r.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), secondary_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(t_r)
        story.append(Spacer(1, 8))

        # ---------------------------------------------------------------------
        # 7. Reproducible Analytical Methodology
        # ---------------------------------------------------------------------
        story.append(Paragraph("7. Reproducible Analytical Methodology", h2_style))
        story.append(Paragraph(report.methodology_section.workflow_summary, body_style))
        story.append(Spacer(1, 4))

        m_rows = [[Paragraph("<b>#</b>", body_style), Paragraph("<b>Stage</b>", body_style), Paragraph("<b>Operation</b>", body_style), Paragraph("<b>Input / Output Version</b>", body_style)]]
        for s in report.methodology_section.steps:
            m_rows.append([
                Paragraph(str(s.step_number), body_style),
                Paragraph(s.stage_name, body_style),
                Paragraph(s.operation_name, body_style),
                Paragraph(f"{s.input_version_id or '-'} &rarr; {s.output_version_id or '-'}", body_style),
            ])
        t_m = Table(m_rows, colWidths=[20, 150, 210, 160])
        t_m.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_card),
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(t_m)
        story.append(Spacer(1, 12))

        # ---------------------------------------------------------------------
        # Footer / Provenance
        # ---------------------------------------------------------------------
        story.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=6))
        story.append(
            Paragraph(
                f"<b>Report ID:</b> {report.report_id} &nbsp;|&nbsp; "
                f"<b>Generated:</b> {report.created_at} &nbsp;|&nbsp; "
                f"<b>Engine:</b> {report.methodology_section.execution_engine}",
                subtitle_style,
            )
        )

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()


pdf_export_service = PdfExportService()
