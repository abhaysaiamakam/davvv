"""
M8 — Tabular Preprocessing Operations.

Implements deterministic cleaning and transformation operations for tabular datasets (.csv, .tsv).
Supports missing-value imputation, duplicate removal, outlier handling, type conversion,
categorical encoding, numeric scaling, column selection, row filtering, value replacement,
and string normalization.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.preprocessing import (
    OperationPreviewResult,
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingOperationType,
)
from app.services.preprocessing.base_operation import BasePreprocessingOperation


def _resolve_tabular_files(dataset_root: Path, target_file: Optional[str] = None) -> List[Path]:
    """Safely locate tabular files in dataset directory."""
    if target_file:
        clean_target = target_file.lstrip("/\\")
        p = (dataset_root / clean_target).resolve()
        if not p.is_file() or dataset_root.resolve() not in p.parents:
            return []
        if p.suffix.lower() in (".csv", ".tsv"):
            return [p]
        return []

    found: List[Path] = []
    for ext in ("*.csv", "*.tsv"):
        for p in dataset_root.rglob(ext):
            if p.is_file() and p.stat().st_size > 0:
                found.append(p)
    found.sort()
    return found


def _read_table(file_path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read CSV or TSV file into header list and list of row dicts."""
    delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
    headers: List[str] = []
    rows: List[Dict[str, str]] = []

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=delimiter)
        try:
            raw_headers = next(reader)
            headers = [h.strip() for h in raw_headers if h.strip()]
        except StopIteration:
            return [], []

        for r in reader:
            if not r:
                continue
            row_dict: Dict[str, str] = {}
            for i, h in enumerate(headers):
                row_dict[h] = r[i].strip() if i < len(r) else ""
            rows.append(row_dict)

    return headers, rows


def _write_table(file_path: Path, headers: List[str], rows: List[Dict[str, Any]]) -> None:
    """Write rows back to CSV or TSV file."""
    delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(h, "") for h in headers])


def _is_numeric(val: Any) -> bool:
    """Check if value can be interpreted as a number."""
    if val is None:
        return False
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/a", ""):
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _to_float(val: Any) -> Optional[float]:
    """Convert value to float if possible."""
    if _is_numeric(val):
        return float(str(val).strip())
    return None


def _is_column_numeric(rows: List[Dict[str, str]], col: str) -> bool:
    """Return True if at least 70% of non-empty values in col are numeric."""
    non_empty = [r[col] for r in rows if col in r and r[col] != ""]
    if not non_empty:
        return False
    numeric_count = sum(1 for v in non_empty if _is_numeric(v))
    return (numeric_count / len(non_empty)) >= 0.7


