from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import hashlib
import threading
import uuid
import zipfile
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.exports import ExportCreateRequest, ExportFormat, ExportJobResponse, ExportType
from app.services.dataset_service import dataset_service
from app.services.report_service import report_service
from app.storage.local import storage_backend

logger = logging.getLogger(__name__)

SECTIONS = {
    ExportType.EDA: "eda_section",
    ExportType.QUALITY: "quality_section",
    ExportType.PREPROCESSING: "preprocessing_section",
    ExportType.FEATURE_ENGINEERING: "feature_engineering_section",
    ExportType.READINESS: "readiness_section",
    ExportType.METHODOLOGY: "methodology_section",
}


class ExportJobService:
    """Version-bound report and dataset exports with pollable background status."""

    def __init__(self, max_workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="croplens-export")
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create(self, dataset_id: str, version_id: str, request: ExportCreateRequest) -> ExportJobResponse:
        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            from app.core.errors import DatasetNotFoundError
            raise DatasetNotFoundError(dataset_id)
        version = dataset_service.get_version(dataset_id, version_id)
        if not version:
            from app.core.errors import VersionNotFoundError
            raise VersionNotFoundError(dataset_id, version_id)
        if request.export_type == ExportType.DATASET and request.format not in {ExportFormat.ZIP, ExportFormat.CSV}:
            raise ValueError("Dataset contents support CSV metadata/records or a ZIP archive.")
        job_id = f"exp-{uuid.uuid4().hex[:16]}"
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        job = {
            "export_id": job_id, "dataset_id": dataset_id, "version_id": version_id,
            "export_type": request.export_type.value, "format": request.format.value,
            "status": "queued", "progress_pct": 0, "created_at": now,
            "completed_at": None, "filename": None, "download_url": None,
            "error_message": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        self._persist(job)
        self._pool.submit(self._run, job_id, request)
        return ExportJobResponse(**job)

    def get(self, export_id: str) -> ExportJobResponse | None:
        with self._lock:
            job = self._jobs.get(export_id)
        if job is None:
            path = storage_backend.results_dir / "exports" / "jobs" / f"{export_id}.json"
            if path.is_file() and path.parent.resolve().is_relative_to(storage_backend.results_dir.resolve()):
                try:
                    job = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
            else:
                return None
        return ExportJobResponse(**job)

    def list_for_version(self, dataset_id: str, version_id: str) -> list[ExportJobResponse]:
        jobs: dict[str, dict[str, Any]] = {}
        with self._lock:
            jobs.update({key: dict(value) for key, value in self._jobs.items()})
        jobs_dir = storage_backend.results_dir / "exports" / "jobs"
        if jobs_dir.is_dir():
            for path in jobs_dir.glob("exp-*.json"):
                try:
                    row = json.loads(path.read_text(encoding="utf-8"))
                    if row.get("dataset_id") == dataset_id and row.get("version_id") == version_id:
                        jobs[row["export_id"]] = row
                except (OSError, json.JSONDecodeError, KeyError):
                    continue
        rows = [ExportJobResponse(**row) for row in jobs.values()
                if row.get("dataset_id") == dataset_id and row.get("version_id") == version_id]
        return sorted(rows, key=lambda row: row.created_at, reverse=True)

    def _persist(self, job: dict[str, Any]) -> None:
        safe_id = job["export_id"]
        path = storage_backend.results_dir / "exports" / "jobs" / f"{safe_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(job), encoding="utf-8")
        temp.replace(path)

    def _update(self, export_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[export_id]
            job.update(changes)
            snapshot = dict(job)
        self._persist(snapshot)
        return snapshot

    @staticmethod
    def _flatten(value: Any, prefix: str = "") -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                rows.extend(ExportJobService._flatten(child, f"{prefix}.{key}" if prefix else str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                rows.extend(ExportJobService._flatten(child, f"{prefix}[{index}]"))
        else:
            if value is not None:
                rows.append((prefix, str(value)))
        return rows

    @classmethod
    def _csv_bytes(cls, payload: dict[str, Any]) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["field", "value"])
        writer.writerows(cls._flatten(payload))
        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def _section_pdf(title: str, payload: dict[str, Any], dataset_name: str, version_id: str, created_at: str) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        story = [Paragraph(title.replace("&", "&amp;"), styles["Title"]),
                 Paragraph(f"{dataset_name} · version {version_id} · generated {created_at}", styles["Normal"]), Spacer(1, 18)]
        rows = [["Evidence field", "Value"]]
        for key, value in ExportJobService._flatten(payload):
            safe_key = key.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe_value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            rows.append([Paragraph(safe_key, styles["BodyText"]), Paragraph(safe_value, styles["BodyText"])])
        table = Table(rows, colWidths=[190, 330], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#047857")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
        doc.build(story)
        return buffer.getvalue()

    def _payload(self, report, request: ExportCreateRequest) -> dict[str, Any]:
        document = report.model_dump(mode="json")
        if request.export_type in SECTIONS:
            key = SECTIONS[request.export_type]
            document = {"report_id": report.report_id, "dataset_id": report.dataset_id,
                        "version_id": report.version_id, "created_at": report.created_at,
                        key: document[key]}
        elif request.export_type == ExportType.COMPREHENSIVE:
            document = {**document}
        if not request.include_methodology:
            document.pop("methodology_section", None)
        return document

    def _version_root(self, dataset_id: str, version_id: str) -> tuple[Path, Any, Any]:
        dataset = dataset_service.get_dataset(dataset_id)
        version = dataset_service.get_version(dataset_id, version_id)
        if not dataset or not version:
            raise ValueError("The selected dataset version is unavailable.")
        root = (storage_backend.base_dir / version.storage_relative_path).resolve()
        if not storage_backend.is_safe_path(root) or not root.is_dir():
            raise ValueError("The selected dataset version is not stored in the configured dataset area.")
        return root, dataset, version

    @staticmethod
    def _safe_filename_part(value: str) -> str:
        return (re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")[:64] or "dataset")

    @staticmethod
    def _export_directory(dataset_id: str, version_id: str, export_id: str) -> Path:
        dataset_key = hashlib.sha256(dataset_id.encode("utf-8")).hexdigest()[:24]
        version_key = hashlib.sha256(version_id.encode("utf-8")).hexdigest()[:24]
        return storage_backend.results_dir / "exports" / dataset_key / version_key / export_id

    def _write_dataset_zip(self, target: Path, dataset_id: str, version_id: str, export_id: str) -> None:
        root, dataset, version = self._version_root(dataset_id, version_id)
        files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
                 and not any(part.startswith(".") for part in path.relative_to(root).parts)]
        manifest = {
            "dataset_id": dataset_id, "dataset_name": dataset.name, "version_id": version_id,
            "version_number": version.version_number, "content_fingerprint": version.content_fingerprint,
            "created_at": version.created_at,
            "files": [{"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size} for path in files],
        }
        total = sum(path.stat().st_size for path in files) or 1
        written = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("croplens-export-manifest.json", json.dumps(manifest, indent=2))
            for path in files:
                relative = path.relative_to(root).as_posix()
                archive.write(path, arcname=relative)
                written += path.stat().st_size
                self._update(export_id, progress_pct=min(95, 5 + written * 90 / total))
            image_csv = self._image_metadata_csv(dataset_id, version_id)
            if image_csv is not None:
                archive.writestr("image-metadata.csv", image_csv)

    @staticmethod
    def _image_metadata_csv(dataset_id: str, version_id: str) -> bytes | None:
        from app.services.image_explorer_service import image_explorer_service
        first_page = image_explorer_service.list_images(dataset_id, version_id, page=1, page_size=100)
        if first_page.modality != "image":
            return None
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["image_id", "filename", "class_name", "width", "height", "file_size_bytes", "format", "color_mode", "status"])
        page = 1
        while True:
            images = image_explorer_service.list_images(dataset_id, version_id, page=page, page_size=100)
            for image in images.items:
                writer.writerow([image.image_id, image.filename, image.class_name, image.width, image.height,
                                 image.file_size_bytes, image.format, image.color_mode, image.status])
            if page * images.page_size >= images.total:
                break
            page += 1
        return output.getvalue().encode("utf-8-sig")

    def _write_dataset_csv(self, target: Path, dataset_id: str, version_id: str) -> str:
        root, _, _ = self._version_root(dataset_id, version_id)
        image_csv = self._image_metadata_csv(dataset_id, version_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        if image_csv is not None:
            target.write_bytes(image_csv)
            return "image-metadata"
        tabular_files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
                         and path.suffix.lower() in {".csv", ".tsv"}
                         and not any(part.startswith(".") for part in path.relative_to(root).parts)]
        if len(tabular_files) != 1:
            raise ValueError("A single CSV/TSV table is required for a direct dataset CSV export. Use ZIP for multiple files or unsupported table formats.")
        source = tabular_files[0]
        if source.suffix.lower() == ".csv":
            shutil.copyfile(source, target)
        else:
            with source.open("r", encoding="utf-8-sig", newline="") as incoming, target.open("w", encoding="utf-8-sig", newline="") as outgoing:
                writer = csv.writer(outgoing)
                writer.writerows(csv.reader(incoming, delimiter="\t"))
        return source.stem

    def _run(self, export_id: str, request: ExportCreateRequest) -> None:
        job = self._update(export_id, status="running", progress_pct=3)
        try:
            if request.export_type == ExportType.DATASET:
                dataset_label = self._safe_filename_part(job["dataset_id"])
                version_label = self._safe_filename_part(job["version_id"])
                if request.format == ExportFormat.CSV:
                    target = self._export_directory(job["dataset_id"], job["version_id"], export_id) / f"dataset-{dataset_label}-{version_label}.csv"
                    self._write_dataset_csv(target, job["dataset_id"], job["version_id"])
                    filename = target.name
                else:
                    filename = f"dataset-{dataset_label}-{version_label}.zip"
                    target = self._export_directory(job["dataset_id"], job["version_id"], export_id) / filename
                    self._write_dataset_zip(target, job["dataset_id"], job["version_id"], export_id)
            else:
                self._update(export_id, progress_pct=10)
                task_context = None
                if request.export_type == ExportType.READINESS:
                    from app.services.readiness_service import readiness_service
                    prior_readiness = readiness_service.get_readiness_assessment(job["dataset_id"], job["version_id"])
                    task_context = prior_readiness.task_context if prior_readiness else None
                report = report_service.generate_report(ReportGenerateRequest(dataset_id=job["dataset_id"], version_id=job["version_id"], title=request.title, task_context=task_context, force_refresh=True))
                payload = self._payload(report, request)
                self._update(export_id, progress_pct=65)
                dataset_label = self._safe_filename_part(job["dataset_id"])
                version_label = self._safe_filename_part(job["version_id"])
                stem = f"croplens-{request.export_type.value}-{dataset_label}-{version_label}"
                target = self._export_directory(job["dataset_id"], job["version_id"], export_id)
                target.mkdir(parents=True, exist_ok=True)
                fmt = request.format
                if fmt == ExportFormat.JSON:
                    filename = f"{stem}.json"
                    (target / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
                elif fmt == ExportFormat.CSV:
                    filename = f"{stem}.csv"
                    (target / filename).write_bytes(self._csv_bytes(payload))
                elif fmt == ExportFormat.PDF:
                    filename = f"{stem}.pdf"
                    if request.export_type == ExportType.COMPREHENSIVE and request.include_methodology and not request.include_visualizations:
                        from app.services.pdf_export_service import pdf_export_service
                        data = pdf_export_service.generate_pdf_report(report)
                    else:
                        section = SECTIONS.get(request.export_type)
                        section_payload = payload.get(section, payload)
                        data = self._section_pdf(request.export_type.value.replace("_", " ").title(), section_payload,
                                                 report.dataset_overview.dataset_name, report.version_id, report.created_at)
                    (target / filename).write_bytes(data)
                else:
                    filename = f"{stem}-bundle.zip"
                    with zipfile.ZipFile(target / filename, "w", zipfile.ZIP_DEFLATED) as archive:
                        archive.writestr(f"{stem}.json", json.dumps(payload, indent=2, ensure_ascii=False, default=str))
                        archive.writestr(f"{stem}.csv", self._csv_bytes(payload))
                        if request.export_type == ExportType.COMPREHENSIVE:
                            if request.include_methodology and not request.include_visualizations:
                                from app.services.pdf_export_service import pdf_export_service
                                pdf_data = pdf_export_service.generate_pdf_report(report)
                            else:
                                pdf_data = self._section_pdf("Comprehensive analysis report", payload,
                                    report.dataset_overview.dataset_name, report.version_id, report.created_at)
                            archive.writestr(f"{stem}.pdf", pdf_data)
                        if request.include_visualizations:
                            from app.services.visualizations import visualization_service
                            try:
                                visuals = visualization_service.get_visualizations(job["dataset_id"], job["version_id"])
                                archive.writestr("visualizations.json", json.dumps(visuals.model_dump(mode="json"), indent=2, default=str))
                            except Exception:
                                pass
                        archive.writestr("provenance.json", json.dumps({"dataset_id": job["dataset_id"], "version_id": job["version_id"], "report_id": report.report_id, "content_fingerprint": report.provenance.content_fingerprint}, indent=2))
            artifact_path = target if request.export_type == ExportType.DATASET else target / filename
            relative = artifact_path.relative_to(storage_backend.results_dir).as_posix()
            self._update(export_id, status="completed", progress_pct=100, completed_at=dt.datetime.now(dt.timezone.utc).isoformat(), filename=filename, download_url=f"/api/v1/exports/{export_id}/download", artifact_relative_path=relative)
        except Exception as exc:
            logger.exception("Export job failed: %s", export_id)
            self._update(export_id, status="failed", progress_pct=100, completed_at=dt.datetime.now(dt.timezone.utc).isoformat(), error_message="Export generation failed. Confirm the selected version has the requested data and retry.")

    def download_path(self, export_id: str) -> tuple[Path, str] | None:
        with self._lock:
            job = self._jobs.get(export_id)
        if job is None:
            status = self.get(export_id)
            if status is None:
                return None
            job = status.model_dump()
            metadata_path = storage_backend.results_dir / "exports" / "jobs" / f"{export_id}.json"
            try:
                job = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        if job.get("status") != "completed" or not job.get("artifact_relative_path"):
            return None
        relative = Path(job["artifact_relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            return None
        path = (storage_backend.results_dir / relative).resolve()
        if not path.is_relative_to(storage_backend.results_dir.resolve()) or not path.is_file():
            return None
        return path, str(job.get("filename") or path.name)


from app.schemas.reports import ReportGenerateRequest

export_job_service = ExportJobService()
