"""
Image Classification Visualizer for CropLens.

Transforms M2 (discovery/validation/duplicates), M3 (Data Quality Lab),
and M4 (EDA Engine) artifacts into validated, chart-ready specifications.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from app.schemas.visualization import (
    AxisScale,
    AxisSpec,
    ChartType,
    SeriesSpec,
    VisualizationCategory,
    VisualizationSpecification,
)
from app.services.visualizations.base import BaseVisualizer


class ImageClassificationVisualizer(BaseVisualizer):
    """Generates computer vision dataset visualizations based on M2–M4 analytics."""

    @property
    def name(self) -> str:
        return "image_classification_visualizer"

    def can_handle(self, dataset_id: str, version_id: str, context: Dict[str, Any]) -> bool:
        """Applicable if EDA, Quality, or M2 analysis results exist in context."""
        return bool(context.get("eda") or context.get("quality") or context.get("analysis"))

    def generate(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[VisualizationSpecification]:
        specs: List[VisualizationSpecification] = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        eda = context.get("eda")
        quality = context.get("quality")
        analysis = context.get("analysis")

        source_refs: Dict[str, Optional[str]] = {
            "analysis_id": getattr(analysis, "id", None) if analysis else None,
            "quality_id": getattr(quality, "id", None) if quality else None,
            "eda_id": getattr(eda, "id", None) if eda else None,
        }

        # ---------------------------------------------------------------------
        # 1. Class Distribution Bar Chart
        # ---------------------------------------------------------------------
        class_dist = None
        if eda and getattr(eda, "class_distribution", None):
            class_dist = eda.class_distribution
        elif quality and getattr(quality, "imbalance", None) and quality.imbalance.class_distribution:
            # Fallback to quality class distribution dict
            class_dist = None

        if class_dist and getattr(class_dist, "distribution", None):
            chart_data = []
            for entry in class_dist.distribution:
                chart_data.append({
                    "class_name": entry.class_name,
                    "valid_image_count": entry.valid_image_count,
                    "invalid_image_count": entry.invalid_image_count,
                    "percentage": round(entry.percentage_of_valid, 2),
                    "deviation_from_mean": round(entry.deviation_from_mean, 2),
                })

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-class-dist-bar",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Class Sample Distribution",
                    description="Valid image counts and relative share across all discovered agricultural classes.",
                    chart_type=ChartType.BAR,
                    category=VisualizationCategory.CLASS_DISTRIBUTION,
                    x_axis=AxisSpec(
                        name="class_name",
                        label="Class Directory",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="valid_image_count",
                        label="Valid Image Count",
                        scale=AxisScale.LINEAR,
                        unit="images",
                        min_val=0.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Valid Images",
                            data_key="valid_image_count",
                            color="#10B981",
                            unit="images",
                        ),
                        SeriesSpec(
                            name="Share (%)",
                            data_key="percentage",
                            color="#6366F1",
                            unit="%",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={
                        "total_classes": class_dist.total_classes,
                        "imbalance_ratio": class_dist.imbalance_ratio,
                        "gini_coefficient": class_dist.gini_coefficient,
                        "entropy": class_dist.entropy,
                    },
                    generated_at=now,
                    source_artifacts=source_refs,
                )
            )

        # ---------------------------------------------------------------------
        # 2. Aspect Ratio Distribution Histogram
        # ---------------------------------------------------------------------
        if eda and getattr(eda, "aspect_ratio_analysis", None):
            ar_analysis = eda.aspect_ratio_analysis
            if getattr(ar_analysis, "distribution_bins", None):
                chart_data = []
                for b in ar_analysis.distribution_bins:
                    chart_data.append({
                        "bin_label": b.label,
                        "min_ar": round(b.min_ar, 2),
                        "max_ar": round(b.max_ar, 2),
                        "count": b.count,
                        "percentage": round(b.percentage, 2),
                    })

                specs.append(
                    VisualizationSpecification(
                        visualization_id=f"vis-{dataset_id}-{version_id}-aspect-ratio-histogram",
                        dataset_id=dataset_id,
                        dataset_version=version_id,
                        title="Image Aspect Ratio Distribution",
                        description="Binned distribution of image aspect ratios (width / height) identifying orientation modes.",
                        chart_type=ChartType.HISTOGRAM,
                        category=VisualizationCategory.IMAGE_GEOMETRY,
                        x_axis=AxisSpec(
                            name="bin_label",
                            label="Aspect Ratio Range",
                            scale=AxisScale.CATEGORY,
                        ),
                        y_axis=AxisSpec(
                            name="count",
                            label="Image Count",
                            scale=AxisScale.LINEAR,
                            unit="images",
                            min_val=0.0,
                        ),
                        series=[
                            SeriesSpec(
                                name="Images",
                                data_key="count",
                                color="#3B82F6",
                                unit="images",
                            ),
                        ],
                        chart_data=chart_data,
                        metadata={
                            "mean_ar": ar_analysis.mean_ar,
                            "median_ar": ar_analysis.median_ar,
                            "portrait_count": ar_analysis.portrait_count,
                            "landscape_count": ar_analysis.landscape_count,
                            "square_count": ar_analysis.square_count,
                        },
                        generated_at=now,
                        source_artifacts=source_refs,
                    )
                )

        # ---------------------------------------------------------------------
        # 3. Image Orientation Breakdown (Pie Chart)
        # ---------------------------------------------------------------------
        dim_stats = getattr(eda, "dimension_analysis", None) or getattr(eda, "dimension_stats", None) if eda else None
        if dim_stats:
            chart_data = [
                {
                    "orientation": "Landscape",
                    "count": dim_stats.landscape_count,
                    "percentage": round(dim_stats.landscape_pct, 2),
                },
                {
                    "orientation": "Portrait",
                    "count": dim_stats.portrait_count,
                    "percentage": round(dim_stats.portrait_pct, 2),
                },
                {
                    "orientation": "Square",
                    "count": dim_stats.square_count,
                    "percentage": round(dim_stats.square_pct, 2),
                },
            ]

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-orientation-pie",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Image Orientation Composition",
                    description="Proportion of images categorized as landscape, portrait, or square geometry.",
                    chart_type=ChartType.PIE,
                    category=VisualizationCategory.IMAGE_GEOMETRY,
                    series=[
                        SeriesSpec(
                            name="Proportion",
                            data_key="count",
                            unit="images",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={
                        "unique_dimensions": dim_stats.unique_dimensions,
                    },
                    generated_at=now,
                    source_artifacts=source_refs,
                )
            )

        # ---------------------------------------------------------------------
        # 4. Image Format Diversity (Pie / Bar Chart)
        # ---------------------------------------------------------------------
        if eda and getattr(eda, "format_analysis", None):
            fmt_analysis = eda.format_analysis
            if fmt_analysis.format_distribution:
                chart_data = []
                for fmt, cnt in fmt_analysis.format_distribution.items():
                    pct = fmt_analysis.format_percentages.get(fmt, 0.0)
                    chart_data.append({
                        "format": fmt,
                        "count": cnt,
                        "percentage": round(pct, 2),
                    })

                specs.append(
                    VisualizationSpecification(
                        visualization_id=f"vis-{dataset_id}-{version_id}-format-pie",
                        dataset_id=dataset_id,
                        dataset_version=version_id,
                        title="Image Encoding & Format Breakdown",
                        description="Proportion of images encoded in each discovered container and format.",
                        chart_type=ChartType.PIE,
                        category=VisualizationCategory.FORMAT_AND_COLOR,
                        series=[
                            SeriesSpec(
                                name="Count",
                                data_key="count",
                                unit="images",
                            ),
                        ],
                        chart_data=chart_data,
                        metadata={
                            "unique_formats": fmt_analysis.unique_format_count,
                            "dominant_format": fmt_analysis.most_common_format,
                        },
                        generated_at=now,
                        source_artifacts=source_refs,
                    )
                )

        # ---------------------------------------------------------------------
        # 5. Color Mode Composition (Bar Chart)
        # ---------------------------------------------------------------------
        if eda and getattr(eda, "color_analysis", None):
            c_analysis = eda.color_analysis
            if c_analysis.color_mode_distribution:
                chart_data = []
                for mode, cnt in c_analysis.color_mode_distribution.items():
                    pct = c_analysis.color_mode_percentages.get(mode, 0.0)
                    chart_data.append({
                        "mode": mode,
                        "count": cnt,
                        "percentage": round(pct, 2),
                    })

                specs.append(
                    VisualizationSpecification(
                        visualization_id=f"vis-{dataset_id}-{version_id}-color-mode-bar",
                        dataset_id=dataset_id,
                        dataset_version=version_id,
                        title="Color Space Composition",
                        description="Distribution of image color channels (e.g. RGB 3-channel, Grayscale 1-channel, RGBA).",
                        chart_type=ChartType.BAR,
                        category=VisualizationCategory.FORMAT_AND_COLOR,
                        x_axis=AxisSpec(
                            name="mode",
                            label="Color Mode",
                            scale=AxisScale.CATEGORY,
                        ),
                        y_axis=AxisSpec(
                            name="count",
                            label="Images",
                            scale=AxisScale.LINEAR,
                            unit="images",
                            min_val=0.0,
                        ),
                        series=[
                            SeriesSpec(
                                name="Images",
                                data_key="count",
                                color="#EC4899",
                                unit="images",
                            ),
                        ],
                        chart_data=chart_data,
                        metadata={
                            "rgb_count": c_analysis.rgb_count,
                            "grayscale_count": c_analysis.grayscale_count,
                            "rgba_count": c_analysis.rgba_count,
                        },
                        generated_at=now,
                        source_artifacts=source_refs,
                    )
                )

        # ---------------------------------------------------------------------
        # 6. RGB Channel Intensity Margins (Bar Chart)
        # ---------------------------------------------------------------------
        if eda and getattr(eda, "color_analysis", None):
            c_analysis = eda.color_analysis
            if c_analysis.rgb_mean and len(c_analysis.rgb_mean) == 3:
                r_mean, g_mean, b_mean = c_analysis.rgb_mean
                r_std = c_analysis.rgb_std[0] if c_analysis.rgb_std and len(c_analysis.rgb_std) > 0 else 0.0
                g_std = c_analysis.rgb_std[1] if c_analysis.rgb_std and len(c_analysis.rgb_std) > 1 else 0.0
                b_std = c_analysis.rgb_std[2] if c_analysis.rgb_std and len(c_analysis.rgb_std) > 2 else 0.0

                chart_data = [
                    {
                        "channel": "Red",
                        "mean_intensity": round(r_mean, 2),
                        "std_intensity": round(r_std, 2),
                        "color": "#EF4444",
                    },
                    {
                        "channel": "Green",
                        "mean_intensity": round(g_mean, 2),
                        "std_intensity": round(g_std, 2),
                        "color": "#22C55E",
                    },
                    {
                        "channel": "Blue",
                        "mean_intensity": round(b_mean, 2),
                        "std_intensity": round(b_std, 2),
                        "color": "#3B82F6",
                    },
                ]

                specs.append(
                    VisualizationSpecification(
                        visualization_id=f"vis-{dataset_id}-{version_id}-rgb-channels-bar",
                        dataset_id=dataset_id,
                        dataset_version=version_id,
                        title="RGB Channel Intensity Profiles",
                        description="Mean channel pixel intensities (0–255) and standard deviations across sampled images.",
                        chart_type=ChartType.BAR,
                        category=VisualizationCategory.FORMAT_AND_COLOR,
                        x_axis=AxisSpec(
                            name="channel",
                            label="Color Channel",
                            scale=AxisScale.CATEGORY,
                        ),
                        y_axis=AxisSpec(
                            name="mean_intensity",
                            label="Mean Pixel Intensity",
                            scale=AxisScale.LINEAR,
                            min_val=0.0,
                            max_val=255.0,
                        ),
                        series=[
                            SeriesSpec(
                                name="Mean Intensity",
                                data_key="mean_intensity",
                                color="#6366F1",
                            ),
                        ],
                        chart_data=chart_data,
                        metadata={
                            "sampling_methodology": c_analysis.sampling_methodology,
                        },
                        generated_at=now,
                        source_artifacts=source_refs,
                    )
                )

        # ---------------------------------------------------------------------
        # 7. File Size Distribution Histogram
        # ---------------------------------------------------------------------
        fs_stats = getattr(eda, "file_size_analysis", None) or getattr(eda, "file_size_stats", None) if eda else None
        if fs_stats:
            if getattr(fs_stats, "size_distribution_bins", None):
                chart_data = []
                for b in fs_stats.size_distribution_bins:
                    chart_data.append({
                        "bin_label": b.label,
                        "min_bytes": b.min_bytes,
                        "max_bytes": b.max_bytes,
                        "count": b.count,
                        "percentage": round(b.percentage, 2),
                    })

                specs.append(
                    VisualizationSpecification(
                        visualization_id=f"vis-{dataset_id}-{version_id}-file-size-histogram",
                        dataset_id=dataset_id,
                        dataset_version=version_id,
                        title="File Size Distribution",
                        description="Binned histogram of compressed file payload sizes on disk.",
                        chart_type=ChartType.HISTOGRAM,
                        category=VisualizationCategory.IMAGE_GEOMETRY,
                        x_axis=AxisSpec(
                            name="bin_label",
                            label="Payload Size Range",
                            scale=AxisScale.CATEGORY,
                        ),
                        y_axis=AxisSpec(
                            name="count",
                            label="Image Count",
                            scale=AxisScale.LINEAR,
                            unit="images",
                            min_val=0.0,
                        ),
                        series=[
                            SeriesSpec(
                                name="Images",
                                data_key="count",
                                color="#F59E0B",
                                unit="images",
                            ),
                        ],
                        chart_data=chart_data,
                        metadata={
                            "total_bytes": fs_stats.total_bytes,
                            "total_human": fs_stats.total_human,
                            "mean_human": fs_stats.mean_human,
                        },
                        generated_at=now,
                        source_artifacts=source_refs,
                    )
                )

        # ---------------------------------------------------------------------
        # 8. Data Quality Score Decomposition (Bar Chart)
        # ---------------------------------------------------------------------
        if quality and getattr(quality, "quality_score", None):
            qs = quality.quality_score
            chart_data = [
                {"dimension": "Overall Quality", "score": round(qs.overall_score, 1), "color": "#10B981"},
            ]
            comp_colors = {
                "integrity": "#3B82F6",
                "balance": "#6366F1",
                "consistency": "#8B5CF6",
                "uniqueness": "#14B8A6",
            }
            if qs.components:
                for comp_key, comp in qs.components.items():
                    chart_data.append({
                        "dimension": comp.name or comp_key.capitalize(),
                        "score": round(comp.score, 1),
                        "color": comp_colors.get(comp_key, "#64748B"),
                    })

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-quality-score-bar",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Data Quality Dimension Breakdown",
                    description="Transparent quality scores (0–100) assessing integrity, class balance, consistency, and duplicate hygiene.",
                    chart_type=ChartType.BAR,
                    category=VisualizationCategory.DATA_QUALITY,
                    x_axis=AxisSpec(
                        name="dimension",
                        label="Evaluation Dimension",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="score",
                        label="Score (0-100)",
                        scale=AxisScale.LINEAR,
                        min_val=0.0,
                        max_val=100.0,
                        unit="points",
                    ),
                    series=[
                        SeriesSpec(
                            name="Score",
                            data_key="score",
                            color="#10B981",
                            unit="points",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={
                        "overall_tier": qs.quality_tier,
                        "passed_threshold": qs.overall_score >= 70.0,
                    },
                    generated_at=now,
                    source_artifacts=source_refs,
                )
            )

        # ---------------------------------------------------------------------
        # 9. Duplicate & Redundancy Impact (Bar Chart)
        # ---------------------------------------------------------------------
        dup_assess = getattr(quality, "duplicate_impact", None) or getattr(quality, "duplicates", None) if quality else None
        if dup_assess and getattr(dup_assess, "is_available", True):
            unique_cnt = dup_assess.clean_unique_images if dup_assess.clean_unique_images is not None else 0
            exact_red = dup_assess.exact_duplicate_redundant_instances or 0
            near_red = dup_assess.near_duplicate_redundant_instances or 0

            chart_data = [
                {"category": "Unique Non-Redundant", "count": unique_cnt, "color": "#10B981"},
                {"category": "Exact Duplicate Redundant", "count": exact_red, "color": "#EF4444"},
                {"category": "Near Duplicate Redundant", "count": near_red, "color": "#F97316"},
            ]

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-duplicate-impact-bar",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Dataset Uniqueness & Duplicate Redundancy",
                    description="Breakdown of unique training images versus redundant exact and perceptual near-duplicate instances.",
                    chart_type=ChartType.BAR,
                    category=VisualizationCategory.DUPLICATES,
                    x_axis=AxisSpec(
                        name="category",
                        label="Image Redundancy Category",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="count",
                        label="Image Count",
                        scale=AxisScale.LINEAR,
                        unit="images",
                        min_val=0.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Count",
                            data_key="count",
                            color="#F97316",
                            unit="images",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={
                        "exact_duplicate_groups": dup_assess.exact_duplicate_groups,
                        "near_duplicate_groups": dup_assess.near_duplicate_groups,
                        "cross_class_duplicate_groups": dup_assess.cross_class_duplicate_groups,
                    },
                    generated_at=now,
                    source_artifacts=source_refs,
                )
            )

        # ---------------------------------------------------------------------
        # 10. Image Dimension Scatter Coordinates
        # ---------------------------------------------------------------------
        dim_analysis = getattr(eda, "dimension_analysis", None) or getattr(eda, "dimension_stats", None) if eda else None
        if dim_analysis and dim_analysis.most_common_dimensions:
            chart_data = []
            for dim in dim_analysis.most_common_dimensions:
                chart_data.append({
                    "width": dim.width,
                    "height": dim.height,
                    "count": dim.count,
                    "aspect_ratio": round(dim.width / max(1, dim.height), 2),
                })

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-dimension-scatter",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Image Dimension Geometry Map",
                    description="Scatter plot of discovered image resolutions across width and height dimensions.",
                    chart_type=ChartType.SCATTER,
                    category=VisualizationCategory.IMAGE_GEOMETRY,
                    x_axis=AxisSpec(
                        name="width",
                        label="Width (pixels)",
                        scale=AxisScale.LINEAR,
                        unit="px",
                        min_val=0.0,
                    ),
                    y_axis=AxisSpec(
                        name="height",
                        label="Height (pixels)",
                        scale=AxisScale.LINEAR,
                        unit="px",
                        min_val=0.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Resolutions",
                            data_key="count",
                            color="#8B5CF6",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={
                        "unique_dimensions": dim_analysis.unique_dimensions,
                    },
                    generated_at=now,
                    source_artifacts=source_refs,
                )
            )

        return specs
