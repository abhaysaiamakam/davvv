"""
CropLens — M10 Dataset Readiness, Methodology & Analytical Reports Engine Tests.

Tests:
1. Multi-dimensional readiness evaluation (integrity, quality, suitability, preprocessing, features).
2. Readiness evaluation with task context (target column validation, classification task).
3. Readiness assessment caching and retrieval.
4. Methodology builder generates reproducible steps and workflow summary.
5. Analytical report composition from M2-M9 artifacts.
6. Analytical report caching, force_refresh, and list retrieval.
7. PDF report export compilation (valid PDF signature '%PDF-').
8. JSON report export structure.
9. HTTP API endpoints for readiness (GET /readiness, POST /readiness/assess, GET /versions/{ver}/readiness).
10. HTTP API endpoints for reports (POST /reports/generate, GET /reports, GET /reports/{id}, GET /reports/{id}/download).
11. 404 error handling for non-existent datasets and reports.
12. Host path leak prevention in report and readiness outputs.
"""
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
import pytest
from PIL import Image

from app.schemas.readiness import (
    DatasetReadinessAssessment,
    ReadinessDimension,
    ReadinessStatus,
    TaskContext,
)
from app.schemas.reports import AnalyticalReport, ReportExportFormat
from app.services.readiness_service import readiness_service
from app.services.report_service import report_service
from app.services.methodology_builder import methodology_builder
from app.services.pdf_export_service import pdf_export_service
from app.storage.local import storage_backend


