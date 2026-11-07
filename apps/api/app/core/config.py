import os
from pathlib import Path
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "CropLens API"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # CORS configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Storage paths (Environment-configurable, default to local directory)
    # The base directory where raw, extracted, and computed data live
    STORAGE_BASE_DIR: Path = Path(
        os.getenv(
            "CROPLENS_STORAGE_BASE_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "storage_data"),
        )
    )

    # Subdirectories for specific lifecycle stages
    STORAGE_UPLOADS_DIRNAME: str = "uploads"
    STORAGE_EXTRACT_DIRNAME: str = "extracted"
    STORAGE_RESULTS_DIRNAME: str = "results"
    STORAGE_CURATED_DIRNAME: str = "curated"
    STORAGE_JOBS_DIRNAME: str = "jobs"
    STORAGE_VISUALIZATIONS_DIRNAME: str = "visualizations"

    # Upload and archive safety thresholds
    MAX_UPLOAD_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB
    MAX_EXTRACT_SIZE_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GB
    MAX_ARCHIVE_FILES: int = 20_000
    SUPPORTED_ARCHIVE_EXTENSIONS: List[str] = [".zip", ".tar", ".gz", ".tgz"]

    # Scalability & Memory-Efficient Processing Thresholds
    DUCKDB_HYBRID_THRESHOLD_BYTES: int = 10 * 1024 * 1024  # 10 MB
    DUCKDB_HYBRID_ROW_THRESHOLD: int = 25_000
    PREVIEW_SAMPLE_ROW_LIMIT: int = 1_000
    VISUALIZATION_SAMPLE_ROW_LIMIT: int = 20_000
    MAX_IMAGE_DECODE_PIXELS: int = 25_000_000  # 25 MP (~5000x5000)
    THUMBNAIL_MAX_DIMENSION: int = 300
    EXPORT_STREAM_CHUNK_SIZE: int = 64 * 1024  # 64 KB
    MAX_CONCURRENT_IMAGE_PROCESSING: int = 16

    # Optional external curated datasets root (e.g. for pre-existing local benchmarks)
    CURATED_DATASETS_DIR: Optional[Path] = (
        Path(os.environ["CROPLENS_CURATED_DATASETS_DIR"])
        if "CROPLENS_CURATED_DATASETS_DIR" in os.environ
        else None
    )

    @property
    def uploads_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / self.STORAGE_UPLOADS_DIRNAME

    @property
    def extract_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / self.STORAGE_EXTRACT_DIRNAME

    @property
    def results_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / self.STORAGE_RESULTS_DIRNAME

    @property
    def curated_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / self.STORAGE_CURATED_DIRNAME

    @property
    def jobs_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / self.STORAGE_JOBS_DIRNAME

    @property
    def visualizations_dir(self) -> Path:
        return self.results_dir / self.STORAGE_VISUALIZATIONS_DIRNAME


settings = Settings()

