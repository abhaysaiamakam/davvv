"""
Tabular Dataset Visualizer for CropLens.

Parses tabular CSV, TSV, or JSON records in dataset directories and generates
column distributions, box plot metrics, categorical frequencies, correlation heatmaps,
and missing value statistics.
"""
from __future__ import annotations

import csv
import datetime
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.visualization import (
    AxisScale,
    AxisSpec,
    ChartType,
    SeriesSpec,
    VisualizationCategory,
    VisualizationSpecification,
)
from app.services.visualizations.base import BaseVisualizer


class TabularVisualizer(BaseVisualizer):
    """Generates visualizations for tabular dataset files (.csv, .tsv)."""

    @property
    def name(self) -> str:
        return "tabular_visualizer"

    def can_handle(self, dataset_id: str, version_id: str, context: Dict[str, Any]) -> bool:
        """Applicable if dataset contains tabular files (.csv or .tsv)."""
        dataset_dir = context.get("dataset_dir")
        if not dataset_dir or not Path(dataset_dir).exists():
            return False
        tabular_files = self._find_tabular_files(Path(dataset_dir))
        return len(tabular_files) > 0

    def _find_tabular_files(self, dataset_dir: Path) -> List[Path]:
        """Find non-empty .csv and .tsv files in the dataset directory."""
        found = []
        for ext in ["*.csv", "*.tsv"]:
            for p in dataset_dir.rglob(ext):
                if p.is_file() and p.stat().st_size > 0:
                    found.append(p)
        return found

    def _parse_csv(self, file_path: Path, max_rows: int = 5000) -> Tuple[List[str], List[Dict[str, str]]]:
        """Safely parse CSV/TSV into headers and string rows."""
        delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
        rows: List[Dict[str, str]] = []
        headers: List[str] = []

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                headers = [h.strip() for h in next(reader) if h.strip()]
            except StopIteration:
                return [], []

            for i, r in enumerate(reader):
                if i >= max_rows:
                    break
                if len(r) == len(headers):
                    rows.append({headers[j]: r[j].strip() for j in range(len(headers))})

        return headers, rows

    def _analyze_columns(
        self, headers: List[str], rows: List[Dict[str, str]]
    ) -> Tuple[Dict[str, List[float]], Dict[str, List[str]], Dict[str, int]]:
        """Separate columns into numeric and categorical and compute missing value counts."""
        numeric_cols: Dict[str, List[float]] = {}
        categorical_cols: Dict[str, List[str]] = {}
        missing_counts: Dict[str, int] = {}

        if not rows:
            return {}, {}, {}

        for h in headers:
            vals = [r[h] for r in rows]
            non_empty = [v for v in vals if v != "" and v.lower() not in ("none", "null", "nan", "na")]
            missing_counts[h] = len(vals) - len(non_empty)

            if not non_empty:
                continue

            # Check if majority can be parsed as float
            num_vals = []
            is_numeric = True
            for v in non_empty:
                try:
                    num_vals.append(float(v))
                except ValueError:
                    is_numeric = False
                    break

            if is_numeric and len(num_vals) > 0:
                numeric_cols[h] = num_vals
            else:
                categorical_cols[h] = non_empty

        return numeric_cols, categorical_cols, missing_counts

    def generate(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[VisualizationSpecification]:
        specs: List[VisualizationSpecification] = []
        dataset_dir = context.get("dataset_dir")
        if not dataset_dir:
            return specs

        tab_files = self._find_tabular_files(Path(dataset_dir))
        if not tab_files:
            return specs

        target_file = tab_files[0]
        headers, rows = self._parse_csv(target_file)
        if not headers or not rows:
            return specs

        numeric_cols, categorical_cols, missing_counts = self._analyze_columns(headers, rows)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        total_rows = len(rows)

        # ---------------------------------------------------------------------
        # 1. Missing Values Bar Chart (if missing values exist)
        # ---------------------------------------------------------------------
        total_missing = sum(missing_counts.values())
        if total_missing > 0:
            chart_data = []
            for col, count in missing_counts.items():
                pct = round((count / max(1, total_rows)) * 100, 2)
                chart_data.append({
                    "column": col,
                    "missing_count": count,
                    "missing_percentage": pct,
                })

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-tab-missing-values",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Tabular Missing Values per Feature",
                    description=f"Count and percentage of null or missing records per column in '{target_file.name}'.",
                    chart_type=ChartType.BAR,
                    category=VisualizationCategory.DATA_QUALITY,
                    x_axis=AxisSpec(
                        name="column",
                        label="Column Name",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="missing_percentage",
                        label="Missing (%)",
                        scale=AxisScale.LINEAR,
                        unit="%",
                        min_val=0.0,
                        max_val=100.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Missing (%)",
                            data_key="missing_percentage",
                            color="#EF4444",
                            unit="%",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={"total_rows": total_rows, "total_missing": total_missing},
                    generated_at=now,
                    source_artifacts={"source_file": target_file.name},
                )
            )

        # ---------------------------------------------------------------------
        # 2. Numerical Column Distribution Histograms
        # ---------------------------------------------------------------------
        for col_name, vals in list(numeric_cols.items())[:4]:  # limit to top 4 numeric cols
            if len(vals) < 3 or max(vals) == min(vals):
                continue

            min_v = min(vals)
            max_v = max(vals)
            bin_count = min(10, max(5, int(math.sqrt(len(vals)))))
            bin_width = (max_v - min_v) / bin_count

            bins = [{"count": 0, "min": min_v + i * bin_width, "max": min_v + (i + 1) * bin_width} for i in range(bin_count)]
            for v in vals:
                idx = min(int((v - min_v) / bin_width), bin_count - 1)
                bins[idx]["count"] += 1

            chart_data = []
            for i, b in enumerate(bins):
                lbl = f"{b['min']:.1f} - {b['max']:.1f}"
                pct = round((b["count"] / len(vals)) * 100, 2)
                chart_data.append({
                    "bin_label": lbl,
                    "count": b["count"],
                    "percentage": pct,
                })

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-tab-num-{col_name.lower().replace(' ', '_')}",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title=f"Feature Distribution: {col_name}",
                    description=f"Empirical frequency histogram for numerical measurement '{col_name}'.",
                    chart_type=ChartType.HISTOGRAM,
                    category=VisualizationCategory.TABULAR_DISTRIBUTION,
                    x_axis=AxisSpec(
                        name="bin_label",
                        label=f"{col_name} Range",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="count",
                        label="Sample Count",
                        scale=AxisScale.LINEAR,
                        min_val=0.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Samples",
                            data_key="count",
                            color="#3B82F6",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={"min": min_v, "max": max_v, "count": len(vals)},
                    generated_at=now,
                    source_artifacts={"source_file": target_file.name},
                )
            )

        # ---------------------------------------------------------------------
        # 3. Categorical Frequencies
        # ---------------------------------------------------------------------
        for col_name, vals in list(categorical_cols.items())[:3]:  # limit to top 3 categorical cols
            counts: Dict[str, int] = {}
            for v in vals:
                counts[v] = counts.get(v, 0) + 1

            # Check cardinality: only visualize if between 2 and 30 categories
            if 2 <= len(counts) <= 30:
                sorted_cats = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:15]
                chart_data = [
                    {"category": k, "count": cnt, "percentage": round((cnt / len(vals)) * 100, 2)}
                    for k, cnt in sorted_cats
                ]

                specs.append(
                    VisualizationSpecification(
                        visualization_id=f"vis-{dataset_id}-{version_id}-tab-cat-{col_name.lower().replace(' ', '_')}",
                        dataset_id=dataset_id,
                        dataset_version=version_id,
                        title=f"Category Breakdown: {col_name}",
                        description=f"Sample frequency across distinct categorical values for feature '{col_name}'.",
                        chart_type=ChartType.BAR,
                        category=VisualizationCategory.TABULAR_DISTRIBUTION,
                        x_axis=AxisSpec(
                            name="category",
                            label=col_name,
                            scale=AxisScale.CATEGORY,
                        ),
                        y_axis=AxisSpec(
                            name="count",
                            label="Frequency",
                            scale=AxisScale.LINEAR,
                            min_val=0.0,
                        ),
                        series=[
                            SeriesSpec(
                                name="Frequency",
                                data_key="count",
                                color="#10B981",
                            ),
                        ],
                        chart_data=chart_data,
                        metadata={"unique_categories": len(counts), "total_samples": len(vals)},
                        generated_at=now,
                        source_artifacts={"source_file": target_file.name},
                    )
                )

        # ---------------------------------------------------------------------
        # 4. Correlation Heatmap (when >= 2 numeric columns exist)
        # ---------------------------------------------------------------------
        numeric_names = list(numeric_cols.keys())
        if len(numeric_names) >= 2:
            num_cols_to_use = numeric_names[:8]
            heatmap_data = []

            for i, col_a in enumerate(num_cols_to_use):
                vals_a = numeric_cols[col_a]
                mean_a = sum(vals_a) / len(vals_a)
                std_a = math.sqrt(sum((x - mean_a) ** 2 for x in vals_a))

                for j, col_b in enumerate(num_cols_to_use):
                    vals_b = numeric_cols[col_b]
                    mean_b = sum(vals_b) / len(vals_b)
                    std_b = math.sqrt(sum((y - mean_b) ** 2 for y in vals_b))

                    if std_a > 0 and std_b > 0 and len(vals_a) == len(vals_b):
                        n = len(vals_a)
                        cov = sum((vals_a[k] - mean_a) * (vals_b[k] - mean_b) for k in range(n))
                        r = round(cov / (std_a * std_b), 3)
                    elif col_a == col_b:
                        r = 1.0
                    else:
                        r = 0.0

                    heatmap_data.append({
                        "x_column": col_a,
                        "y_column": col_b,
                        "correlation": r,
                    })

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-tab-correlation-heatmap",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Feature Correlation Matrix",
                    description="Pairwise Pearson correlation matrix across numerical features in the dataset.",
                    chart_type=ChartType.HEATMAP,
                    category=VisualizationCategory.TABULAR_CORRELATION,
                    x_axis=AxisSpec(
                        name="x_column",
                        label="Feature A",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="y_column",
                        label="Feature B",
                        scale=AxisScale.CATEGORY,
                    ),
                    series=[
                        SeriesSpec(
                            name="Pearson r",
                            data_key="correlation",
                        ),
                    ],
                    chart_data=heatmap_data,
                    metadata={"evaluated_features": num_cols_to_use},
                    generated_at=now,
                    source_artifacts={"source_file": target_file.name},
                )
            )

        return specs

