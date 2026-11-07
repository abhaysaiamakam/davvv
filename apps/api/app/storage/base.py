from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class StorageBackend(ABC):
    """Abstract storage interface for CropLens dataset lifecycle management."""

    @abstractmethod
    def initialize(self) -> None:
        """Ensure all required root directories exist with appropriate permissions."""
        pass

    @abstractmethod
    def get_upload_path(self, dataset_id: str, filename: str) -> Path:
        """Resolve a safe destination path for an incoming dataset upload."""
        pass

    @abstractmethod
    def get_extract_path(self, dataset_id: str) -> Path:
        """Resolve a directory for temporary staging of extracted dataset contents."""
        pass

    @abstractmethod
    def get_results_path(self, analysis_id: str) -> Path:
        """Resolve a directory for persistent analysis artifacts, metrics, and logs."""
        pass

    @abstractmethod
    def get_curated_path(self, slug: str) -> Path:
        """Resolve the path for curated reference datasets."""
        pass

    @abstractmethod
    def resolve_dataset_path(self, dataset: Any) -> Path:
        """Resolve root path for any registered dataset (curated or uploaded)."""
        pass

    @abstractmethod
    def sanitize_relative_path(self, absolute_path: Path) -> str:
        """
        Convert an absolute filesystem path into a safe, client-facing relative path,
        ensuring host machine details are never exposed.
        """
        pass

    @abstractmethod
    def is_safe_path(self, target_path: Path) -> bool:
        """Verify that a path resides strictly within the configured storage root."""
        pass

    @abstractmethod
    def get_storage_status(self) -> Dict[str, Any]:
        """Return high-level storage readiness information without exposing sensitive system paths."""
        pass

    @abstractmethod
    def save_analysis(
        self,
        analysis_id: str,
        data: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Path:
        """Persist structured analysis result to disk under results storage."""
        pass

    @abstractmethod
    def load_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted analysis result from disk by its analysis identifier."""
        pass

    @abstractmethod
    def get_latest_analysis_id_for_dataset(self, dataset_id: str) -> Optional[str]:
        """Retrieve the identifier of the latest persisted analysis for a dataset."""
        pass

    @abstractmethod
    def list_persisted_analyses(self) -> List[Dict[str, Any]]:
        """List all persisted analysis records from disk."""
        pass

    @abstractmethod
    def save_quality_assessment(
        self,
        assessment_id: str,
        data: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Path:
        """Persist structured quality assessment result to disk under results/quality storage."""
        pass

    @abstractmethod
    def load_quality_assessment(self, assessment_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted quality assessment result from disk by its identifier."""
        pass

    @abstractmethod
    def get_latest_quality_assessment_id_for_dataset(self, dataset_id: str) -> Optional[str]:
        """Retrieve the identifier of the latest persisted quality assessment for a dataset."""
        pass

    @abstractmethod
    def list_persisted_quality_assessments(self) -> List[Dict[str, Any]]:
        """List all persisted quality assessment records from disk."""
        pass

    @abstractmethod
    def save_eda_report(
        self,
        eda_id: str,
        data: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Path:
        """Persist structured EDA report to disk under results/eda storage."""
        pass

    @abstractmethod
    def load_eda_report(self, eda_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted EDA report from disk by its identifier."""
        pass

    @abstractmethod
    def get_latest_eda_report_id_for_dataset(self, dataset_id: str) -> Optional[str]:
        """Retrieve the identifier of the latest persisted EDA report for a dataset."""
        pass

    @abstractmethod
    def list_persisted_eda_reports(self) -> List[Dict[str, Any]]:
        """List all persisted EDA report records from disk."""
        pass

    # -------------------------------------------------------------------------
    # M5 — Dataset Comparison
    # -------------------------------------------------------------------------

    @abstractmethod
    def save_comparison(
        self,
        comparison_id: str,
        data: Dict[str, Any],
        dataset_a_id: Optional[str] = None,
        dataset_b_id: Optional[str] = None,
    ) -> Path:
        """Persist structured comparison report to disk under results/comparisons storage."""
        pass

    @abstractmethod
    def load_comparison(self, comparison_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted comparison report from disk by its identifier."""
        pass

    @abstractmethod
    def get_latest_comparison_id_for_pair(
        self, dataset_a_id: str, dataset_b_id: str
    ) -> Optional[str]:
        """Retrieve the identifier of the latest persisted comparison for a dataset pair."""
        pass

    @abstractmethod
    def list_persisted_comparisons(self) -> List[Dict[str, Any]]:
        """List all persisted comparison report records from disk."""
        pass

    # -------------------------------------------------------------------------
    # M6 — Dynamic Datasets, Versions & Jobs
    # -------------------------------------------------------------------------

    @abstractmethod
    def save_dataset_metadata(self, dataset_id: str, data: Dict[str, Any]) -> Path:
        """Persist dynamic dataset metadata definition to disk."""
        pass

    @abstractmethod
    def load_dataset_metadata(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted dynamic dataset metadata from disk."""
        pass

    @abstractmethod
    def list_persisted_dataset_metadata(self) -> List[Dict[str, Any]]:
        """List all dynamically registered dataset metadata records from disk."""
        pass

    @abstractmethod
    def save_dataset_version(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist a dataset version record to disk."""
        pass

    @abstractmethod
    def load_dataset_version(
        self, dataset_id: str, version_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load a persisted dataset version record from disk."""
        pass

    @abstractmethod
    def list_persisted_dataset_versions(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List all persisted version records for a dataset, sorted newest first."""
        pass

    @abstractmethod
    def save_job(self, job_id: str, data: Dict[str, Any]) -> Path:
        """Persist processing job state record to disk."""
        pass

    @abstractmethod
    def load_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted processing job record from disk."""
        pass

    @abstractmethod
    def list_persisted_jobs(self) -> List[Dict[str, Any]]:
        """List all persisted processing jobs from disk, sorted newest first."""
        pass

    @abstractmethod
    def save_visualizations(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist visualization collection for a dataset version."""
        pass

    @abstractmethod
    def load_visualizations(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load visualization collection for a dataset version (or latest)."""
        pass

    @abstractmethod
    def list_persisted_visualizations(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List all historical visualization collections for a dataset."""
        pass

    @abstractmethod
    def save_insights(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist insight collection for a dataset version and update latest pointer."""
        pass

    @abstractmethod
    def load_insights(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load insight collection for a dataset version (or latest)."""
        pass

    @abstractmethod
    def list_persisted_insights(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List all historical insight collections for a dataset."""
        pass

    @abstractmethod
    def load_insight_by_id(self, insight_id: str) -> Optional[Dict[str, Any]]:
        """Load a single insight by its insight_id from the item index."""
        pass

    @abstractmethod
    def save_preprocessing_history(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist preprocessing transformation history for a derived dataset version."""
        pass

    @abstractmethod
    def load_preprocessing_history(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load preprocessing history for a specific version or latest."""
        pass

    @abstractmethod
    def list_persisted_preprocessing_history(
        self, dataset_id: str
    ) -> List[Dict[str, Any]]:
        """List all historical preprocessing records for a dataset."""
        pass

    @abstractmethod
    def save_readiness_assessment(
        self, dataset_id: str, version_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist dataset readiness assessment."""
        pass

    @abstractmethod
    def load_readiness_assessment(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load dataset readiness assessment for version or latest."""
        pass

    @abstractmethod
    def save_analytical_report(
        self, dataset_id: str, version_id: str, report_id: str, data: Dict[str, Any]
    ) -> Path:
        """Persist unified analytical report object."""
        pass

    @abstractmethod
    def load_analytical_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Load unified analytical report by report_id."""
        pass

    @abstractmethod
    def list_analytical_reports(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List persisted reports for a dataset or dataset version."""
        pass

    @abstractmethod
    def save_report_export_file(
        self, dataset_id: str, report_id: str, filename: str, content_bytes: bytes
    ) -> Path:
        """Save exported report file (PDF or JSON)."""
        pass

    @abstractmethod
    def get_report_export_file_path(
        self, dataset_id: str, report_id: str, filename: str
    ) -> Optional[Path]:
        """Get path to exported report file."""
        pass