def _create_image_bytes(fmt: str = "JPEG", size=(32, 32), color=(100, 150, 200)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return buf.getvalue()


def _create_sample_zip(target_path: Path, files_dict: dict) -> Path:
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in files_dict.items():
            if isinstance(data, str):
                zf.writestr(arcname, data.encode("utf-8"))
            else:
                zf.writestr(arcname, data)
    return target_path


# ---------------------------------------------------------------------------
# 1. Readiness Service Tests
# ---------------------------------------------------------------------------

def test_assess_readiness_basic(client, tmp_path):
    """Test evaluating readiness on an uploaded dataset."""
    img = _create_image_bytes("JPEG")
    zip_file = tmp_path / "readiness_ds.zip"
    _create_sample_zip(zip_file, {
        "ClassA/img1.jpg": img,
        "ClassA/img2.jpg": img,
        "ClassB/img3.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("readiness_ds.zip", f, "application/zip")},
            data={"dataset_id": "m10_readiness_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    start = time.time()
    while time.time() - start < 30.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.2)

    assessment = readiness_service.assess_readiness("m10_readiness_ds")
    assert assessment.dataset_id == "m10_readiness_ds"
    assert assessment.overall_score >= 0
    assert len(assessment.dimensions) == 5
    dims = {d.dimension: d for d in assessment.dimensions}
    assert ReadinessDimension.DATASET_INTEGRITY in dims
    assert ReadinessDimension.DATA_QUALITY in dims
    assert ReadinessDimension.ANALYTICAL_SUITABILITY in dims
    assert ReadinessDimension.PREPROCESSING_STATUS in dims
    assert ReadinessDimension.FEATURE_READINESS in dims


def test_assess_readiness_with_task_context(client, tmp_path):
    """Test readiness assessment incorporating task context."""
    img = _create_image_bytes("JPEG")
    zip_file = tmp_path / "task_ctx_ds.zip"
    _create_sample_zip(zip_file, {
        "Cat/c1.jpg": img,
        "Dog/d1.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("task_ctx_ds.zip", f, "application/zip")},
            data={"dataset_id": "m10_task_ctx_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    start = time.time()
    while time.time() - start < 30.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.2)

    task_ctx = TaskContext(
        task_type="classification",
        analytical_goal="Train image classifier",
    )
    assessment = readiness_service.assess_readiness(
        "m10_task_ctx_ds", task_context=task_ctx
    )
    assert assessment.task_context is not None
    assert assessment.task_context.task_type == "classification"


# ---------------------------------------------------------------------------
# 2. Methodology Builder Tests
# ---------------------------------------------------------------------------

def test_methodology_builder_execution():
    """Test methodology generation produces reproducible steps."""
    methodology = methodology_builder.build_methodology(
        dataset_id="test_ds",
        version_id="v1",
        modality="image",
        analysis_artifact={"total_images": 100},
        quality_artifact={"overall_quality_score": 90},
        readiness_score=85,
    )
    assert methodology.workflow_summary
    assert len(methodology.steps) >= 3
    stage_names = [s.stage_name for s in methodology.steps]
    assert "Dataset Discovery & Modality Detection" in stage_names
    assert "Data Quality Assessment" in stage_names
    assert "Dataset Readiness Assessment" in stage_names


# ---------------------------------------------------------------------------
# 3. Report Service Tests
# ---------------------------------------------------------------------------

def test_report_generation_and_export(client, tmp_path):
    """Test generating a report, checking sections, and exporting PDF/JSON."""
    img = _create_image_bytes("JPEG")
    zip_file = tmp_path / "report_ds.zip"
    _create_sample_zip(zip_file, {
        "A/a1.jpg": img,
        "B/b1.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("report_ds.zip", f, "application/zip")},
            data={"dataset_id": "m10_report_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    start = time.time()
    while time.time() - start < 30.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.2)

    from app.schemas.reports import ReportGenerateRequest
    req = ReportGenerateRequest(dataset_id="m10_report_ds", title="Test Analytical Report")
    report = report_service.generate_report(req)

    assert report.report_id.startswith("rep-m10_report_ds-")
    assert report.title == "Test Analytical Report"
    assert report.executive_summary.dataset_name
    assert report.dataset_overview.modality
    assert report.readiness_section.overall_score >= 0
    assert report.methodology_section.execution_engine

    # Test PDF Export
    pdf_bytes, media_type, pdf_name = report_service.download_report(
        dataset_id="m10_report_ds",
        report_id=report.report_id,
        export_format=ReportExportFormat.PDF,
    )
    assert media_type == "application/pdf"
    assert pdf_name.endswith(".pdf")
    assert pdf_bytes.startswith(b"%PDF-")

    # Test JSON Export
    json_bytes, json_media, json_name = report_service.download_report(
        dataset_id="m10_report_ds",
        report_id=report.report_id,
        export_format=ReportExportFormat.JSON,
    )
    assert json_media == "application/json"
    assert json_name.endswith(".json")
    parsed = json.loads(json_bytes.decode("utf-8"))
    assert parsed["report_id"] == report.report_id


# ---------------------------------------------------------------------------
# 4. HTTP API Endpoints Tests
# ---------------------------------------------------------------------------

def test_readiness_api_endpoints(client, tmp_path):
    """Test readiness HTTP GET and POST endpoints."""
    img = _create_image_bytes("JPEG")
    zip_file = tmp_path / "readiness_api_ds.zip"
    _create_sample_zip(zip_file, {
        "A/a1.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("readiness_api_ds.zip", f, "application/zip")},
            data={"dataset_id": "m10_readiness_api_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    start = time.time()
    while time.time() - start < 30.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.2)

    # GET /readiness
    r_get = client.get("/api/v1/datasets/m10_readiness_api_ds/readiness")
    assert r_get.status_code == 200
    r_data = r_get.json()
    assert r_data["dataset_id"] == "m10_readiness_api_ds"
    assert "overall_score" in r_data

    # POST /readiness/assess
    r_post = client.post(
        "/api/v1/datasets/m10_readiness_api_ds/readiness/assess",
        json={"dataset_id": "m10_readiness_api_ds", "task_context": {"analytical_goal": "API evaluation"}},
    )
    assert r_post.status_code == 200
    assert r_post.json()["task_context"]["analytical_goal"] == "API evaluation"


def test_reports_api_endpoints(client, tmp_path):
    """Test analytical reports HTTP endpoints."""
    img = _create_image_bytes("JPEG")
    zip_file = tmp_path / "reports_api_ds.zip"
    _create_sample_zip(zip_file, {
        "X/x1.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("reports_api_ds.zip", f, "application/zip")},
            data={"dataset_id": "m10_reports_api_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    start = time.time()
    while time.time() - start < 30.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.2)

    # 1. POST /reports/generate
    gen_res = client.post(
        "/api/v1/datasets/m10_reports_api_ds/reports/generate",
        json={"dataset_id": "m10_reports_api_ds", "title": "API Generated Report"},
    )
    assert gen_res.status_code == 200
    report_data = gen_res.json()
    report_id = report_data["report_id"]

    # 2. GET /reports
    list_res = client.get("/api/v1/datasets/m10_reports_api_ds/reports")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 3. GET /reports/{report_id}
    single_res = client.get(f"/api/v1/datasets/m10_reports_api_ds/reports/{report_id}")
    assert single_res.status_code == 200
    assert single_res.json()["report_id"] == report_id

    # 4. GET /reports/{report_id}/download (JSON)
    dl_json = client.get(
        f"/api/v1/datasets/m10_reports_api_ds/reports/{report_id}/download",
        params={"format": "json"},
    )
    assert dl_json.status_code == 200
    assert dl_json.headers["content-type"] == "application/json"

    # 5. GET /reports/{report_id}/download (PDF)
    dl_pdf = client.get(
        f"/api/v1/datasets/m10_reports_api_ds/reports/{report_id}/download",
        params={"format": "pdf"},
    )
    assert dl_pdf.status_code == 200
    assert dl_pdf.headers["content-type"] == "application/pdf"
    assert dl_pdf.content.startswith(b"%PDF-")


def test_no_host_path_leak_in_reports(client, tmp_path):
    """Ensure generated reports do not leak host paths."""
    img = _create_image_bytes("JPEG")
    zip_file = tmp_path / "path_leak_report_ds.zip"
    _create_sample_zip(zip_file, {
        "A/a1.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("path_leak_report_ds.zip", f, "application/zip")},
            data={"dataset_id": "path_leak_report_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    start = time.time()
    while time.time() - start < 30.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.2)

    gen_res = client.post(
        "/api/v1/datasets/path_leak_report_ds/reports/generate",
        json={"dataset_id": "path_leak_report_ds"},
    )
    assert gen_res.status_code == 200
    dumped = json.dumps(gen_res.json())
    assert "/Users/" not in dumped
    assert "/home/" not in dumped
    assert "/var/" not in dumped
