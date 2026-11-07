"""
M7 — Tabular Dataset Insight Analyzer.

Generates insights from CSV/tabular files discovered in the dataset directory,
supplemented by visualization artifacts that may already contain computed statistics.
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.insights import (
    DatasetInsight,
    InsightCategory,
    InsightConfidence,
    InsightEvidence,
    InsightSeverity,
)
from app.services.insights.base_insight_analyzer import BaseInsightAnalyzer

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_id(dataset_id: str, version_id: str, rule_id: str) -> str:
    safe_ds = dataset_id.replace("/", "-")[:40]
    safe_ver = version_id.replace("/", "-")[:20]
    return f"ins-{safe_ds}-{safe_ver}-{rule_id}"


class TabularInsightAnalyzer(BaseInsightAnalyzer):
    """
    Produces evidence-backed insights for tabular (CSV) datasets.

    Reads CSV files from context["dataset_dir"] using stdlib csv module.
    Also reads visualization specs from context["visualizations"] if available.
    """

    @property
    def name(self) -> str:
        return "tabular_insight_analyzer"

    def can_handle(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> bool:
        dataset_dir: Optional[Path] = context.get("dataset_dir")
        if dataset_dir and isinstance(dataset_dir, Path) and dataset_dir.exists():
            csv_files = list(dataset_dir.rglob("*.csv"))
            if csv_files:
                return True
        return False

    def analyze(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[DatasetInsight]:
        dataset_dir: Optional[Path] = context.get("dataset_dir")
        if not dataset_dir or not dataset_dir.exists():
            return []

        csv_files = list(dataset_dir.rglob("*.csv"))
        if not csv_files:
            return []

        insights: List[DatasetInsight] = []

        for csv_path in csv_files[:5]:  # Cap at 5 files to avoid timeouts
            try:
                stats = self._compute_stats(csv_path)
                if stats is None:
                    continue

                file_label = csv_path.name
                suffix = f"-{file_label}"

                try:
                    insights.extend(self._small_dataset_insight(dataset_id, version_id, stats, suffix))
                except Exception as exc:
                    logger.debug(f"[{self.name}] small_dataset rule failed for {file_label}: {exc}")

                try:
                    insights.extend(self._missing_values_insights(dataset_id, version_id, stats, suffix))
                except Exception as exc:
                    logger.debug(f"[{self.name}] missing_values rule failed for {file_label}: {exc}")

                try:
                    insights.extend(self._constant_column_insights(dataset_id, version_id, stats, suffix))
                except Exception as exc:
                    logger.debug(f"[{self.name}] constant_column rule failed for {file_label}: {exc}")

                try:
                    insights.extend(self._high_cardinality_insights(dataset_id, version_id, stats, suffix))
                except Exception as exc:
                    logger.debug(f"[{self.name}] high_cardinality rule failed for {file_label}: {exc}")

            except Exception as exc:
                logger.warning(f"[{self.name}] Error analyzing {csv_path}: {exc}")

        return insights

    # ------------------------------------------------------------------
    # CSV stats computation (stdlib only — no pandas dependency)
    # ------------------------------------------------------------------

    def _compute_stats(self, csv_path: Path) -> Optional[Dict[str, Any]]:
        """Compute column-level statistics from a CSV file using stdlib csv."""
        import csv
        import math

        try:
            with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    return None
                columns = list(reader.fieldnames)
                rows: List[Dict[str, str]] = []
                for i, row in enumerate(reader):
                    if i >= 10000:  # safety cap
                        break
                    rows.append(row)
        except Exception as exc:
            logger.debug(f"[{self.name}] Cannot read {csv_path}: {exc}")
            return None

        if not columns or not rows:
            return None

        total_rows = len(rows)
        col_stats: Dict[str, Dict[str, Any]] = {}

        for col in columns:
            vals = [r.get(col, "") for r in rows]
            missing = sum(1 for v in vals if v is None or str(v).strip() == "")
            non_missing = [str(v).strip() for v in vals if v is not None and str(v).strip() != ""]
            unique_vals = set(non_missing)

            # Try to parse as numeric
            numeric_vals = []
            for v in non_missing:
                try:
                    numeric_vals.append(float(v))
                except ValueError:
                    pass

            is_numeric = len(numeric_vals) >= 0.5 * len(non_missing) if non_missing else False

            std_val = None
            if is_numeric and len(numeric_vals) > 1:
                mean_v = sum(numeric_vals) / len(numeric_vals)
                variance = sum((x - mean_v) ** 2 for x in numeric_vals) / len(numeric_vals)
                std_val = math.sqrt(variance)

            col_stats[col] = {
                "total": total_rows,
                "missing": missing,
                "missing_pct": (missing / total_rows * 100) if total_rows > 0 else 0.0,
                "unique_count": len(unique_vals),
                "is_numeric": is_numeric,
                "std": std_val,
                "is_constant": len(unique_vals) <= 1,
                "cardinality_ratio": len(unique_vals) / total_rows if total_rows > 0 else 0.0,
            }

        return {
            "file": str(csv_path.name),
            "total_rows": total_rows,
            "total_cols": len(columns),
            "columns": col_stats,
        }

    # ------------------------------------------------------------------
    # Individual rules
    # ------------------------------------------------------------------

    def _small_dataset_insight(
        self,
        dataset_id: str,
        version_id: str,
        stats: Dict[str, Any],
        suffix: str,
    ) -> List[DatasetInsight]:
        total_rows = stats["total_rows"]
        if total_rows >= 100:
            return []

        rule_id = f"small_tabular_dataset{suffix}"
        evidence = InsightEvidence(
            metric="total_rows",
            value=total_rows,
            unit="rows",
            threshold=100.0,
            source_artifact="tabular_file",
            source_path=f"file:{stats['file']}",
            explanation=f"File '{stats['file']}' contains only {total_rows} rows, which is below the minimum recommended size of 100.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.DATASET_COVERAGE,
                severity=InsightSeverity.MEDIUM,
                confidence=InsightConfidence.HIGH,
                title=f"Very small tabular dataset ({total_rows} rows)",
                summary=f"File '{stats['file']}' has only {total_rows} rows, which may be insufficient for reliable model training.",
                explanation=(
                    f"'{stats['file']}' contains {total_rows} rows. "
                    "Models trained on fewer than 100 rows are prone to overfitting "
                    "and produce unreliable evaluation metrics due to high variance."
                ),
                evidence=[evidence],
                impact="Insufficient data leads to overfitting and poor generalization.",
                recommended_action=(
                    "Collect additional data to reach at least several hundred rows. "
                    "If limited data is unavoidable, use cross-validation and regularization."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _missing_values_insights(
        self,
        dataset_id: str,
        version_id: str,
        stats: Dict[str, Any],
        suffix: str,
    ) -> List[DatasetInsight]:
        results = []
        file_name = stats["file"]

        for col, col_stats in stats["columns"].items():
            pct = col_stats["missing_pct"]
            if pct == 0:
                continue

            if pct >= 100:
                severity = InsightSeverity.CRITICAL
                threshold = 100.0
            elif pct >= 50:
                severity = InsightSeverity.HIGH
                threshold = 50.0
            elif pct >= 20:
                severity = InsightSeverity.MEDIUM
                threshold = 20.0
            else:
                continue

            rule_id = f"missing_values-{col[:30]}{suffix}"
            evidence = InsightEvidence(
                metric="missing_value_pct",
                value=round(pct, 1),
                unit="percent",
                threshold=threshold,
                source_artifact="tabular_file",
                source_path=f"file:{file_name}/column:{col}",
                explanation=f"Column '{col}' in '{file_name}' has {round(pct, 1)}% missing values.",
            )
            results.append(
                DatasetInsight(
                    insight_id=_make_id(dataset_id, version_id, rule_id),
                    dataset_id=dataset_id,
                    version_id=version_id,
                    category=InsightCategory.MISSING_VALUES,
                    severity=severity,
                    confidence=InsightConfidence.HIGH,
                    title=f"High missing values in column '{col}' ({round(pct, 1)}%)",
                    summary=f"Column '{col}' has {round(pct, 1)}% missing values in '{file_name}'.",
                    explanation=(
                        f"Column '{col}' in '{file_name}' has {round(pct, 1)}% missing values. "
                        "High missingness reduces predictive power and may require imputation or column removal."
                    ),
                    evidence=[evidence],
                    affected_columns=[col],
                    impact="Missing values degrade model performance and require explicit imputation strategies.",
                    recommended_action=(
                        "Investigate why values are missing (MCAR, MAR, or MNAR). "
                        "Apply appropriate imputation (mean/median for numeric, mode for categorical) "
                        "or remove the column if missingness exceeds 50%."
                    ),
                    created_at=_now(),
                    analyzer_id=self.name,
                    rule_id=rule_id,
                )
            )

        return results

    def _constant_column_insights(
        self,
        dataset_id: str,
        version_id: str,
        stats: Dict[str, Any],
        suffix: str,
    ) -> List[DatasetInsight]:
        results = []
        file_name = stats["file"]

        constant_cols = [col for col, cs in stats["columns"].items() if cs["is_constant"]]
        if not constant_cols:
            return []

        rule_id = f"constant_columns{suffix}"
        evidence = InsightEvidence(
            metric="constant_column_count",
            value=len(constant_cols),
            unit="columns",
            source_artifact="tabular_file",
            source_path=f"file:{file_name}/constant_columns",
            explanation=f"{len(constant_cols)} column(s) in '{file_name}' have only one unique value and carry no predictive information.",
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.DATA_QUALITY,
                severity=InsightSeverity.MEDIUM,
                confidence=InsightConfidence.HIGH,
                title=f"{len(constant_cols)} constant column(s) in '{file_name}'",
                summary=f"{len(constant_cols)} column(s) have only one unique value and carry no predictive signal.",
                explanation=(
                    f"The following column(s) in '{file_name}' have zero variance: "
                    f"{', '.join(constant_cols[:10])}. "
                    "Constant columns provide no discriminatory information and add noise to feature spaces."
                ),
                evidence=[evidence],
                affected_columns=constant_cols[:20],
                impact="Constant features add no information and may cause numerical issues in some models.",
                recommended_action="Remove constant columns from the feature set before training.",
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

    def _high_cardinality_insights(
        self,
        dataset_id: str,
        version_id: str,
        stats: Dict[str, Any],
        suffix: str,
    ) -> List[DatasetInsight]:
        file_name = stats["file"]
        high_card_cols = []

        for col, cs in stats["columns"].items():
            if cs["is_numeric"]:
                continue
            if cs["unique_count"] > 50 and cs["cardinality_ratio"] > 0.8:
                high_card_cols.append((col, cs["unique_count"], cs["cardinality_ratio"]))

        if not high_card_cols:
            return []

        rule_id = f"high_cardinality_categorical{suffix}"
        col_names = [c[0] for c in high_card_cols]
        evidence = InsightEvidence(
            metric="high_cardinality_column_count",
            value=len(high_card_cols),
            unit="columns",
            source_artifact="tabular_file",
            source_path=f"file:{file_name}/high_cardinality_columns",
            explanation=(
                f"{len(high_card_cols)} categorical column(s) have >80% cardinality ratio, "
                "meaning nearly every row has a unique value."
            ),
        )
        return [
            DatasetInsight(
                insight_id=_make_id(dataset_id, version_id, rule_id),
                dataset_id=dataset_id,
                version_id=version_id,
                category=InsightCategory.DATA_QUALITY,
                severity=InsightSeverity.LOW,
                confidence=InsightConfidence.MEDIUM,
                title=f"{len(high_card_cols)} high-cardinality categorical column(s)",
                summary=f"{len(high_card_cols)} categorical column(s) have very high unique value counts (likely IDs).",
                explanation=(
                    f"Column(s) {', '.join(col_names[:5])} in '{file_name}' have very high cardinality (>80% unique values). "
                    "These are likely identifier or free-text fields that should not be used as categorical features directly."
                ),
                evidence=[evidence],
                affected_columns=col_names[:20],
                impact="High-cardinality columns used as features cause overfitting and poor generalization.",
                recommended_action=(
                    "Drop or encode high-cardinality columns appropriately. "
                    "Consider hashing, embedding, or target encoding for meaningful high-cardinality fields."
                ),
                created_at=_now(),
                analyzer_id=self.name,
                rule_id=rule_id,
            )
        ]

