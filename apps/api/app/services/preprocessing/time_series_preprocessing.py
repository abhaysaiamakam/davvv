"""
M8 — Time-Series Preprocessing Operations.

Implements temporal operations for time-series datasets:
- Parse timestamps
- Sort by timestamp
- Handle duplicate timestamps (keep_first, keep_last, drop_all, aggregate)
- Interpolate missing measurements (linear, forward_fill, backward_fill)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.preprocessing import (
    OperationPreviewResult,
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingOperationType,
)
from app.services.preprocessing.base_operation import BasePreprocessingOperation
from app.services.preprocessing.tabular_preprocessing import (
    _is_numeric,
    _read_table,
    _resolve_tabular_files,
    _to_float,
    _write_table,
)


def _parse_iso(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    cleaned = dt_str.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Parse Timestamps
# ---------------------------------------------------------------------------
class ParseTimestampsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.PARSE_TIMESTAMPS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TIME_SERIES

    @property
    def display_name(self) -> str:
        return "Parse Timestamps"

    @property
    def description(self) -> str:
        return "Parses date/time strings in a column into standardized ISO-8601 timestamps."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timestamp_column": {"type": "string"},
                "format": {"type": "string", "description": "Optional strptime format string"},
            },
            "required": ["timestamp_column"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        p = config.parameters
        if not p.get("timestamp_column") and not config.target_columns:
            return ["Parameter 'timestamp_column' is required."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular time-series files found."],
            )

        col = config.parameters.get("timestamp_column") or (config.target_columns[0] if config.target_columns else None)
        headers, rows = _read_table(files[0])
        if col not in headers:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=[f"Timestamp column '{col}' not in headers."],
            )

        parsed_ok = 0
        failed = 0
        for r in rows:
            dt = _parse_iso(r.get(col, ""))
            if dt:
                parsed_ok += 1
            else:
                failed += 1

        sample_after = []
        for r in rows[:3]:
            new_r = dict(r)
            dt = _parse_iso(new_r.get(col, ""))
            if dt:
                new_r[col] = dt.isoformat()
            sample_after.append(new_r)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=parsed_ok,
            affected_columns=[col],
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            before_metrics={"total_rows": len(rows)},
            after_metrics={"successfully_parsed": parsed_ok, "parse_failures": failed},
            sample_before=rows[:3],
            sample_after=sample_after,
            warnings=[f"Failed to parse timestamps in {failed} rows."] if failed > 0 else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        col = config.parameters.get("timestamp_column") or (config.target_columns[0] if config.target_columns else None)

        total_parsed = 0
        for f_path in files:
            headers, rows = _read_table(f_path)
            if col not in headers:
                continue

            for r in rows:
                dt = _parse_iso(r.get(col, ""))
                if dt:
                    r[col] = dt.isoformat()
                    total_parsed += 1

            _write_table(f_path, headers, rows)

        return {
            "affected_rows": total_parsed,
            "affected_columns": [col] if col else [],
            "affected_files": [f.name for f in files],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 2. Sort Timestamps
# ---------------------------------------------------------------------------
class SortTimestampsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.SORT_TIMESTAMPS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TIME_SERIES

    @property
    def display_name(self) -> str:
        return "Sort Timestamps"

    @property
    def description(self) -> str:
        return "Sorts observations chronologically by the timestamp column."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timestamp_column": {"type": "string"},
                "ascending": {"type": "boolean", "default": True},
            },
            "required": ["timestamp_column"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        if not config.parameters.get("timestamp_column") and not config.target_columns:
            return ["Parameter 'timestamp_column' is required."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        col = config.parameters.get("timestamp_column") or (config.target_columns[0] if config.target_columns else None)
        asc = config.parameters.get("ascending", True)
        headers, rows = _read_table(files[0])
        if col not in headers:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=[f"Timestamp column '{col}' not in headers."],
            )

        sorted_rows = sorted(
            rows,
            key=lambda r: _parse_iso(r.get(col, "")) or datetime.min,
            reverse=not asc,
        )

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=len(rows),
            affected_columns=[col],
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=sorted_rows[:3],
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        col = config.parameters.get("timestamp_column") or (config.target_columns[0] if config.target_columns else None)
        asc = config.parameters.get("ascending", True)

        for f_path in files:
            headers, rows = _read_table(f_path)
            if col not in headers:
                continue

            sorted_rows = sorted(
                rows,
                key=lambda r: _parse_iso(r.get(col, "")) or datetime.min,
                reverse=not asc,
            )
            _write_table(f_path, headers, sorted_rows)

        return {
            "affected_rows": len(rows),
            "affected_columns": [col] if col else [],
            "affected_files": [f.name for f in files],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 3. Handle Duplicate Timestamps
# ---------------------------------------------------------------------------
class HandleDuplicateTimestampsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.HANDLE_DUPLICATE_TIMESTAMPS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TIME_SERIES

    @property
    def display_name(self) -> str:
        return "Handle Duplicate Timestamps"

    @property
    def description(self) -> str:
        return "Resolves rows sharing identical timestamps by keeping first, keeping last, dropping, or aggregating."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timestamp_column": {"type": "string"},
                "strategy": {"type": "string", "enum": ["keep_first", "keep_last", "drop_all"], "default": "keep_first"},
            },
            "required": ["timestamp_column"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        strategy = config.parameters.get("strategy", "keep_first")
        if strategy not in ("keep_first", "keep_last", "drop_all"):
            return [f"Invalid strategy '{strategy}'."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        col = config.parameters.get("timestamp_column") or (config.target_columns[0] if config.target_columns else None)
        strategy = config.parameters.get("strategy", "keep_first")
        headers, rows = _read_table(files[0])

        keys = [r.get(col, "") for r in rows]
        from collections import Counter
        counts = Counter(keys)
        dup_count = sum(c - 1 for c in counts.values() if c > 1)

        deduped: List[Dict[str, str]] = []
        if strategy == "keep_first":
            seen = set()
            for r in rows:
                k = r.get(col, "")
                if k not in seen:
                    seen.add(k)
                    deduped.append(r)
        elif strategy == "keep_last":
            seen = set()
            for r in reversed(rows):
                k = r.get(col, "")
                if k not in seen:
                    seen.add(k)
                    deduped.append(r)
            deduped.reverse()
        elif strategy == "drop_all":
            for r in rows:
                if counts[r.get(col, "")] == 1:
                    deduped.append(r)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=len(rows) - len(deduped),
            affected_columns=[col],
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(deduped),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=deduped[:3],
            warnings=[f"Found {dup_count} duplicate timestamp records."] if dup_count > 0 else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        col = config.parameters.get("timestamp_column") or (config.target_columns[0] if config.target_columns else None)
        strategy = config.parameters.get("strategy", "keep_first")

        total_dropped = 0
        rows_before = 0
        rows_after = 0

        for f_path in files:
            headers, rows = _read_table(f_path)
            rows_before += len(rows)
            keys = [r.get(col, "") for r in rows]
            from collections import Counter
            counts = Counter(keys)

            deduped: List[Dict[str, str]] = []
            if strategy == "keep_first":
                seen = set()
                for r in rows:
                    k = r.get(col, "")
                    if k not in seen:
                        seen.add(k)
                        deduped.append(r)
            elif strategy == "keep_last":
                seen = set()
                for r in reversed(rows):
                    k = r.get(col, "")
                    if k not in seen:
                        seen.add(k)
                        deduped.append(r)
                deduped.reverse()
            elif strategy == "drop_all":
                for r in rows:
                    if counts[r.get(col, "")] == 1:
                        deduped.append(r)

            total_dropped += (len(rows) - len(deduped))
            rows_after += len(deduped)
            _write_table(f_path, headers, deduped)

        return {
            "affected_rows": total_dropped,
            "affected_columns": [col] if col else [],
            "affected_files": [f.name for f in files],
            "rows_before": rows_before,
            "rows_after": rows_after,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 4. Interpolate Missing Timestamps
# ---------------------------------------------------------------------------
class InterpolateMissingTimestampsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.INTERPOLATE_MISSING_TIMESTAMPS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TIME_SERIES

    @property
    def display_name(self) -> str:
        return "Interpolate Missing Measurements"

    @property
    def description(self) -> str:
        return "Fills missing values along temporal series via linear interpolation, forward fill, or backward fill."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def known_limitations(self) -> List[str]:
        return ["Linear interpolation applies strictly to numeric measurement columns."]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "strategy": {"type": "string", "enum": ["linear", "forward_fill", "backward_fill"], "default": "linear"},
            },
            "required": ["strategy"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        strat = config.parameters.get("strategy", "linear")
        if strat not in ("linear", "forward_fill", "backward_fill"):
            return [f"Invalid interpolation strategy '{strat}'."]
        return []

    def _interpolate_series(self, values: List[str], strategy: str) -> List[str]:
        n = len(values)
        res = list(values)

        if strategy == "forward_fill":
            last_val = ""
            for i in range(n):
                if res[i] not in ("", "nan", "null"):
                    last_val = res[i]
                elif last_val:
                    res[i] = last_val
        elif strategy == "backward_fill":
            next_val = ""
            for i in reversed(range(n)):
                if res[i] not in ("", "nan", "null"):
                    next_val = res[i]
                elif next_val:
                    res[i] = next_val
        elif strategy == "linear":
            # Linear interpolation on numeric sequences
            i = 0
            while i < n:
                if res[i] in ("", "nan", "null"):
                    # Find start and end bounds
                    start_idx = i - 1
                    end_idx = i
                    while end_idx < n and res[end_idx] in ("", "nan", "null"):
                        end_idx += 1

                    v_start = _to_float(res[start_idx]) if start_idx >= 0 else None
                    v_end = _to_float(res[end_idx]) if end_idx < n else None

                    if v_start is not None and v_end is not None:
                        step = (v_end - v_start) / (end_idx - start_idx)
                        for k in range(start_idx + 1, end_idx):
                            res[k] = str(round(v_start + step * (k - start_idx), 4))
                    elif v_start is not None:
                        for k in range(start_idx + 1, end_idx):
                            res[k] = str(v_start)
                    elif v_end is not None:
                        for k in range(start_idx + 1, end_idx):
                            res[k] = str(v_end)

                    i = end_idx
                else:
                    i += 1
        return res

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        strat = config.parameters.get("strategy", "linear")
        cols = config.target_columns or config.parameters.get("columns", [])
        headers, rows = _read_table(files[0])
        active_cols = [c for c in cols if c in headers] if cols else headers

        missing_count = 0
        for c in active_cols:
            missing_count += sum(1 for r in rows if r.get(c, "") in ("", "nan", "null"))

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=missing_count,
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            warnings=[
                "Interpolation assumes temporal continuity. Verify data integrity against domain expectations."
            ],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        strat = config.parameters.get("strategy", "linear")
        cols = config.target_columns or config.parameters.get("columns", [])

        total_interpolated = 0
        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers] if cols else headers

            for c in active_cols:
                vals = [r.get(c, "") for r in rows]
                interpolated = self._interpolate_series(vals, strat)
                for i, new_v in enumerate(interpolated):
                    if vals[i] in ("", "nan", "null") and new_v not in ("", "nan", "null"):
                        rows[i][c] = new_v
                        total_interpolated += 1

            _write_table(f_path, headers, rows)

        return {
            "affected_rows": total_interpolated,
            "affected_columns": cols,
            "affected_files": [f.name for f in files],
            "warnings": [],
        }
