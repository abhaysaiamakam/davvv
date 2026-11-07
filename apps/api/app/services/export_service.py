"""
Streaming Export Service for Large CSV, JSON, and ZIP Datasets.

Prevents in-memory buffer bloat by streaming export contents directly in chunks.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from app.core.config import settings
from app.services.tabular_engine import tabular_engine

logger = logging.getLogger(__name__)


class ExportService:
    """Handles memory-efficient streaming exports of datasets and report artifacts."""

    def stream_csv_file(self, file_path: Path, chunk_size: int = 65536) -> Generator[bytes, None, None]:
        """Stream CSV/TSV file contents in raw binary chunks."""
        if not file_path.is_file():
            raise FileNotFoundError(f"Export target file '{file_path.name}' not found.")

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def stream_dataset_zip(self, dataset_root: Path, target_zip_path: Path) -> Generator[bytes, None, None]:
        """Create and stream a ZIP archive of dataset_root in chunks."""
        target_zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in dataset_root.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    arcname = str(file_path.relative_to(dataset_root))
                    zf.write(file_path, arcname=arcname)

        yield from self.stream_csv_file(target_zip_path)


export_service = ExportService()
