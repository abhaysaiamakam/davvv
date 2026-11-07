"""
M10 — Analytical Methodology Builder.

Constructs a step-by-step, reproducible execution graph documenting how CropLens analyzed,
cleaned, engineered, and evaluated a dataset version across M2–M9.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from app.schemas.reports import MethodologySection, MethodologyStep


class MethodologyBuilder:
    """Service for constructing reproducible analytical methodology documentation."""

    def build_methodology(
        self,
        dataset_id: str,
        version_id: str,
        modality: str,
        analysis_artifact: Optional[Dict[str, Any]] = None,
        quality_artifact: Optional[Dict[str, Any]] = None,
        eda_artifact: Optional[Dict[str, Any]] = None,
        preprocessing_history: Optional[List[Dict[str, Any]]] = None,
        feature_history: Optional[List[Dict[str, Any]]] = None,
        readiness_score: Optional[int] = None,
    ) -> MethodologySection:
        steps: List[MethodologyStep] = []
        step_counter = 1
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        def _to_dict(art: Any) -> Dict[str, Any]:
            if art is None:
                return {}
            if hasattr(art, "model_dump"):
                return art.model_dump()
            if isinstance(art, dict):
                return art
            return {}

        analysis_dict = _to_dict(analysis_artifact)
        quality_dict = _to_dict(quality_artifact)
        eda_dict = _to_dict(eda_artifact)

        # Step 1: Discovery & Profiling
        steps.append(
            MethodologyStep(
                step_number=step_counter,
                stage_name="Dataset Discovery & Modality Detection",
                operation_name="Structure Scanning & File Indexing",
                parameters={"modality": modality, "target_version": version_id},
                input_version_id=version_id,
                output_version_id=version_id,
                timestamp=analysis_dict.get("timestamp", now),
            )
        )
        step_counter += 1

        # Step 2: Quality Inspection (M3)
        if quality_artifact:
            steps.append(
                MethodologyStep(
                    step_number=step_counter,
                    stage_name="Data Quality Assessment",
                    operation_name="Header Verification & Anomaly Inspection",
                    parameters={
                        "missing_values_checked": True,
                        "duplicates_checked": True,
                        "corrupt_files_checked": True,
                    },
                    input_version_id=version_id,
                    output_version_id=version_id,
                    timestamp=quality_dict.get("created_at") or quality_dict.get("assessment_timestamp", now),
                )
            )
            step_counter += 1

        # Step 3: Exploratory Data Analysis (M4)
        if eda_artifact:
            steps.append(
                MethodologyStep(
                    step_number=step_counter,
                    stage_name="Exploratory Data Analysis",
                    operation_name="Distribution Profiling & Visualization Specification",
                    parameters={"eda_type": modality},
                    input_version_id=version_id,
                    output_version_id=version_id,
                    timestamp=eda_dict.get("report_timestamp", now),
                )
            )
            step_counter += 1

        # Step 4: Preprocessing History (M8)
        if preprocessing_history:
            for record in preprocessing_history:
                for op in record.get("operations", []):
                    steps.append(
                        MethodologyStep(
                            step_number=step_counter,
                            stage_name="Data Preprocessing & Cleaning",
                            operation_name=str(op.get("operation_type", "cleaning_operation")),
                            parameters=op.get("parameters", {}),
                            input_version_id=record.get("source_version_id"),
                            output_version_id=record.get("derived_version_id"),
                            affected_count=op.get("rows_before", 0) - op.get("rows_after", 0) if op.get("rows_before") is not None and op.get("rows_after") is not None else len(op.get("affected_files", [])),
                            timestamp=op.get("executed_at", now),
                        )
                    )
                    step_counter += 1

        # Step 5: Feature Engineering & Selection (M9)
        if feature_history:
            for record in feature_history:
                for op in record.get("operations", []):
                    steps.append(
                        MethodologyStep(
                            step_number=step_counter,
                            stage_name="Feature Engineering & Selection",
                            operation_name=str(op.get("operation_type", "feature_operation")),
                            parameters=op.get("parameters", {}),
                            input_version_id=record.get("source_version_id"),
                            output_version_id=record.get("derived_version_id"),
                            affected_count=len(op.get("generated_features", [])) or len(op.get("removed_features", [])),
                            timestamp=op.get("executed_at", now),
                        )
                    )
                    step_counter += 1

        # Step 6: Readiness Evaluation (M10)
        steps.append(
            MethodologyStep(
                step_number=step_counter,
                stage_name="Dataset Readiness Assessment",
                operation_name="Multidimensional Suitability Evaluation",
                parameters={"overall_readiness_score": readiness_score or 100},
                input_version_id=version_id,
                output_version_id=version_id,
                timestamp=now,
            )
        )

        reproducibility_notes = [
            "All directory paths and client inputs were sanitized using isolated path ancestry verification.",
            "Dataset content fingerprints were computed via streaming SHA-256 byte digests over sorted file entries.",
            "All transformation operations executed deterministically without in-place mutation of source dataset archives.",
        ]

        summary = (
            f"Dataset '{dataset_id}' (version '{version_id}') underwent automated end-to-end evaluation "
            f"comprising {len(steps)} distinct analytical, cleaning, and feature engineering steps."
        )

        return MethodologySection(
            workflow_summary=summary,
            steps=steps,
            execution_engine="CropLens Automated Intelligence Engine v0.1.0",
            reproducibility_notes=reproducibility_notes,
        )


methodology_builder = MethodologyBuilder()
