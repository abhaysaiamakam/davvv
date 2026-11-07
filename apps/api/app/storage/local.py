import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from app.core.config import Settings, settings as default_settings
from app.core.errors import PathTraversalError, StorageError
from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage implementation for CropLens."""

    def __init__(self, cfg: Optional[Settings] = None):
        self._cfg = cfg

    @property
    def base_dir(self) -> Path:
        if self._cfg:
            return self._cfg.STORAGE_BASE_DIR.resolve()
        env_base = os.getenv("CROPLENS_STORAGE_BASE_DIR")
        if env_base:
            return Path(env_base).resolve()
        return default_settings.STORAGE_BASE_DIR.resolve()

    @property
    def uploads_dir(self) -> Path:
        dirname = (self._cfg or default_settings).STORAGE_UPLOADS_DIRNAME
        return (self.base_dir / dirname).resolve()

    @property
    def extract_dir(self) -> Path:
        dirname = (self._cfg or default_settings).STORAGE_EXTRACT_DIRNAME
        return (self.base_dir / dirname).resolve()

    @property
    def results_dir(self) -> Path:
        dirname = (self._cfg or default_settings).STORAGE_RESULTS_DIRNAME
        return (self.base_dir / dirname).resolve()

    @property
    def curated_dir(self) -> Path:
        dirname = (self._cfg or default_settings).STORAGE_CURATED_DIRNAME
        return (self.base_dir / dirname).resolve()

    @property
    def jobs_dir(self) -> Path:
        dirname = getattr(self._cfg or default_settings, "STORAGE_JOBS_DIRNAME", "jobs")
        return (self.base_dir / dirname).resolve()

    @property
    def visualizations_dir(self) -> Path:
        dirname = getattr(
            self._cfg or default_settings,
            "STORAGE_VISUALIZATIONS_DIRNAME",
            "visualizations",
        )
        return (self.results_dir / dirname).resolve()

    @property
    def insights_dir(self) -> Path:
        return (self.results_dir / "insights").resolve()

    @property
    def preprocessing_dir(self) -> Path:
        return (self.results_dir / "preprocessing").resolve()

    @property
    def readiness_dir(self) -> Path:
        return (self.results_dir / "readiness").resolve()

    @property
    def reports_dir(self) -> Path:
        return (self.results_dir / "reports").resolve()

    @property
    def external_curated_dir(self) -> Optional[Path]:
        env_ext = os.getenv("CROPLENS_CURATED_DATASETS_DIR")
        if env_ext:
            p = Path(env_ext).resolve()
            if p.exists():
                return p
        cfg = self._cfg or default_settings
        if cfg.CURATED_DATASETS_DIR and cfg.CURATED_DATASETS_DIR.exists():
            return cfg.CURATED_DATASETS_DIR.resolve()
        return None

    def initialize(self) -> None:
        """Create storage directory tree if it does not already exist."""
        try:
            for directory in [
                self.base_dir,
                self.uploads_dir,
                self.extract_dir,
                self.results_dir,
                self.quality_dir,
                self.eda_dir,
                self.comparison_dir,
                self.curated_dir,
                self.jobs_dir,
                self.visualizations_dir,
                self.insights_dir,
                self.preprocessing_dir,
                self.readiness_dir,
                self.reports_dir,
            ]:
                directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Failed to initialize storage directories: {exc}")

    def is_safe_path(self, target_path: Path) -> bool:
        """Prevent directory traversal attacks by validating path ancestry."""
        try:
            abs_target = target_path.absolute()
            abs_base = self.base_dir.absolute()

            # Check lexical base containment
            if abs_base == abs_target or abs_base in abs_target.parents:
                return True

            # Check resolved base containment
            resolved = target_path.resolve()
            if self.base_dir == resolved or self.base_dir in resolved.parents:
                return True

            # If target is inside external curated directory (if configured)
            if self.external_curated_dir:
                ext_abs = self.external_curated_dir.absolute()
                if ext_abs == abs_target or ext_abs in abs_target.parents:
                    return True
                ext_res = self.external_curated_dir.resolve()
                if ext_res == resolved or ext_res in resolved.parents:
                    return True

            return False
        except Exception:
            return False

    def sanitize_relative_path(self, absolute_path: Path) -> str:
        """
        Convert an absolute server path to a sanitized storage-relative path string.
        Never exposes the host OS directory root to the API or client.
        """
        try:
            resolved = absolute_path.resolve()
            if self.base_dir in resolved.parents or self.base_dir == resolved:
                rel = resolved.relative_to(self.base_dir)
                return str(rel).replace("\\", "/")

            if self.external_curated_dir and (
                self.external_curated_dir in resolved.parents
                or self.external_curated_dir == resolved
            ):
                rel = resolved.relative_to(self.external_curated_dir)
                rel_str = str(rel).replace("\\", "/")
                return f"curated/{rel_str}"

            if self.base_dir in absolute_path.parents or self.base_dir == absolute_path:
                rel = absolute_path.relative_to(self.base_dir)
                return str(rel).replace("\\", "/")

            return f"curated/{absolute_path.name}"
        except Exception:
            return absolute_path.name

    def _sanitize_id(self, identifier: str) -> str:
        """Validate and clean dataset/analysis ID to prevent path traversal characters."""
        if not identifier or ".." in identifier or "/" in identifier or "\\" in identifier:
            raise PathTraversalError()
        cleaned = "".join(c for c in identifier if c.isalnum() or c in ("-", "_")).strip()
        if not cleaned or cleaned != identifier:
            raise PathTraversalError()
        return cleaned

    def get_upload_path(self, dataset_id: str, filename: str) -> Path:
        safe_id = self._sanitize_id(dataset_id)
        safe_filename = Path(filename).name
        target_dir = self.uploads_dir / safe_id
        target_path = target_dir / safe_filename
        if not self.is_safe_path(target_path):
            raise PathTraversalError()
        return target_path

    def get_extract_path(self, dataset_id: str) -> Path:
        safe_id = self._sanitize_id(dataset_id)
        target = self.extract_dir / safe_id
        if not self.is_safe_path(target):
            raise PathTraversalError()
        return target

    def get_results_path(self, analysis_id: str) -> Path:
        safe_id = self._sanitize_id(analysis_id)
        target = self.results_dir / safe_id
        if not self.is_safe_path(target):
            raise PathTraversalError()
        return target

    def get_curated_path(self, slug: str) -> Path:
        safe_slug = self._sanitize_id(slug)
        primary_target = self.curated_dir / safe_slug
        if primary_target.exists():
            return primary_target

        # Check external curated directory if configured
        if self.external_curated_dir and self.external_curated_dir.exists():
            ext_target = self.external_curated_dir / safe_slug
            if ext_target.exists():
                return ext_target

            # Known directory aliases for agricultural benchmarks
            aliases = {
                "icar-rice-maize": ["Rice_and_Maize_Dataset", "icar_rice_maize"],
                "paddy-doctor": ["paddy-disease-classification", "paddy_doctor"],
                "mendeley-rice": ["Rice_Leaf_Disease_Mendeley_Original", "rice_leaf_dataset"],
                "plant-village": ["plantvillage_data", "plant_village"],
                "plant-doc": ["PlantDoc-Object-Detection-Dataset-master", "plant_doc"],
                "chilli-leaf": ["Image Dataset on Chili Leaf Diseases in the Krishn", "chilli_leaf"],
            }
            if safe_slug in aliases:
                for alias in aliases[safe_slug]:
                    candidate = self.external_curated_dir / alias
                    if candidate.exists():
                        return candidate

        return primary_target

    def resolve_dataset_path(self, dataset: Any) -> Path:
        """Resolve the target directory for a dataset metadata instance."""
        if getattr(dataset, "is_curated", False):
            return self.get_curated_path(getattr(dataset, "slug", getattr(dataset, "id", "")))
        if getattr(dataset, "is_uploaded", False):
            rel = getattr(dataset, "storage_relative_path", None)
            if rel:
                target = (self.base_dir / rel).resolve()
                if self.is_safe_path(target) and target.exists():
                    return target
            return self.get_extract_path(getattr(dataset, "id", ""))
        return self.curated_dir / self._sanitize_id(getattr(dataset, "slug", getattr(dataset, "id", "")))

    def get_storage_status(self) -> Dict[str, Any]:
        """Return readiness info without leaking host filesystem details."""
        total, used, free = shutil.disk_usage(self.base_dir if self.base_dir.exists() else Path.cwd())
        return {
            "initialized": self.base_dir.exists(),
            "storage_type": "local_filesystem",
            "disk_free_gb": round(free / (1024**3), 2),
            "disk_total_gb": round(total / (1024**3), 2),
            "directories_ready": {
                "uploads": self.uploads_dir.exists(),
                "extracted": self.extract_dir.exists(),
                "results": self.results_dir.exists(),
                "curated": self.curated_dir.exists(),
            },
            "external_curated_configured": self.external_curated_dir is not None,
        }

    def save_analysis(
        self,
        analysis_id: str,
        data: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Path:
        """
        Persist a structured analysis result dictionary as JSON under results_dir.
        Also writes an index/pointer for the dataset's latest analysis run.
        """
        safe_analysis_id = self._sanitize_id(analysis_id)
        target_dir = self.results_dir / safe_analysis_id
        target_dir.mkdir(parents=True, exist_ok=True)
        result_file = target_dir / "result.json"

        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write analysis result {analysis_id}: {exc}")

        # Update dataset pointer to this latest analysis
        ds_id = dataset_id or data.get("dataset_id")
        if ds_id:
            try:
                safe_ds = self._sanitize_id(str(ds_id))
                ds_pointer_dir = self.results_dir / "datasets" / safe_ds
                ds_pointer_dir.mkdir(parents=True, exist_ok=True)
                pointer_file = ds_pointer_dir / "latest.json"
                with open(pointer_file, "w", encoding="utf-8") as pf:
                    json.dump(
                        {
                            "latest_analysis_id": safe_analysis_id,
                            "dataset_id": str(ds_id),
                            "updated_at": data.get("completed_at") or data.get("created_at"),
                        },
                        pf,
                        indent=2,
                    )
            except Exception as ptr_exc:
                logger.warning(f"Failed to write latest pointer for dataset {ds_id}: {ptr_exc}")

        return result_file

    def load_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Load a persisted analysis result from disk."""
        try:
            safe_analysis_id = self._sanitize_id(analysis_id)
        except PathTraversalError:
            return None

        result_file = self.results_dir / safe_analysis_id / "result.json"
        if not result_file.is_file():
            return None

        try:
            with open(result_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read analysis result from {result_file}: {exc}")
            return None

    def get_latest_analysis_id_for_dataset(self, dataset_id: str) -> Optional[str]:
        """Retrieve the identifier of the latest persisted analysis for a dataset."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None

        pointer_file = self.results_dir / "datasets" / safe_ds / "latest.json"
        if pointer_file.is_file():
            try:
                with open(pointer_file, "r", encoding="utf-8") as f:
                    ptr = json.load(f)
                    return ptr.get("latest_analysis_id")
            except Exception as exc:
                logger.warning(f"Failed to read dataset pointer file {pointer_file}: {exc}")

        # Fallback: scan analyses looking for dataset_id
        candidates = []
        for analysis in self.list_persisted_analyses():
            if analysis.get("dataset_id") == dataset_id:
                candidates.append(analysis)
        if candidates:
            # Sort by created_at descending
            candidates.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            return candidates[0].get("id")

        return None

    def list_persisted_analyses(self) -> List[Dict[str, Any]]:
        """List all persisted analysis records from disk, sorted newest first."""
        results: List[Dict[str, Any]] = []
        if not self.results_dir.exists():
            return results

        try:
            for item in self.results_dir.iterdir():
                # Skip the "datasets" pointer directory, "quality" directory, "eda" directory, "comparisons" directory, and non-directories
                if not item.is_dir() or item.name in ("datasets", "quality", "eda", "comparisons"):
                    continue
                result_file = item / "result.json"
                if result_file.is_file():
                    try:
                        with open(result_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            results.append(data)
                    except Exception as exc:
                        logger.warning(f"Error reading {result_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list results directory: {exc}")

        # Sort descending by created_at
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results


    @property
    def quality_dir(self) -> Path:
        """Subdirectory under results_dir for data quality assessments."""
        return self.results_dir / "quality"

    @property
    def eda_dir(self) -> Path:
        """Subdirectory under results_dir for EDA reports."""
        return self.results_dir / "eda"

    @property
    def comparison_dir(self) -> Path:
        """Subdirectory under results_dir for dataset comparison reports."""
        return self.results_dir / "comparisons"

    def save_quality_assessment(
        self,
        assessment_id: str,
        data: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Path:
        """
        Persist structured data quality assessment dictionary as JSON under quality_dir.
        Also writes an index/pointer for the dataset's latest quality assessment run.
        """
        safe_assessment_id = self._sanitize_id(assessment_id)
        target_dir = self.quality_dir / safe_assessment_id
        target_dir.mkdir(parents=True, exist_ok=True)
        result_file = target_dir / "assessment.json"

        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write quality assessment {assessment_id}: {exc}")

        # Update dataset pointer to this latest quality assessment
        ds_id = dataset_id or data.get("dataset_id")
        if ds_id:
            try:
                safe_ds = self._sanitize_id(str(ds_id))
                ds_pointer_dir = self.quality_dir / "datasets" / safe_ds
                ds_pointer_dir.mkdir(parents=True, exist_ok=True)
                pointer_file = ds_pointer_dir / "latest.json"
                with open(pointer_file, "w", encoding="utf-8") as pf:
                    json.dump(
                        {
                            "latest_assessment_id": safe_assessment_id,
                            "dataset_id": str(ds_id),
                            "updated_at": data.get("completed_at") or data.get("created_at"),
                        },
                        pf,
                        indent=2,
                    )
            except Exception as ptr_exc:
                logger.warning(f"Failed to write latest quality pointer for dataset {ds_id}: {ptr_exc}")

        return result_file

    def load_quality_assessment(self, assessment_id: str) -> Optional[Dict[str, Any]]:
        """Load a persisted data quality assessment result from disk."""
        try:
            safe_assessment_id = self._sanitize_id(assessment_id)
        except PathTraversalError:
            return None

        result_file = self.quality_dir / safe_assessment_id / "assessment.json"
        if not result_file.is_file():
            return None

        try:
            with open(result_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read quality assessment from {result_file}: {exc}")
            return None

    def get_latest_quality_assessment_id_for_dataset(self, dataset_id: str) -> Optional[str]:
        """Retrieve the identifier of the latest persisted quality assessment for a dataset."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None

        pointer_file = self.quality_dir / "datasets" / safe_ds / "latest.json"
        if pointer_file.is_file():
            try:
                with open(pointer_file, "r", encoding="utf-8") as f:
                    ptr = json.load(f)
                    return ptr.get("latest_assessment_id")
            except Exception as exc:
                logger.warning(f"Failed to read dataset quality pointer file {pointer_file}: {exc}")

        # Fallback: scan quality assessments looking for dataset_id
        candidates = []
        for assessment in self.list_persisted_quality_assessments():
            if assessment.get("dataset_id") == dataset_id:
                candidates.append(assessment)
        if candidates:
            candidates.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            return candidates[0].get("id")

        return None

    def list_persisted_quality_assessments(self) -> List[Dict[str, Any]]:
        """List all persisted quality assessment records from disk, sorted newest first."""
        results: List[Dict[str, Any]] = []
        if not self.quality_dir.exists():
            return results

        try:
            for item in self.quality_dir.iterdir():
                if not item.is_dir() or item.name == "datasets":
                    continue
                result_file = item / "assessment.json"
                if result_file.is_file():
                    try:
                        with open(result_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            results.append(data)
                    except Exception as exc:
                        logger.warning(f"Error reading quality assessment {result_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list quality results directory: {exc}")

        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results


    def save_eda_report(
        self,
        eda_id: str,
        data: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Path:
        """Persist structured EDA report as JSON under eda_dir."""
        safe_eda_id = self._sanitize_id(eda_id)
        target_dir = self.eda_dir / safe_eda_id
        target_dir.mkdir(parents=True, exist_ok=True)
        result_file = target_dir / "report.json"
        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write EDA report {eda_id}: {exc}")
        ds_id = dataset_id or data.get("dataset_id")
        if ds_id:
            try:
                safe_ds = self._sanitize_id(str(ds_id))
                ds_pointer_dir = self.eda_dir / "datasets" / safe_ds
                ds_pointer_dir.mkdir(parents=True, exist_ok=True)
                pointer_file = ds_pointer_dir / "latest.json"
                with open(pointer_file, "w", encoding="utf-8") as pf:
                    json.dump(
                        {
                            "latest_eda_id": safe_eda_id,
                            "dataset_id": str(ds_id),
                            "updated_at": data.get("completed_at") or data.get("created_at"),
                        },
                        pf,
                        indent=2,
                    )
            except Exception as ptr_exc:
                logger.warning(f"Failed to write latest EDA pointer for dataset {ds_id}: {ptr_exc}")
        return result_file

    def load_eda_report(self, eda_id: str) -> Optional[Dict[str, Any]]:
        """Load a persisted EDA report from disk."""
        try:
            safe_eda_id = self._sanitize_id(eda_id)
        except PathTraversalError:
            return None
        result_file = self.eda_dir / safe_eda_id / "report.json"
        if not result_file.is_file():
            return None
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read EDA report from {result_file}: {exc}")
            return None

    def get_latest_eda_report_id_for_dataset(self, dataset_id: str) -> Optional[str]:
        """Retrieve the identifier of the latest persisted EDA report for a dataset."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None
        pointer_file = self.eda_dir / "datasets" / safe_ds / "latest.json"
        if pointer_file.is_file():
            try:
                with open(pointer_file, "r", encoding="utf-8") as f:
                    ptr = json.load(f)
                    return ptr.get("latest_eda_id")
            except Exception as exc:
                logger.warning(f"Failed to read dataset EDA pointer file {pointer_file}: {exc}")
        candidates = []
        for report in self.list_persisted_eda_reports():
            if report.get("dataset_id") == dataset_id:
                candidates.append(report)
        if candidates:
            candidates.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            return candidates[0].get("id")
        return None

    def list_persisted_eda_reports(self) -> List[Dict[str, Any]]:
        """List all persisted EDA report records from disk, sorted newest first."""
        results: List[Dict[str, Any]] = []
        if not self.eda_dir.exists():
            return results
        try:
            for item in self.eda_dir.iterdir():
                if not item.is_dir() or item.name == "datasets":
                    continue
                result_file = item / "report.json"
                if result_file.is_file():
                    try:
                        with open(result_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            results.append(data)
                    except Exception as exc:
                        logger.warning(f"Error reading EDA report {result_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list EDA results directory: {exc}")
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results



    # -------------------------------------------------------------------------
    # M5 — Dataset Comparison
    # -------------------------------------------------------------------------

    def save_comparison(
        self,
        comparison_id: str,
        data: Dict[str, Any],
        dataset_a_id: Optional[str] = None,
        dataset_b_id: Optional[str] = None,
    ) -> Path:
        """Persist structured comparison report as JSON under comparison_dir."""
        try:
            safe_cmp_id = self._sanitize_id(comparison_id)
        except PathTraversalError:
            raise StorageError(f"Invalid comparison ID: {comparison_id!r}")
        target_dir = self.comparison_dir / safe_cmp_id
        target_dir.mkdir(parents=True, exist_ok=True)
        result_file = target_dir / "comparison.json"
        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write comparison report to {result_file}: {exc}")

        # Write pair pointer so we can quickly look up the latest comparison for a dataset pair
        if dataset_a_id and dataset_b_id:
            try:
                pair_key = "--".join(sorted([dataset_a_id, dataset_b_id]))
                safe_pair = self._sanitize_id(pair_key)
                pair_dir = self.comparison_dir / "pairs" / safe_pair
                pair_dir.mkdir(parents=True, exist_ok=True)
                ptr_file = pair_dir / "latest.json"
                with open(ptr_file, "w", encoding="utf-8") as pf:
                    json.dump(
                        {
                            "latest_comparison_id": safe_cmp_id,
                            "dataset_a_id": dataset_a_id,
                            "dataset_b_id": dataset_b_id,
                            "updated_at": data.get("completed_at") or data.get("created_at"),
                        },
                        pf,
                        indent=2,
                    )
            except Exception as ptr_exc:
                logger.warning(f"Failed to write latest comparison pointer for pair: {ptr_exc}")
        return result_file

    def load_comparison(self, comparison_id: str) -> Optional[Dict[str, Any]]:
        """Load a persisted comparison report from disk."""
        try:
            safe_cmp_id = self._sanitize_id(comparison_id)
        except PathTraversalError:
            return None
        result_file = self.comparison_dir / safe_cmp_id / "comparison.json"
        if not result_file.is_file():
            return None
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read comparison report from {result_file}: {exc}")
            return None

    def get_latest_comparison_id_for_pair(
        self, dataset_a_id: str, dataset_b_id: str
    ) -> Optional[str]:
        """Retrieve the identifier of the latest persisted comparison for a dataset pair."""
        pair_key = "--".join(sorted([dataset_a_id, dataset_b_id]))
        try:
            safe_pair = self._sanitize_id(pair_key)
        except PathTraversalError:
            return None
        pointer_file = self.comparison_dir / "pairs" / safe_pair / "latest.json"
        if pointer_file.is_file():
            try:
                with open(pointer_file, "r", encoding="utf-8") as f:
                    ptr = json.load(f)
                    return ptr.get("latest_comparison_id")
            except Exception as exc:
                logger.warning(f"Failed to read comparison pointer file {pointer_file}: {exc}")
        # Fallback: scan all comparisons
        candidates = []
        for cmp in self.list_persisted_comparisons():
            a = cmp.get("dataset_a_id", "")
            b = cmp.get("dataset_b_id", "")
            if set([a, b]) == set([dataset_a_id, dataset_b_id]):
                candidates.append(cmp)
        if candidates:
            candidates.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            return candidates[0].get("id")
        return None

    def list_persisted_comparisons(self) -> List[Dict[str, Any]]:
        """List all persisted comparison report records from disk, sorted newest first."""
        results: List[Dict[str, Any]] = []
        if not self.comparison_dir.exists():
            return results
        try:
            for item in self.comparison_dir.iterdir():
                if not item.is_dir() or item.name == "pairs":
                    continue
                result_file = item / "comparison.json"
                if result_file.is_file():
                    try:
                        with open(result_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            results.append(data)
                    except Exception as exc:
                        logger.warning(f"Error reading comparison report {result_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list comparisons directory: {exc}")
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results


    # -------------------------------------------------------------------------
    # M6 — Dynamic Datasets, Versions & Jobs
    # -------------------------------------------------------------------------

    def save_dataset_metadata(self, dataset_id: str, data: Dict[str, Any]) -> Path:
        """Persist dynamic dataset metadata definition to disk."""
        safe_id = self._sanitize_id(dataset_id)
        target_dir = self.results_dir / "datasets" / safe_id
        target_dir.mkdir(parents=True, exist_ok=True)
        meta_file = target_dir / "metadata.json"
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write dataset metadata to {meta_file}: {exc}")
        return meta_file

    def load_dataset_metadata(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted dynamic dataset metadata from disk."""
        try:
            safe_id = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None
        meta_file = self.results_dir / "datasets" / safe_id / "metadata.json"
        if not meta_file.is_file():
            return None
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read dataset metadata from {meta_file}: {exc}")
            return None

    def list_persisted_dataset_metadata(self) -> List[Dict[str, Any]]:
        """List all dynamically registered dataset metadata records from disk."""
        results: List[Dict[str, Any]] = []
        datasets_dir = self.results_dir / "datasets"
        if not datasets_dir.exists():
            return results
        try:
            for item in datasets_dir.iterdir():
                if not item.is_dir():
                    continue
                meta_file = item / "metadata.json"
                if meta_file.is_file():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception as exc:
                        logger.warning(f"Error reading dataset metadata {meta_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list datasets directory: {exc}")
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results


    def save_dataset_version(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist a dataset version record to disk."""
        safe_id = self._sanitize_id(dataset_id)
        safe_vid = self._sanitize_id(version_id)
        versions_dir = self.results_dir / "datasets" / safe_id / "versions"
        target_dir = versions_dir / safe_vid
        target_dir.mkdir(parents=True, exist_ok=True)
        version_file = target_dir / "version.json"
        try:
            with open(version_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write version record to {version_file}: {exc}")

        # Update latest version pointer if status is ready
        status = str(data.get("status", "")).lower()
        if status in ("ready", "completed", "validated"):
            ptr_file = versions_dir / "latest_version.json"
            try:
                with open(ptr_file, "w", encoding="utf-8") as pf:
                    json.dump(
                        {
                            "latest_version_id": safe_vid,
                            "dataset_id": dataset_id,
                            "version_number": data.get("version_number"),
                            "content_fingerprint": data.get("content_fingerprint"),
                            "updated_at": data.get("created_at"),
                        },
                        pf,
                        indent=2,
                    )
            except Exception as ptr_exc:
                logger.warning(f"Failed to update latest version pointer: {ptr_exc}")

        return version_file

    def load_dataset_version(
        self, dataset_id: str, version_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load a persisted dataset version record from disk."""
        try:
            safe_id = self._sanitize_id(dataset_id)
            safe_vid = self._sanitize_id(version_id)
        except PathTraversalError:
            return None
        version_file = (
            self.results_dir / "datasets" / safe_id / "versions" / safe_vid / "version.json"
        )
        if not version_file.is_file():
            return None
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read version file {version_file}: {exc}")
            return None

    def list_persisted_dataset_versions(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List all persisted version records for a dataset, sorted newest first."""
        results: List[Dict[str, Any]] = []
        try:
            safe_id = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return results
        versions_dir = self.results_dir / "datasets" / safe_id / "versions"
        if not versions_dir.exists():
            return results
        try:
            for item in versions_dir.iterdir():
                if not item.is_dir():
                    continue
                v_file = item / "version.json"
                if v_file.is_file():
                    try:
                        with open(v_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception as exc:
                        logger.warning(f"Error reading version file {v_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list dataset versions: {exc}")
        results.sort(key=lambda x: (x.get("version_number", 0), str(x.get("created_at", ""))), reverse=True)
        return results

    def save_job(self, job_id: str, data: Dict[str, Any]) -> Path:
        """Persist processing job state record to disk."""
        safe_jid = self._sanitize_id(job_id)
        target_dir = self.jobs_dir / safe_jid
        target_dir.mkdir(parents=True, exist_ok=True)
        job_file = target_dir / "job.json"
        try:
            with open(job_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write job record to {job_file}: {exc}")
        return job_file

    def load_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted processing job record from disk."""
        try:
            safe_jid = self._sanitize_id(job_id)
        except PathTraversalError:
            return None
        job_file = self.jobs_dir / safe_jid / "job.json"
        if not job_file.is_file():
            return None
        try:
            with open(job_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read job record {job_file}: {exc}")
            return None

    def list_persisted_jobs(self) -> List[Dict[str, Any]]:
        """List all persisted processing jobs from disk, sorted newest first."""
        results: List[Dict[str, Any]] = []
        if not self.jobs_dir.exists():
            return results
        try:
            for item in self.jobs_dir.iterdir():
                if not item.is_dir():
                    continue
                job_file = item / "job.json"
                if job_file.is_file():
                    try:
                        with open(job_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception as exc:
                        logger.warning(f"Error reading job file {job_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list jobs directory: {exc}")
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results

    def save_visualizations(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist visualization collection for a dataset version and update latest pointer."""
        safe_ds = self._sanitize_id(dataset_id)
        safe_ver = self._sanitize_id(version_id)

        target_dir = self.visualizations_dir / "datasets" / safe_ds / "versions" / safe_ver
        target_dir.mkdir(parents=True, exist_ok=True)
        collection_file = target_dir / "visualizations.json"

        try:
            with open(collection_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write visualizations for {dataset_id}/{version_id}: {exc}")

        # Update latest pointer for this dataset
        latest_dir = self.visualizations_dir / "datasets" / safe_ds
        latest_dir.mkdir(parents=True, exist_ok=True)
        latest_file = latest_dir / "latest.json"
        try:
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            logger.warning(f"Failed to update latest visualization pointer for {dataset_id}: {exc}")

        # Persist individual item specifications for quick ID lookup
        items = data.get("items", [])
        for item in items:
            vis_id = item.get("visualization_id")
            if vis_id:
                try:
                    safe_vid = self._sanitize_id(vis_id)
                    item_dir = self.visualizations_dir / "items" / safe_vid
                    item_dir.mkdir(parents=True, exist_ok=True)
                    with open(item_dir / "specification.json", "w", encoding="utf-8") as f:
                        json.dump(item, f, indent=2, default=str)
                except Exception as exc:
                    logger.debug(f"Could not index individual visualization item {vis_id}: {exc}")

        return collection_file

    def load_visualizations(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load visualization collection for a specific dataset version or latest."""
        safe_ds = self._sanitize_id(dataset_id)

        if version_id:
            safe_ver = self._sanitize_id(version_id)
            target_file = (
                self.visualizations_dir
                / "datasets"
                / safe_ds
                / "versions"
                / safe_ver
                / "visualizations.json"
            )
        else:
            target_file = self.visualizations_dir / "datasets" / safe_ds / "latest.json"

        if not target_file.is_file():
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read visualization file {target_file}: {exc}")
            return None

    def list_persisted_visualizations(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List all historical visualization collections for a dataset."""
        safe_ds = self._sanitize_id(dataset_id)
        versions_dir = self.visualizations_dir / "datasets" / safe_ds / "versions"
        results: List[Dict[str, Any]] = []

        if not versions_dir.exists():
            return results

        try:
            for v_dir in versions_dir.iterdir():
                if not v_dir.is_dir():
                    continue
                v_file = v_dir / "visualizations.json"
                if v_file.is_file():
                    try:
                        with open(v_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception as exc:
                        logger.warning(f"Error reading visualization collection {v_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list visualizations for {dataset_id}: {exc}")

        results.sort(key=lambda x: str(x.get("generated_at", "")), reverse=True)
        return results

    # -------------------------------------------------------------------------
    # M7 — Insights Storage
    # -------------------------------------------------------------------------

    def save_insights(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist insight collection for a dataset version and update latest pointer."""
        safe_ds = self._sanitize_id(dataset_id)
        safe_ver = self._sanitize_id(version_id)

        target_dir = self.insights_dir / "datasets" / safe_ds / "versions" / safe_ver
        target_dir.mkdir(parents=True, exist_ok=True)
        collection_file = target_dir / "insights.json"

        try:
            with open(collection_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write insights for {dataset_id}/{version_id}: {exc}")

        # Update latest pointer
        latest_dir = self.insights_dir / "datasets" / safe_ds
        latest_dir.mkdir(parents=True, exist_ok=True)
        latest_file = latest_dir / "latest.json"
        try:
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            logger.warning(f"Failed to update latest insights pointer for {dataset_id}: {exc}")

        # Index individual insight items for single-insight lookup by ID
        items = data.get("items", [])
        for item in items:
            iid = item.get("insight_id")
            if iid:
                try:
                    safe_iid = self._sanitize_id(iid)
                    item_dir = self.insights_dir / "items" / safe_iid
                    item_dir.mkdir(parents=True, exist_ok=True)
                    with open(item_dir / "insight.json", "w", encoding="utf-8") as f:
                        json.dump(item, f, indent=2, default=str)
                except Exception as exc:
                    logger.debug(f"Could not index individual insight item {iid}: {exc}")

        return collection_file

    def load_insights(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load insight collection for a specific dataset version or latest."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None

        if version_id:
            try:
                safe_ver = self._sanitize_id(version_id)
            except PathTraversalError:
                return None
            target_file = (
                self.insights_dir / "datasets" / safe_ds / "versions" / safe_ver / "insights.json"
            )
        else:
            target_file = self.insights_dir / "datasets" / safe_ds / "latest.json"

        if not target_file.is_file():
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read insights file {target_file}: {exc}")
            return None

    def list_persisted_insights(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List all historical insight collections for a dataset, sorted newest first."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return []
        versions_dir = self.insights_dir / "datasets" / safe_ds / "versions"
        results: List[Dict[str, Any]] = []

        if not versions_dir.exists():
            return results

        try:
            for v_dir in versions_dir.iterdir():
                if not v_dir.is_dir():
                    continue
                v_file = v_dir / "insights.json"
                if v_file.is_file():
                    try:
                        with open(v_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception as exc:
                        logger.warning(f"Error reading insight collection {v_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list insights for {dataset_id}: {exc}")

        results.sort(key=lambda x: str(x.get("generated_at", "")), reverse=True)
        return results

    def load_insight_by_id(self, insight_id: str) -> Optional[Dict[str, Any]]:
        """Load a single insight by its insight_id from the item index."""
        try:
            safe_iid = self._sanitize_id(insight_id)
        except PathTraversalError:
            return None
        item_file = self.insights_dir / "items" / safe_iid / "insight.json"
        if not item_file.is_file():
            return None
        try:
            with open(item_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read insight item {item_file}: {exc}")
            return None

    # -------------------------------------------------------------------------
    # M8 — Preprocessing History Storage
    # -------------------------------------------------------------------------

    def save_preprocessing_history(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist preprocessing transformation history for a derived dataset version."""
        safe_ds = self._sanitize_id(dataset_id)
        safe_ver = self._sanitize_id(version_id)

        target_dir = self.preprocessing_dir / "datasets" / safe_ds / "versions" / safe_ver
        target_dir.mkdir(parents=True, exist_ok=True)
        history_file = target_dir / "history.json"

        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write preprocessing history for {dataset_id}/{version_id}: {exc}")

        # Update latest pointer for this dataset
        latest_dir = self.preprocessing_dir / "datasets" / safe_ds
        latest_dir.mkdir(parents=True, exist_ok=True)
        latest_file = latest_dir / "latest.json"
        try:
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            logger.warning(f"Failed to update latest preprocessing pointer for {dataset_id}: {exc}")

        return history_file

    def load_preprocessing_history(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load preprocessing history for a specific version or latest."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None

        if version_id:
            try:
                safe_ver = self._sanitize_id(version_id)
            except PathTraversalError:
                return None
            target_file = (
                self.preprocessing_dir
                / "datasets"
                / safe_ds
                / "versions"
                / safe_ver
                / "history.json"
            )
        else:
            target_file = self.preprocessing_dir / "datasets" / safe_ds / "latest.json"

        if not target_file.is_file():
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read preprocessing history {target_file}: {exc}")
            return None

    def list_persisted_preprocessing_history(
        self, dataset_id: str
    ) -> List[Dict[str, Any]]:
        """List all historical preprocessing records for a dataset, sorted newest first."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return []
        versions_dir = self.preprocessing_dir / "datasets" / safe_ds / "versions"
        results: List[Dict[str, Any]] = []

        if not versions_dir.exists():
            return results

        try:
            for v_dir in versions_dir.iterdir():
                if not v_dir.is_dir():
                    continue
                v_file = v_dir / "history.json"
                if v_file.is_file():
                    try:
                        with open(v_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception as exc:
                        logger.warning(f"Error reading preprocessing history {v_file}: {exc}")
        except OSError as exc:
            logger.error(f"Failed to list preprocessing history for {dataset_id}: {exc}")

        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results

    # -------------------------------------------------------------------------
    # M10 — Readiness Assessment & Analytical Report Storage
    # -------------------------------------------------------------------------

    def save_readiness_assessment(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist dataset readiness assessment for a dataset version."""
        safe_ds = self._sanitize_id(dataset_id)
        safe_ver = self._sanitize_id(version_id)

        target_dir = self.readiness_dir / "datasets" / safe_ds / "versions" / safe_ver
        target_dir.mkdir(parents=True, exist_ok=True)
        readiness_file = target_dir / "readiness.json"

        try:
            with open(readiness_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write readiness assessment for {dataset_id}/{version_id}: {exc}")

        # Update latest pointer for this dataset
        latest_dir = self.readiness_dir / "datasets" / safe_ds
        latest_dir.mkdir(parents=True, exist_ok=True)
        latest_file = latest_dir / "latest.json"
        try:
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            logger.warning(f"Failed to update latest readiness pointer for {dataset_id}: {exc}")

        return readiness_file

    def load_readiness_assessment(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load readiness assessment for a specific dataset version or latest."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return None

        if version_id:
            try:
                safe_ver = self._sanitize_id(version_id)
            except PathTraversalError:
                return None
            target_file = (
                self.readiness_dir
                / "datasets"
                / safe_ds
                / "versions"
                / safe_ver
                / "readiness.json"
            )
        else:
            target_file = self.readiness_dir / "datasets" / safe_ds / "latest.json"

        if not target_file.is_file():
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read readiness assessment {target_file}: {exc}")
            return None

    def save_analytical_report(
        self, dataset_id: str, version_id: str, report_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist a unified analytical report object."""
        safe_ds = self._sanitize_id(dataset_id)
        safe_ver = self._sanitize_id(version_id)
        safe_rep = self._sanitize_id(report_id)

        target_dir = self.reports_dir / "datasets" / safe_ds / "versions" / safe_ver / safe_rep
        target_dir.mkdir(parents=True, exist_ok=True)
        report_file = target_dir / "report.json"

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            raise StorageError(f"Failed to write analytical report {report_id}: {exc}")

        # Maintain global report index file by report_id
        index_dir = self.reports_dir / "index"
        index_dir.mkdir(parents=True, exist_ok=True)
        index_file = index_dir / f"{safe_rep}.json"
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as exc:
            logger.warning(f"Failed to update report index for {report_id}: {exc}")

        return report_file

    def load_analytical_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Load unified analytical report by report_id."""
        try:
            safe_rep = self._sanitize_id(report_id)
        except PathTraversalError:
            return None

        index_file = self.reports_dir / "index" / f"{safe_rep}.json"
        if not index_file.is_file():
            return None

        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read report {index_file}: {exc}")
            return None

    def list_analytical_reports(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List persisted reports for a dataset or dataset version."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
        except PathTraversalError:
            return []

        results: List[Dict[str, Any]] = []

        if version_id:
            try:
                safe_ver = self._sanitize_id(version_id)
            except PathTraversalError:
                return []
            v_dir = self.reports_dir / "datasets" / safe_ds / "versions" / safe_ver
            if v_dir.exists():
                for rep_folder in v_dir.iterdir():
                    if rep_folder.is_dir():
                        r_file = rep_folder / "report.json"
                        if r_file.is_file():
                            try:
                                with open(r_file, "r", encoding="utf-8") as f:
                                    results.append(json.load(f))
                            except Exception:
                                pass
        else:
            ds_versions_dir = self.reports_dir / "datasets" / safe_ds / "versions"
            if ds_versions_dir.exists():
                for v_dir in ds_versions_dir.iterdir():
                    if v_dir.is_dir():
                        for rep_folder in v_dir.iterdir():
                            if rep_folder.is_dir():
                                r_file = rep_folder / "report.json"
                                if r_file.is_file():
                                    try:
                                        with open(r_file, "r", encoding="utf-8") as f:
                                            results.append(json.load(f))
                                    except Exception:
                                        pass

        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results

    def save_report_export_file(
        self, dataset_id: str, report_id: str, filename: str, content_bytes: bytes
    ) -> Path:
        """Save exported report file (PDF or JSON)."""
        safe_ds = self._sanitize_id(dataset_id)
        safe_rep = self._sanitize_id(report_id)
        safe_fname = "".join(c for c in filename if c.isalnum() or c in (".", "-", "_")).strip()

        export_dir = self.reports_dir / "exports" / safe_ds / safe_rep
        export_dir.mkdir(parents=True, exist_ok=True)
        export_file = export_dir / safe_fname

        try:
            with open(export_file, "wb") as f:
                f.write(content_bytes)
        except OSError as exc:
            raise StorageError(f"Failed to write report export file {filename}: {exc}")

        return export_file

    def get_report_export_file_path(
        self, dataset_id: str, report_id: str, filename: str
    ) -> Optional[Path]:
        """Get path to exported report file."""
        try:
            safe_ds = self._sanitize_id(dataset_id)
            safe_rep = self._sanitize_id(report_id)
            safe_fname = "".join(c for c in filename if c.isalnum() or c in (".", "-", "_")).strip()
        except PathTraversalError:
            return None

        export_file = self.reports_dir / "exports" / safe_ds / safe_rep / safe_fname
        if export_file.is_file():
            return export_file
        return None


# Global storage singleton
storage_backend = LocalStorageBackend()


def get_storage_backend() -> StorageBackend:
    return storage_backend
