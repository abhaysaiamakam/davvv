"""
Time-Series Dataset Visualizer for CropLens.

Detects temporal columns and numerical measurements in tabular dataset files,
generating chronological trend lines and temporal distributions.
"""
from __future__ import annotations

import csv
import datetime
from pathlib import Path
import re
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


DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),                     # 2026-05-18
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),                     # 2026/05/18
    re.compile(r"^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}"),       # ISO datetime
]


class TimeSeriesVisualizer(BaseVisualizer):
    """Generates time-series trend line charts when temporal attributes are detected."""

    @property
    def name(self) -> str:
        return "time_series_visualizer"

    def can_handle(self, dataset_id: str, version_id: str, context: Dict[str, Any]) -> bool:
        """Applicable if dataset contains tabular files with temporal columns."""
        dataset_dir = context.get("dataset_dir")
        if not dataset_dir or not Path(dataset_dir).exists():
            return False

        tabular_files = []
        for ext in ["*.csv", "*.tsv"]:
            for p in Path(dataset_dir).rglob(ext):
                if p.is_file() and p.stat().st_size > 0:
                    tabular_files.append(p)

        if not tabular_files:
            return False

        # Inspect tabular files for date-like columns
        for target_file in tabular_files:
            time_col, numeric_cols = self._find_temporal_and_numeric_cols(target_file)
            if time_col is not None and numeric_cols:
                return True
        return False

    def _find_temporal_and_numeric_cols(
        self, file_path: Path
    ) -> Tuple[Optional[str], List[str]]:
        """Identify candidate temporal column and numeric columns."""
        delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                headers = next(reader, None)
                if not headers:
                    return None, []

                sample_rows = []
                for i, r in enumerate(reader):
                    if i >= 100:
                        break
                    if len(r) == len(headers):
                        sample_rows.append(r)
        except Exception:
            return None, []

        if not sample_rows:
            return None, []

        temporal_col: Optional[str] = None
        numeric_cols: List[str] = []

        for idx, col in enumerate(headers):
            col_lower = col.lower().strip()
            # Test if values match date patterns
            date_matches = 0
            num_matches = 0
            for r in sample_rows:
                val = r[idx].strip()
                if not val:
                    continue
                if any(p.match(val) for p in DATE_PATTERNS) or "date" in col_lower or "time" in col_lower:
                    date_matches += 1
                try:
                    float(val)
                    num_matches += 1
                except ValueError:
                    pass

            if date_matches >= len(sample_rows) * 0.7 and temporal_col is None:
                temporal_col = col
            elif num_matches >= len(sample_rows) * 0.8:
                numeric_cols.append(col)

        return temporal_col, numeric_cols

    def generate(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[VisualizationSpecification]:
        specs: List[VisualizationSpecification] = []
        dataset_dir = context.get("dataset_dir")
        if not dataset_dir:
            return specs

        p_dir = Path(dataset_dir)
        tab_files = list(p_dir.rglob("*.csv")) + list(p_dir.rglob("*.tsv"))
        if not tab_files:
            return specs

        for target_file in tab_files:
            time_col, numeric_cols = self._find_temporal_and_numeric_cols(target_file)
            if not time_col or not numeric_cols:
                continue

            # Parse data rows
            delimiter = "\t" if target_file.suffix.lower() == ".tsv" else ","
            rows: List[Dict[str, Any]] = []
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for r in reader:
                    time_val = r.get(time_col, "").strip()
                    if not time_val:
                        continue
                    row_dict = {"time": time_val}
                    valid_num = False
                    for ncol in numeric_cols[:3]:
                        try:
                            row_dict[ncol] = float(r.get(ncol, ""))
                            valid_num = True
                        except (ValueError, TypeError):
                            pass
                    if valid_num:
                        rows.append(row_dict)

            if len(rows) < 3:
                continue

            # Sort rows chronologically by time
            rows.sort(key=lambda x: str(x.get("time", "")))

            # Subsample if too large for chart (e.g. 100 points)
            if len(rows) > 100:
                step = len(rows) // 100
                sampled_rows = rows[::step]
            else:
                sampled_rows = rows

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            measurement_col = numeric_cols[0]

            chart_data = [
                {"time": r["time"], "value": r.get(measurement_col, 0.0)}
                for r in sampled_rows
                if measurement_col in r
            ]

            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-time-series-{measurement_col.lower().replace(' ', '_')}",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title=f"Chronological Trend: {measurement_col}",
                    description=f"Time-series measurement trend of '{measurement_col}' observed over temporal sequence '{time_col}'.",
                    chart_type=ChartType.LINE,
                    category=VisualizationCategory.TIME_SERIES,
                    x_axis=AxisSpec(
                        name="time",
                        label=time_col,
                        scale=AxisScale.TIME,
                    ),
                    y_axis=AxisSpec(
                        name="value",
                        label=measurement_col,
                        scale=AxisScale.LINEAR,
                    ),
                    series=[
                        SeriesSpec(
                            name=measurement_col,
                            data_key="value",
                            color="#059669",
                            chart_type=ChartType.LINE,
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={
                        "temporal_column": time_col,
                        "measurement_column": measurement_col,
                        "total_data_points": len(rows),
                        "sampled_points": len(chart_data),
                    },
                    generated_at=now,
                    source_artifacts={"source_file": target_file.name},
                )
            )

        return specs