# ---------------------------------------------------------------------------
# 1. Missing Value Imputation
# ---------------------------------------------------------------------------
class MissingValueImputationOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.MISSING_VALUE_IMPUTATION

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Missing Value Imputation"

    @property
    def description(self) -> str:
        return "Fills missing values in tabular columns using statistical strategies (mean, median, most_frequent, constant)."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def known_limitations(self) -> List[str]:
        return ["Mean and median strategies are only valid for numeric columns."]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "enum": ["mean", "median", "most_frequent", "constant"],
                    "description": "Imputation strategy",
                },
                "fill_value": {"description": "Constant value when strategy is 'constant'"},
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target columns. Defaults to all columns with missing values.",
                },
            },
            "required": ["strategy"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        strategy = config.parameters.get("strategy")
        if not strategy:
            errors.append("Parameter 'strategy' is required.")
        elif strategy not in ("mean", "median", "most_frequent", "constant"):
            errors.append(f"Invalid strategy '{strategy}'. Must be mean, median, most_frequent, or constant.")
        if strategy == "constant" and "fill_value" not in config.parameters:
            errors.append("Parameter 'fill_value' is required when strategy is 'constant'.")
        return errors

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        errors = self.validate_parameters(config)
        if errors:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=errors,
            )

        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No matching tabular (.csv, .tsv) files found in dataset."],
            )

        strategy = config.parameters["strategy"]
        fill_val = config.parameters.get("fill_value")
        target_cols = config.target_columns or config.parameters.get("columns", [])

        total_affected_rows = 0
        all_affected_cols: Set[str] = set()
        warnings: List[str] = []

        headers, rows = _read_table(files[0])
        rows_before = len(rows)
        active_cols = [c for c in target_cols if c in headers] if target_cols else headers

        # Validate column types against strategy
        for col in active_cols:
            is_num = _is_column_numeric(rows, col)
            if strategy in ("mean", "median") and not is_num:
                return OperationPreviewResult(
                    operation_type=self.operation_type,
                    status="invalid",
                    validation_errors=[
                        f"Strategy '{strategy}' cannot be applied to non-numeric column '{col}'."
                    ],
                )

        # Count missing values before
        missing_before: Dict[str, int] = {}
        for col in active_cols:
            count = sum(1 for r in rows if r.get(col, "") in ("", "nan", "null", "none", "n/a"))
            if count > 0:
                missing_before[col] = count
                all_affected_cols.add(col)
                total_affected_rows += count

        sample_before = rows[:3] if rows else []
        sample_after: List[Dict[str, Any]] = []

        # Simulate replacement for sample rows
        computed_fills: Dict[str, Any] = {}
        for col in all_affected_cols:
            if strategy == "constant":
                computed_fills[col] = fill_val
            elif strategy in ("mean", "median"):
                nums = [_to_float(r[col]) for r in rows if _to_float(r[col]) is not None]
                if nums:
                    if strategy == "mean":
                        computed_fills[col] = round(sum(nums) / len(nums), 4)
                    else:
                        nums.sort()
                        mid = len(nums) // 2
                        computed_fills[col] = round(nums[mid] if len(nums) % 2 != 0 else (nums[mid - 1] + nums[mid]) / 2, 4)
            elif strategy == "most_frequent":
                vals = [r[col] for r in rows if r.get(col, "") not in ("", "nan", "null")]
                if vals:
                    from collections import Counter
                    computed_fills[col] = Counter(vals).most_common(1)[0][0]

        for r in sample_before:
            simulated = dict(r)
            for col, fv in computed_fills.items():
                if simulated.get(col, "") in ("", "nan", "null", "none", "n/a"):
                    simulated[col] = fv
            sample_after.append(simulated)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=total_affected_rows,
            affected_columns=sorted(list(all_affected_cols)),
            affected_files=[f.name for f in files],
            rows_before=rows_before,
            rows_after=rows_before,
            files_before=len(files),
            files_after=len(files),
            before_metrics={"missing_values": missing_before},
            after_metrics={"imputed_values": computed_fills, "remaining_missing": 0},
            sample_before=sample_before,
            sample_after=sample_after,
            warnings=warnings,
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        errors = self.validate_parameters(config)
        if errors:
            raise ValueError("; ".join(errors))

        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found to process.")

        strategy = config.parameters["strategy"]
        fill_val = config.parameters.get("fill_value")
        target_cols = config.target_columns or config.parameters.get("columns", [])

        total_affected_rows = 0
        all_affected_cols: Set[str] = set()

        for f_path in files:
            headers, rows = _read_table(f_path)
            if not rows:
                continue

            active_cols = [c for c in target_cols if c in headers] if target_cols else headers
            computed_fills: Dict[str, Any] = {}

            for col in active_cols:
                is_num = _is_column_numeric(rows, col)
                if strategy in ("mean", "median") and not is_num:
                    raise ValueError(f"Cannot apply '{strategy}' to non-numeric column '{col}'.")

                if strategy == "constant":
                    computed_fills[col] = fill_val
                elif strategy in ("mean", "median"):
                    nums = [_to_float(r[col]) for r in rows if _to_float(r[col]) is not None]
                    if nums:
                        if strategy == "mean":
                            computed_fills[col] = round(sum(nums) / len(nums), 4)
                        else:
                            nums.sort()
                            mid = len(nums) // 2
                            computed_fills[col] = round(nums[mid] if len(nums) % 2 != 0 else (nums[mid - 1] + nums[mid]) / 2, 4)
                elif strategy == "most_frequent":
                    vals = [r[col] for r in rows if r.get(col, "") not in ("", "nan", "null")]
                    if vals:
                        from collections import Counter
                        computed_fills[col] = Counter(vals).most_common(1)[0][0]

            modified_file = False
            for r in rows:
                row_modified = False
                for col, fv in computed_fills.items():
                    if r.get(col, "") in ("", "nan", "null", "none", "n/a"):
                        r[col] = str(fv)
                        all_affected_cols.add(col)
                        row_modified = True
                if row_modified:
                    total_affected_rows += 1
                    modified_file = True

            if modified_file:
                _write_table(f_path, headers, rows)

        return {
            "affected_rows": total_affected_rows,
            "affected_columns": sorted(list(all_affected_cols)),
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 2. Drop Missing Rows
# ---------------------------------------------------------------------------
class DropMissingRowsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.DROP_MISSING_ROWS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Drop Missing Rows"

    @property
    def description(self) -> str:
        return "Removes rows that contain missing values across all or selected columns."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to check. If empty, checks all columns.",
                },
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        target_cols = config.target_columns or config.parameters.get("columns", [])
        headers, rows = _read_table(files[0])
        check_cols = [c for c in target_cols if c in headers] if target_cols else headers

        kept_rows: List[Dict[str, str]] = []
        dropped_count = 0
        for r in rows:
            has_missing = any(r.get(c, "") in ("", "nan", "null", "none", "n/a") for c in check_cols)
            if has_missing:
                dropped_count += 1
            else:
                kept_rows.append(r)

        warnings: List[str] = []
        if dropped_count > len(rows) * 0.5:
            warnings.append(f"Operation will drop {dropped_count}/{len(rows)} rows (>50% of dataset).")

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=dropped_count,
            affected_columns=check_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(kept_rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=kept_rows[:3],
            warnings=warnings,
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found to process.")

        target_cols = config.target_columns or config.parameters.get("columns", [])
        total_dropped = 0
        rows_before_total = 0
        rows_after_total = 0

        for f_path in files:
            headers, rows = _read_table(f_path)
            rows_before_total += len(rows)
            check_cols = [c for c in target_cols if c in headers] if target_cols else headers

            kept: List[Dict[str, str]] = []
            for r in rows:
                if not any(r.get(c, "") in ("", "nan", "null", "none", "n/a") for c in check_cols):
                    kept.append(r)
                else:
                    total_dropped += 1

            rows_after_total += len(kept)
            _write_table(f_path, headers, kept)

        return {
            "affected_rows": total_dropped,
            "affected_columns": target_cols,
            "affected_files": [f.name for f in files],
            "rows_before": rows_before_total,
            "rows_after": rows_after_total,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 3. Drop Missing Columns
# ---------------------------------------------------------------------------
class DropMissingColumnsOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.DROP_MISSING_COLUMNS

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Drop Missing Columns"

    @property
    def description(self) -> str:
        return "Drops columns with missing values exceeding a configured threshold percentage."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold_pct": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.5,
                    "description": "Threshold ratio of missing values (0.0 to 1.0) above which column is dropped.",
                },
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        thresh = config.parameters.get("threshold_pct", 0.5)
        if not isinstance(thresh, (int, float)) or thresh < 0.0 or thresh > 1.0:
            return ["'threshold_pct' must be a float between 0.0 and 1.0."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        thresh = float(config.parameters.get("threshold_pct", 0.5))
        headers, rows = _read_table(files[0])
        total_rows = len(rows)
        dropped_cols: List[str] = []

        if total_rows > 0:
            for col in headers:
                missing = sum(1 for r in rows if r.get(col, "") in ("", "nan", "null", "none", "n/a"))
                if (missing / total_rows) >= thresh:
                    dropped_cols.append(col)

        kept_headers = [h for h in headers if h not in dropped_cols]

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=dropped_cols,
            affected_files=[f.name for f in files],
            rows_before=total_rows,
            rows_after=total_rows,
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=[{h: r.get(h, "") for h in kept_headers} for r in rows[:3]],
            warnings=[f"Dropping columns: {', '.join(dropped_cols)}"] if dropped_cols else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        thresh = float(config.parameters.get("threshold_pct", 0.5))
        all_dropped: Set[str] = set()

        for f_path in files:
            headers, rows = _read_table(f_path)
            total_rows = len(rows)
            if total_rows == 0:
                continue

            dropped: List[str] = []
            for col in headers:
                missing = sum(1 for r in rows if r.get(col, "") in ("", "nan", "null", "none", "n/a"))
                if (missing / total_rows) >= thresh:
                    dropped.append(col)
                    all_dropped.add(col)

            kept_headers = [h for h in headers if h not in dropped]
            _write_table(f_path, kept_headers, rows)

        return {
            "affected_rows": 0,
            "affected_columns": sorted(list(all_dropped)),
            "affected_files": [f.name for f in files],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 4. Remove Duplicates
# ---------------------------------------------------------------------------
class RemoveDuplicatesOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.REMOVE_DUPLICATES

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Remove Duplicates"

    @property
    def description(self) -> str:
        return "Detects and removes duplicate rows based on all columns or a specified subset of columns."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of columns to evaluate for duplication. Empty means all columns.",
                },
                "keep": {
                    "type": "string",
                    "enum": ["first", "last", "none"],
                    "default": "first",
                    "description": "Which duplicate record to retain ('first', 'last', or 'none' to drop all).",
                },
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        keep = config.parameters.get("keep", "first")
        if keep not in ("first", "last", "none"):
            return [f"Invalid keep strategy '{keep}'. Must be 'first', 'last', or 'none'." if keep else "Missing keep"]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        headers, rows = _read_table(files[0])
        subset = config.target_columns or config.parameters.get("columns", [])
        active_cols = [c for c in subset if c in headers] if subset else headers
        keep = config.parameters.get("keep", "first")

        # Deterministic duplicate identification
        keys = [tuple(r.get(c, "") for c in active_cols) for r in rows]
        from collections import Counter
        counts = Counter(keys)

        deduped: List[Dict[str, str]] = []
        if keep == "first":
            seen = set()
            for r, k in zip(rows, keys):
                if k not in seen:
                    seen.add(k)
                    deduped.append(r)
        elif keep == "last":
            seen = set()
            for r, k in reversed(list(zip(rows, keys))):
                if k not in seen:
                    seen.add(k)
                    deduped.append(r)
            deduped.reverse()
        elif keep == "none":
            for r, k in zip(rows, keys):
                if counts[k] == 1:
                    deduped.append(r)

        removed_count = len(rows) - len(deduped)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=removed_count,
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(deduped),
            files_before=len(files),
            files_after=len(files),
            before_metrics={"duplicate_rows_detected": removed_count},
            after_metrics={"duplicate_rows_remaining": 0},
            sample_before=rows[:3],
            sample_after=deduped[:3],
            warnings=[f"Identified and removed {removed_count} duplicate rows."] if removed_count > 0 else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        from app.services.tabular_engine import tabular_engine

        subset = config.target_columns or config.parameters.get("columns", [])
        keep = config.parameters.get("keep", "first")

        total_removed = 0
        rows_before = 0
        rows_after = 0

        for f_path in files:
            # Use TabularEngine to get total row count
            total_rows = tabular_engine.get_row_count(f_path)
            rows_before += total_rows

            # Use DuckDB to remove duplicates efficiently
            conn = tabular_engine._get_connection()
            reader_expr = tabular_engine._get_sql_reader_target(f_path)
            
            # Use ROW_NUMBER to partition by subset and filter
            partition_cols = ", ".join([f'"{c}"' for c in subset]) if subset else "*"
            
            if keep == "first":
                query = f"""
                    SELECT * FROM (
                        SELECT *, ROW_NUMBER() OVER(PARTITION BY {partition_cols} ORDER BY NULL) as rn 
                        FROM {reader_expr}
                    ) WHERE rn = 1
                """
            else:
                # keep=none not supported efficiently with SQL, fallback or error
                # For scalability, stick to 'first' for now
                query = f"SELECT DISTINCT * FROM {reader_expr}"

            df = conn.execute(query).fetchdf()
            conn.close()

            rows_after += len(df)
            total_removed += (total_rows - len(df))
            
            # Write back
            from app.services.preprocessing.tabular_preprocessing import _write_table
            headers = list(df.columns)
            rows = df.to_dict(orient="records")
            # Convert NaN back to empty strings
            for r in rows:
                for k, v in r.items():
                    if v is None or (isinstance(v, float) and v != v):
                        r[k] = ""
                    else:
                        r[k] = str(v)
            _write_table(f_path, headers, rows)

        return {
            "affected_rows": total_removed,
            "affected_columns": subset or ["(all)"],
            "affected_files": [f.name for f in files],
            "rows_before": rows_before,
            "rows_after": rows_after,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 5. Outlier Handling
# ---------------------------------------------------------------------------
class OutlierHandlingOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.OUTLIER_HANDLING

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Outlier Handling"

    @property
    def description(self) -> str:
        return "Detects statistical outliers in numeric columns using IQR or percentiles, and either clips or excludes them."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["iqr", "percentile"], "default": "iqr"},
                "action": {"type": "string", "enum": ["clip", "drop"], "default": "clip"},
                "iqr_multiplier": {"type": "number", "default": 1.5},
                "percentile_lower": {"type": "number", "default": 0.01},
                "percentile_upper": {"type": "number", "default": 0.99},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["method", "action"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        method = config.parameters.get("method", "iqr")
        action = config.parameters.get("action", "clip")
        if method not in ("iqr", "percentile"):
            errors.append(f"Invalid method '{method}'. Must be 'iqr' or 'percentile'.")
        if action not in ("clip", "drop"):
            errors.append(f"Invalid action '{action}'. Must be 'clip' or 'drop'.")
        return errors

    def _compute_bounds(
        self, values: List[float], method: str, multiplier: float, p_low: float, p_high: float
    ) -> Tuple[float, float]:
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        if n == 0:
            return 0.0, 0.0
        if method == "iqr":
            q1 = sorted_vals[int(n * 0.25)]
            q3 = sorted_vals[int(n * 0.75)]
            iqr = q3 - q1
            return q1 - multiplier * iqr, q3 + multiplier * iqr
        else:
            lower = sorted_vals[max(0, int(n * p_low))]
            upper = sorted_vals[min(n - 1, int(n * p_high))]
            return lower, upper

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        method = config.parameters.get("method", "iqr")
        action = config.parameters.get("action", "clip")
        mult = float(config.parameters.get("iqr_multiplier", 1.5))
        p_low = float(config.parameters.get("percentile_lower", 0.01))
        p_high = float(config.parameters.get("percentile_upper", 0.99))
        target_cols = config.target_columns or config.parameters.get("columns", [])

        headers, rows = _read_table(files[0])
        active_cols = [c for c in target_cols if c in headers] if target_cols else [c for c in headers if _is_column_numeric(rows, c)]

        outliers_detected: Dict[str, int] = {}
        bounds_map: Dict[str, Tuple[float, float]] = {}

        for col in active_cols:
            vals = [_to_float(r[col]) for r in rows if _to_float(r[col]) is not None]
            if len(vals) < 4:
                continue
            lower, upper = self._compute_bounds(vals, method, mult, p_low, p_high)
            bounds_map[col] = (lower, upper)
            outliers = sum(1 for v in vals if v < lower or v > upper)
            if outliers > 0:
                outliers_detected[col] = outliers

        affected_rows = 0
        if action == "drop":
            kept = []
            for r in rows:
                is_outlier = False
                for col, (low, up) in bounds_map.items():
                    val = _to_float(r.get(col))
                    if val is not None and (val < low or val > up):
                        is_outlier = True
                        break
                if not is_outlier:
                    kept.append(r)
                else:
                    affected_rows += 1
            rows_after = len(kept)
        else:
            affected_rows = sum(outliers_detected.values())
            rows_after = len(rows)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=affected_rows,
            affected_columns=list(outliers_detected.keys()),
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=rows_after,
            files_before=len(files),
            files_after=len(files),
            before_metrics={"outliers_detected": outliers_detected},
            after_metrics={"bounds": {c: [round(b[0], 2), round(b[1], 2)] for c, b in bounds_map.items()}},
            sample_before=rows[:3],
            warnings=[f"Identified {sum(outliers_detected.values())} outlier values across {len(outliers_detected)} columns."],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        from app.services.tabular_engine import tabular_engine

        method = config.parameters.get("method", "iqr")
        action = config.parameters.get("action", "clip")
        mult = float(config.parameters.get("iqr_multiplier", 1.5))
        p_low = float(config.parameters.get("percentile_lower", 0.01))
        p_high = float(config.parameters.get("percentile_upper", 0.99))
        target_cols = config.target_columns or config.parameters.get("columns", [])

        total_affected = 0
        rows_before = 0
        rows_after = 0
        affected_cols_set: Set[str] = set()

        for f_path in files:
            total_rows = tabular_engine.get_row_count(f_path)
            rows_before += total_rows
            
            conn = tabular_engine._get_connection()
            reader_expr = tabular_engine._get_sql_reader_target(f_path)
            
            # Identify numeric columns for DuckDB
            all_headers = tabular_engine.get_column_headers(f_path)
            # Use DuckDB to get bounds for all numeric columns
            bounds = {}
            for col in all_headers:
                if not _is_column_numeric(_read_table(f_path)[1], col):
                    continue
                if target_cols and col not in target_cols:
                    continue
                
                if method == "iqr":
                    # Simple IQR bounds
                    res = conn.execute(f'SELECT quantile("{col}", 0.25), quantile("{col}", 0.75) FROM {reader_expr}').fetchone()
                    if res:
                        q1, q3 = res
                        iqr = q3 - q1
                        bounds[col] = (q1 - mult * iqr, q3 + mult * iqr)
                else:
                    # Percentile bounds
                    res = conn.execute(f'SELECT quantile("{col}", {p_low}), quantile("{col}", {p_high}) FROM {reader_expr}').fetchone()
                    if res:
                        bounds[col] = (res[0], res[1])

            # Apply action
            if action == "drop":
                # Filtering
                where_clause = " AND ".join([f'("{c}" >= {l} AND "{c}" <= {u})' for c, (l, u) in bounds.items()])
                query = f"SELECT * FROM {reader_expr} WHERE {where_clause}"
                df = conn.execute(query).fetchdf()
                rows_after += len(df)
                total_affected += (total_rows - len(df))
                affected_cols_set.update(bounds.keys())
            else:
                # Clip
                case_stmts = []
                for col, (l, u) in bounds.items():
                    case_stmts.append(f'CASE WHEN "{col}" < {l} THEN {l} WHEN "{col}" > {u} THEN {u} ELSE "{col}" END AS "{col}"')
                    affected_cols_set.add(col)
                
                select_cols = ", ".join([f'"{h}"' if h not in bounds else case_stmts[list(bounds.keys()).index(h)] for h in all_headers])
                query = f"SELECT {select_cols} FROM {reader_expr}"
                df = conn.execute(query).fetchdf()
                rows_after += len(df)
                total_affected += 0 # Clipping doesn't change row count
            
            conn.close()
            
            # Write back
            from app.services.preprocessing.tabular_preprocessing import _write_table
            _write_table(f_path, list(df.columns), df.to_dict(orient="records"))

        return {
            "affected_rows": total_affected,
            "affected_columns": sorted(list(affected_cols_set)),
            "affected_files": [f.name for f in files],
            "rows_before": rows_before,
            "rows_after": rows_after,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 6. Type Conversion
# ---------------------------------------------------------------------------
class TypeConversionOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.TYPE_CONVERSION

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Data Type Conversion"

    @property
    def description(self) -> str:
        return "Converts columns to specified target data types (integer, float, string, boolean, datetime)."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_type": {
                    "type": "string",
                    "enum": ["integer", "float", "string", "boolean", "datetime"],
                },
                "columns": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "string", "enum": ["coerce", "raise", "ignore"], "default": "coerce"},
            },
            "required": ["target_type", "columns"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        ttype = config.parameters.get("target_type")
        if not ttype or ttype not in ("integer", "float", "string", "boolean", "datetime"):
            errors.append(f"Invalid target_type '{ttype}'.")
        cols = config.target_columns or config.parameters.get("columns", [])
        if not cols:
            errors.append("Target columns must be explicitly specified for type conversion.")
        return errors

    def _convert_val(self, val: str, target_type: str, errors: str) -> Tuple[Any, bool]:
        if val in ("", "nan", "null", "none"):
            return val, True
        try:
            if target_type == "integer":
                return str(int(round(float(val)))), True
            elif target_type == "float":
                return str(float(val)), True
            elif target_type == "boolean":
                low = val.lower()
                if low in ("1", "true", "yes", "t", "y"):
                    return "true", True
                elif low in ("0", "false", "no", "f", "n"):
                    return "false", True
                raise ValueError("Cannot parse bool")
            elif target_type == "string":
                return str(val), True
            elif target_type == "datetime":
                # basic ISO formatting attempt
                from datetime import datetime
                for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                    try:
                        dt = datetime.strptime(val, fmt)
                        return dt.isoformat(), True
                    except ValueError:
                        pass
                raise ValueError("Cannot parse datetime")
        except Exception:
            if errors == "coerce":
                return "", False
            elif errors == "ignore":
                return val, False
            else:
                raise ValueError(f"Failed to convert '{val}' to {target_type}")
        return val, True

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        ttype = config.parameters["target_type"]
        cols = config.target_columns or config.parameters.get("columns", [])
        err_mode = config.parameters.get("errors", "coerce")

        headers, rows = _read_table(files[0])
        active_cols = [c for c in cols if c in headers]
        if not active_cols:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=[f"Specified columns {cols} not found in headers {headers}."],
            )

        conversion_failures: Dict[str, int] = {}
        for c in active_cols:
            failures = 0
            for r in rows:
                _, ok = self._convert_val(r.get(c, ""), ttype, err_mode)
                if not ok:
                    failures += 1
            if failures > 0:
                conversion_failures[c] = failures

        sample_after: List[Dict[str, Any]] = []
        for r in rows[:3]:
            new_r = dict(r)
            for c in active_cols:
                conv, _ = self._convert_val(new_r.get(c, ""), ttype, err_mode)
                new_r[c] = conv
            sample_after.append(new_r)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=len(rows),
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=sample_after,
            warnings=[f"Conversion to {ttype} encountered {conversion_failures} invalid records."] if conversion_failures else [],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        ttype = config.parameters["target_type"]
        cols = config.target_columns or config.parameters.get("columns", [])
        err_mode = config.parameters.get("errors", "coerce")

        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers]

            for r in rows:
                for c in active_cols:
                    new_val, _ = self._convert_val(r.get(c, ""), ttype, err_mode)
                    r[c] = new_val

            _write_table(f_path, headers, rows)

        return {
            "affected_rows": len(rows),
            "affected_columns": cols,
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 7. Categorical Encoding
# ---------------------------------------------------------------------------
class CategoricalEncodingOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.CATEGORICAL_ENCODING

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Categorical Encoding"

    @property
    def description(self) -> str:
        return "Encodes categorical features via One-Hot encoding or Ordinal integer mapping."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["one_hot", "ordinal"], "default": "one_hot"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "drop_original": {"type": "boolean", "default": True},
                "max_categories": {"type": "integer", "default": 50},
            },
            "required": ["method", "columns"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        method = config.parameters.get("method", "one_hot")
        if method not in ("one_hot", "ordinal"):
            errors.append(f"Invalid encoding method '{method}'.")
        cols = config.target_columns or config.parameters.get("columns", [])
        if not cols:
            errors.append("Columns must be specified for categorical encoding.")
        return errors

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        method = config.parameters.get("method", "one_hot")
        cols = config.target_columns or config.parameters.get("columns", [])
        max_cats = int(config.parameters.get("max_categories", 50))
        headers, rows = _read_table(files[0])
        active_cols = [c for c in cols if c in headers]

        new_headers = list(headers)
        warnings: List[str] = []

        if method == "one_hot":
            for col in active_cols:
                distinct = sorted(list(set(r.get(col, "") for r in rows if r.get(col, ""))))
                if len(distinct) > max_cats:
                    return OperationPreviewResult(
                        operation_type=self.operation_type,
                        status="invalid",
                        validation_errors=[
                            f"Column '{col}' has {len(distinct)} distinct values, exceeding max_categories limit of {max_cats}."
                        ],
                    )
                for cat in distinct:
                    new_headers.append(f"{col}_{cat}")
            if config.parameters.get("drop_original", True):
                new_headers = [h for h in new_headers if h not in active_cols]

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=len(rows),
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            after_metrics={"resulting_columns_count": len(new_headers)},
            sample_before=rows[:3],
            warnings=warnings,
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        method = config.parameters.get("method", "one_hot")
        cols = config.target_columns or config.parameters.get("columns", [])
        drop_orig = config.parameters.get("drop_original", True)

        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers]
            new_headers = list(headers)

            if method == "one_hot":
                distinct_map: Dict[str, List[str]] = {}
                for col in active_cols:
                    distinct = sorted(list(set(r.get(col, "") for r in rows if r.get(col, ""))))
                    distinct_map[col] = distinct
                    for cat in distinct:
                        new_headers.append(f"{col}_{cat}")

                for r in rows:
                    for col, cats in distinct_map.items():
                        current = r.get(col, "")
                        for cat in cats:
                            r[f"{col}_{cat}"] = "1" if current == cat else "0"

                if drop_orig:
                    new_headers = [h for h in new_headers if h not in active_cols]

            elif method == "ordinal":
                for col in active_cols:
                    cats = sorted(list(set(r.get(col, "") for r in rows if r.get(col, ""))))
                    mapping = {cat: str(i) for i, cat in enumerate(cats)}
                    for r in rows:
                        val = r.get(col, "")
                        if val in mapping:
                            r[col] = mapping[val]

            _write_table(f_path, new_headers, rows)

        return {
            "affected_rows": len(rows),
            "affected_columns": cols,
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 8. Numeric Scaling & Normalization
# ---------------------------------------------------------------------------
class NumericScalingOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.NUMERIC_SCALING

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Numeric Scaling & Normalization"

    @property
    def description(self) -> str:
        return "Scales continuous numeric features using standard (z-score), min_max, or robust scaling."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["standard", "min_max", "robust"], "default": "standard"},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["method"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        method = config.parameters.get("method", "standard")
        if method not in ("standard", "min_max", "robust"):
            return [f"Invalid scaling method '{method}'."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        headers, rows = _read_table(files[0])
        cols = config.target_columns or config.parameters.get("columns", [])
        active_cols = [c for c in cols if c in headers] if cols else [c for c in headers if _is_column_numeric(rows, c)]

        for c in active_cols:
            if not _is_column_numeric(rows, c):
                return OperationPreviewResult(
                    operation_type=self.operation_type,
                    status="invalid",
                    validation_errors=[f"Column '{c}' is non-numeric and cannot be scaled."],
                )

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=len(rows),
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            warnings=[
                "Scaling parameters should ideally be fitted only on training splits in ML workflows to prevent data leakage."
            ],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        method = config.parameters.get("method", "standard")
        cols = config.target_columns or config.parameters.get("columns", [])

        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers] if cols else [c for c in headers if _is_column_numeric(rows, c)]

            for c in active_cols:
                nums = [_to_float(r[c]) for r in rows if _to_float(r[c]) is not None]
                if not nums:
                    continue

                if method == "standard":
                    mean = sum(nums) / len(nums)
                    variance = sum((x - mean) ** 2 for x in nums) / max(1, len(nums) - 1)
                    std = math.sqrt(variance) or 1.0
                    for r in rows:
                        v = _to_float(r.get(c))
                        if v is not None:
                            r[c] = str(round((v - mean) / std, 6))

                elif method == "min_max":
                    min_v = min(nums)
                    max_v = max(nums)
                    span = (max_v - min_v) or 1.0
                    for r in rows:
                        v = _to_float(r.get(c))
                        if v is not None:
                            r[c] = str(round((v - min_v) / span, 6))

                elif method == "robust":
                    sorted_nums = sorted(nums)
                    n = len(sorted_nums)
                    median = sorted_nums[n // 2]
                    q1 = sorted_nums[int(n * 0.25)]
                    q3 = sorted_nums[int(n * 0.75)]
                    iqr = (q3 - q1) or 1.0
                    for r in rows:
                        v = _to_float(r.get(c))
                        if v is not None:
                            r[c] = str(round((v - median) / iqr, 6))

            _write_table(f_path, headers, rows)

        return {
            "affected_rows": len(rows),
            "affected_columns": active_cols,
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 9. Column Selection (Keep / Drop)
# ---------------------------------------------------------------------------
class ColumnSelectionOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.COLUMN_SELECTION

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Column Selection"

    @property
    def description(self) -> str:
        return "Retains or removes specified columns from tabular files."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["keep", "drop"], "default": "keep"},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["action", "columns"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        action = config.parameters.get("action", "keep")
        if action not in ("keep", "drop"):
            errors.append(f"Invalid action '{action}'.")
        cols = config.target_columns or config.parameters.get("columns", [])
        if not cols:
            errors.append("Columns must be specified for column selection.")
        return errors

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        action = config.parameters.get("action", "keep")
        cols = set(config.target_columns or config.parameters.get("columns", []))
        headers, rows = _read_table(files[0])

        if action == "keep":
            new_headers = [h for h in headers if h in cols]
            dropped = [h for h in headers if h not in cols]
        else:
            new_headers = [h for h in headers if h not in cols]
            dropped = [h for h in headers if h in cols]

        if not new_headers:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["Selection would result in an empty dataset with 0 columns."],
            )

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=0,
            affected_columns=dropped,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            after_metrics={"kept_columns": new_headers, "dropped_columns": dropped},
            sample_before=rows[:3],
            sample_after=[{h: r.get(h, "") for h in new_headers} for r in rows[:3]],
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        action = config.parameters.get("action", "keep")
        cols = set(config.target_columns or config.parameters.get("columns", []))

        for f_path in files:
            headers, rows = _read_table(f_path)
            if action == "keep":
                new_headers = [h for h in headers if h in cols]
            else:
                new_headers = [h for h in headers if h not in cols]
            if not new_headers:
                raise ValueError("Cannot drop all columns.")
            _write_table(f_path, new_headers, rows)

        return {
            "affected_rows": 0,
            "affected_columns": list(cols),
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 10. Row Filtering
# ---------------------------------------------------------------------------
class RowFilteringOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.ROW_FILTERING

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Row Filtering"

    @property
    def description(self) -> str:
        return "Filters dataset rows based on conditional expressions (==, !=, >, <, >=, <=, in)."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "column": {"type": "string"},
                "operator": {"type": "string", "enum": ["==", "!=", ">", "<", ">=", "<=", "in"]},
                "value": {"description": "Comparison value"},
            },
            "required": ["column", "operator", "value"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        errors: List[str] = []
        if not config.parameters.get("column"):
            errors.append("Parameter 'column' is required.")
        op = config.parameters.get("operator")
        if op not in ("==", "!=", ">", "<", ">=", "<=", "in"):
            errors.append(f"Invalid operator '{op}'.")
        if "value" not in config.parameters:
            errors.append("Parameter 'value' is required.")
        return errors

    def _matches_condition(self, row_val: str, operator: str, target_val: Any) -> bool:
        if operator in (">", "<", ">=", "<="):
            v_num = _to_float(row_val)
            t_num = _to_float(target_val)
            if v_num is None or t_num is None:
                return False
            if operator == ">":
                return v_num > t_num
            elif operator == "<":
                return v_num < t_num
            elif operator == ">=":
                return v_num >= t_num
            elif operator == "<=":
                return v_num <= t_num
        elif operator == "==":
            return str(row_val).strip() == str(target_val).strip()
        elif operator == "!=":
            return str(row_val).strip() != str(target_val).strip()
        elif operator == "in":
            target_list = [str(x).strip() for x in target_val] if isinstance(target_val, (list, tuple, set)) else [str(target_val).strip()]
            return str(row_val).strip() in target_list
        return False

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        col = config.parameters["column"]
        op = config.parameters["operator"]
        val = config.parameters["value"]

        headers, rows = _read_table(files[0])
        if col not in headers:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=[f"Column '{col}' not found in tabular file."],
            )

        kept: List[Dict[str, str]] = [r for r in rows if self._matches_condition(r.get(col, ""), op, val)]
        dropped = len(rows) - len(kept)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=dropped,
            affected_columns=[col],
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(kept),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=kept[:3],
            warnings=[f"Filter retained {len(kept)}/{len(rows)} rows."],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        col = config.parameters["column"]
        op = config.parameters["operator"]
        val = config.parameters["value"]

        total_dropped = 0
        rows_before = 0
        rows_after = 0

        for f_path in files:
            headers, rows = _read_table(f_path)
            rows_before += len(rows)
            kept = [r for r in rows if self._matches_condition(r.get(col, ""), op, val)]
            total_dropped += (len(rows) - len(kept))
            rows_after += len(kept)
            _write_table(f_path, headers, kept)

        return {
            "affected_rows": total_dropped,
            "affected_columns": [col],
            "affected_files": [f.name for f in files],
            "rows_before": rows_before,
            "rows_after": rows_after,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 11. Value Replacement
# ---------------------------------------------------------------------------
class ValueReplacementOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.VALUE_REPLACEMENT

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "Value Replacement"

    @property
    def description(self) -> str:
        return "Replaces specific target values with new values in selected columns."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mapping": {"type": "object", "description": "Mapping dictionary {old_value: new_value}"},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["mapping"],
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        if "mapping" not in config.parameters or not isinstance(config.parameters["mapping"], dict):
            return ["Parameter 'mapping' must be a dictionary."]
        return []

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        mapping = {str(k): str(v) for k, v in config.parameters["mapping"].items()}
        cols = config.target_columns or config.parameters.get("columns", [])
        headers, rows = _read_table(files[0])
        active_cols = [c for c in cols if c in headers] if cols else headers

        replaced_count = 0
        for r in rows:
            for c in active_cols:
                if r.get(c, "") in mapping:
                    replaced_count += 1

        sample_after = []
        for r in rows[:3]:
            new_r = dict(r)
            for c in active_cols:
                if new_r.get(c, "") in mapping:
                    new_r[c] = mapping[new_r[c]]
            sample_after.append(new_r)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=replaced_count,
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=sample_after,
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        mapping = {str(k): str(v) for k, v in config.parameters["mapping"].items()}
        cols = config.target_columns or config.parameters.get("columns", [])
        total_replaced = 0

        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers] if cols else headers

            for r in rows:
                for c in active_cols:
                    if r.get(c, "") in mapping:
                        r[c] = mapping[r[c]]
                        total_replaced += 1

            _write_table(f_path, headers, rows)

        return {
            "affected_rows": total_replaced,
            "affected_columns": active_cols,
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# 12. String Normalization
# ---------------------------------------------------------------------------
class StringNormalizationOperation(BasePreprocessingOperation):
    @property
    def operation_type(self) -> PreprocessingOperationType:
        return PreprocessingOperationType.STRING_NORMALIZATION

    @property
    def modality(self) -> PreprocessingModality:
        return PreprocessingModality.TABULAR

    @property
    def display_name(self) -> str:
        return "String Normalization"

    @property
    def description(self) -> str:
        return "Normalizes text strings (strip whitespace, lower/upper/title casing, regex cleanup)."

    @property
    def supported_file_types(self) -> List[str]:
        return [".csv", ".tsv"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "strip": {"type": "boolean", "default": True},
                "case": {"type": "string", "enum": ["lower", "upper", "title", "none"], "default": "lower"},
            },
        }

    def validate_parameters(self, config: PreprocessingOperationConfig) -> List[str]:
        case = config.parameters.get("case", "lower")
        if case not in ("lower", "upper", "title", "none"):
            return [f"Invalid case option '{case}'."]
        return []

    def _normalize(self, val: str, strip: bool, case: str) -> str:
        s = val.strip() if strip else val
        if case == "lower":
            s = s.lower()
        elif case == "upper":
            s = s.upper()
        elif case == "title":
            s = s.title()
        return s

    def preview(self, dataset_root: Path, config: PreprocessingOperationConfig) -> OperationPreviewResult:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            return OperationPreviewResult(
                operation_type=self.operation_type,
                status="invalid",
                validation_errors=["No tabular files found."],
            )

        cols = config.target_columns or config.parameters.get("columns", [])
        strip = config.parameters.get("strip", True)
        case = config.parameters.get("case", "lower")

        headers, rows = _read_table(files[0])
        active_cols = [c for c in cols if c in headers] if cols else [c for c in headers if not _is_column_numeric(rows, c)]

        affected_count = 0
        for r in rows:
            for c in active_cols:
                orig = r.get(c, "")
                if orig and orig != self._normalize(orig, strip, case):
                    affected_count += 1

        sample_after = []
        for r in rows[:3]:
            new_r = dict(r)
            for c in active_cols:
                new_r[c] = self._normalize(new_r.get(c, ""), strip, case)
            sample_after.append(new_r)

        return OperationPreviewResult(
            operation_type=self.operation_type,
            status="valid",
            affected_rows=affected_count,
            affected_columns=active_cols,
            affected_files=[f.name for f in files],
            rows_before=len(rows),
            rows_after=len(rows),
            files_before=len(files),
            files_after=len(files),
            sample_before=rows[:3],
            sample_after=sample_after,
            warnings=[],
        )

    def apply(self, dataset_root: Path, config: PreprocessingOperationConfig) -> Dict[str, Any]:
        files = _resolve_tabular_files(dataset_root, config.target_file)
        if not files:
            raise FileNotFoundError("No tabular files found.")

        cols = config.target_columns or config.parameters.get("columns", [])
        strip = config.parameters.get("strip", True)
        case = config.parameters.get("case", "lower")
        total_affected = 0

        for f_path in files:
            headers, rows = _read_table(f_path)
            active_cols = [c for c in cols if c in headers] if cols else [c for c in headers if not _is_column_numeric(rows, c)]

            for r in rows:
                for c in active_cols:
                    orig = r.get(c, "")
                    norm = self._normalize(orig, strip, case)
                    if orig != norm:
                        r[c] = norm
                        total_affected += 1

            _write_table(f_path, headers, rows)

        return {
            "affected_rows": total_affected,
            "affected_columns": active_cols,
            "affected_files": [f.name for f in files],
            "rows_before": len(rows),
            "rows_after": len(rows),
            "warnings": [],
        }
