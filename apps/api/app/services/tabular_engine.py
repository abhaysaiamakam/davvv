"""
Scalable Tabular Analytical Engine (DuckDB + Parquet Shadow Path).

Provides memory-efficient, high-performance analytical processing for large CSV/TSV datasets.
Includes streaming row inspection, exact SQL aggregations, deterministic sampling,
and optional Parquet shadow acceleration.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Generator

import duckdb
from app.core.config import settings

logger = logging.getLogger(__name__)


class TabularEngine:
    """Analytical query and transformation engine for tabular files."""

    def __init__(self):
        pass

    def should_use_duckdb(self, file_path: Path, row_count_hint: Optional[int] = None) -> bool:
        """Return True if dataset exceeds in-memory thresholds."""
        if not file_path.is_file():
            return False
        if file_path.stat().st_size >= settings.DUCKDB_HYBRID_THRESHOLD_BYTES:
            return True
        if row_count_hint is not None and row_count_hint >= settings.DUCKDB_HYBRID_ROW_THRESHOLD:
            return True
        return False

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Create an isolated, memory-bounded DuckDB connection."""
        conn = duckdb.connect(database=":memory:")
        conn.execute("PRAGMA memory_limit='1GB';")
        conn.execute("PRAGMA threads=4;")
        return conn

    def _get_sql_reader_target(self, file_path: Path) -> str:
        """Format target file for DuckDB read_csv_auto query."""
        clean_path = str(file_path.resolve()).replace("'", "''")
        delim = "\\t" if file_path.suffix.lower() == ".tsv" else ","
        return f"read_csv_auto('{clean_path}', delim='{delim}', header=True, ignore_errors=True, SAMPLE_SIZE=20000)"

    def ensure_parquet_cache(self, file_path: Path) -> Path:
        """Convert CSV/TSV to Parquet shadow file if large, returning target file path."""
        if not self.should_use_duckdb(file_path):
            return file_path

        cache_dir = file_path.parent / ".parquet_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        parquet_file = cache_dir / f"{file_path.stem}.parquet"

        if parquet_file.exists() and parquet_file.stat().st_mtime >= file_path.stat().st_mtime:
            return parquet_file

        try:
            conn = self._get_connection()
            reader = self._get_sql_reader_target(file_path)
            escaped_pq = str(parquet_file.resolve()).replace("'", "''")
            conn.execute(f"COPY (SELECT * FROM {reader}) TO '{escaped_pq}' (FORMAT PARQUET);")
            conn.close()
            logger.info(f"[TabularEngine] Generated Parquet cache for {file_path.name}")
            return parquet_file
        except Exception as e:
            logger.warning(f"[TabularEngine] Failed to create Parquet cache for {file_path.name}: {e}")
            return file_path

    def get_row_count(self, file_path: Path) -> int:
        """Return total row count streamingly without full-memory load."""
        if file_path.suffix.lower() == ".parquet":
            conn = self._get_connection()
            res = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{file_path}')").fetchone()
            conn.close()
            return res[0] if res else 0

        if self.should_use_duckdb(file_path):
            conn = self._get_connection()
            reader = self._get_sql_reader_target(file_path)
            res = conn.execute(f"SELECT COUNT(*) FROM {reader}").fetchone()
            conn.close()
            return res[0] if res else 0

        # Chunked CSV count for smaller files
        import csv
        delim = "\t" if file_path.suffix.lower() == ".tsv" else ","
        count = 0
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delim)
            try:
                next(reader)  # Header
            except StopIteration:
                return 0
            for _ in reader:
                count += 1
        return count

    def get_column_headers(self, file_path: Path) -> List[str]:
        """Return list of column headers from CSV/TSV/Parquet."""
        if file_path.suffix.lower() == ".parquet":
            conn = self._get_connection()
            res = conn.execute(f"SELECT * FROM read_parquet('{file_path}') LIMIT 0").description
            conn.close()
            return [d[0] for d in res]

        import csv
        delim = "\t" if file_path.suffix.lower() == ".tsv" else ","
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delim)
            try:
                raw = next(reader)
                return [h.strip() for h in raw if h.strip()]
            except StopIteration:
                return []

    def compute_exact_column_stats(self, file_path: Path) -> Dict[str, Any]:
        """Compute exact missing counts, distinct counts, and numeric stats via DuckDB."""
        target = self.ensure_parquet_cache(file_path)
        is_parquet = target.suffix.lower() == ".parquet"

        conn = self._get_connection()
        reader_expr = f"read_parquet('{target}')" if is_parquet else self._get_sql_reader_target(target)

        # Get schema
        schema_info = conn.execute(f"DESCRIBE SELECT * FROM {reader_expr}").fetchall()
        total_rows = conn.execute(f"SELECT COUNT(*) FROM {reader_expr}").fetchone()[0]

        stats: Dict[str, Any] = {
            "total_rows": total_rows,
            "columns": {},
        }

        for col_name, col_type, *_ in schema_info:
            clean_col = col_name.replace('"', '""')
            col_expr = f'"{clean_col}"'

            # Missing and distinct count
            res = conn.execute(
                f"SELECT COUNT(*) - COUNT({col_expr}), COUNT(DISTINCT {col_expr}) FROM {reader_expr}"
            ).fetchone()
            null_count = res[0] if res else 0
            distinct_count = res[1] if res else 0

            col_stat: Dict[str, Any] = {
                "column_name": col_name,
                "data_type": col_type,
                "null_count": null_count,
                "null_pct": round((null_count / total_rows * 100) if total_rows > 0 else 0.0, 2),
                "distinct_count": distinct_count,
            }

            # Numeric statistics if column is numeric
            if any(t in col_type.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "HUGEINT")):
                num_res = conn.execute(
                    f"SELECT MIN({col_expr}), MAX({col_expr}), AVG({col_expr}), STDDEV({col_expr}), MEDIAN({col_expr}) FROM {reader_expr}"
                ).fetchone()
                if num_res and num_res[0] is not None:
                    col_stat.update({
                        "min": float(num_res[0]),
                        "max": float(num_res[1]),
                        "mean": round(float(num_res[2]), 4) if num_res[2] is not None else None,
                        "std": round(float(num_res[3]), 4) if num_res[3] is not None else None,
                        "median": round(float(num_res[4]), 4) if num_res[4] is not None else None,
                    })

            stats["columns"][col_name] = col_stat

        conn.close()
        return stats

    def sample_rows(
        self,
        file_path: Path,
        sample_limit: int = 1000,
        seed: int = 42,
    ) -> Tuple[List[Dict[str, Any]], bool, int]:
        """
        Return sampled list of row dicts.
        Returns tuple: (rows, is_exact_full_dataset, total_rows).
        """
        total_rows = self.get_row_count(file_path)

        if total_rows <= sample_limit:
            # Full dataset fits within sample limit
            from app.services.preprocessing.tabular_preprocessing import _read_table
            headers, rows = _read_table(file_path)
            return rows, True, total_rows

        # Sample required
        target = self.ensure_parquet_cache(file_path)
        is_parquet = target.suffix.lower() == ".parquet"

        conn = self._get_connection()
        reader_expr = f"read_parquet('{target}')" if is_parquet else self._get_sql_reader_target(target)

        pct = min(100.0, max(0.1, (sample_limit / max(total_rows, 1)) * 100.0))
        query = f"SELECT * FROM {reader_expr} USING SAMPLE {pct:.2f}% (bernoulli, {seed}) LIMIT {sample_limit}"
        df = conn.execute(query).fetchdf()
        conn.close()

        rows = df.to_dict(orient="records")
        # Sanitize NaN values to empty string / None for JSON safety
        sanitized_rows = []
        for r in rows:
            clean_r = {}
            for k, v in r.items():
                if v is None or (isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf"))):
                    clean_r[k] = ""
                else:
                    clean_r[k] = str(v)
            sanitized_rows.append(clean_r)

        return sanitized_rows, False, total_rows


tabular_engine = TabularEngine()
