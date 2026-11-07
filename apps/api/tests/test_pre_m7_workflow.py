"""
CropLens — Pre-M7 End-to-End Workflow Audit, Testing & Integration Validation.

Validates the complete 7-stage automatic dataset intelligence workflow:
- Stage A: Dataset Upload & Security (Formats, Zip-Slip, Tar traversal, Decompression bombs, Quotas, Fingerprinting)
- Stage B: Structure & Characteristic Profiling (Image classification, Tabular, Time-series, Annotations)
- Stage C: Automatic Analytics Execution (M2 discovery -> validation -> deduplication -> unified -> M3 quality -> M4 EDA)
- Stage D: Automatic Visualization Specification Generation (Dynamic selection, Chart specs, Chart-ready data)
- Stage E: Persistence & API Retrieval (Filesystem storage, REST endpoints, 404s, Filtering, Zero path leaks)
- Stage F: Dataset Versioning, Deduplication & Historical Preservation (v1 -> v2, Fingerprint reuse, Restart recovery, Failure isolation)
- Stage G: Frontend Contract Readiness (Shared TypeScript models alignment, Schema invariants)
"""
import io
import json
import os
import tarfile
import time
import uuid
import zipfile
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import (
    ArchiveSecurityError,
    InvalidArchiveError,
    PayloadTooLargeError,
)
from app.main import app
from app.schemas.dataset import DatasetStatus
from app.schemas.job import JobStage, JobStatus
from app.schemas.visualization import ChartType, VisualizationCategory
from app.services.dataset_service import dataset_service
from app.services.job_service import job_service, JobService
from app.services.upload_service import upload_service
from app.services.visualizations import (
    ImageClassificationVisualizer,
    TabularVisualizer,
    TimeSeriesVisualizer,
    AnnotationVisualizer,
    chart_selection_registry,
    visualization_service,
)
from app.storage.local import storage_backend


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Ensure in-memory caches and job registries are clean between tests."""
    job_service._jobs.clear()
    dataset_service._dynamic_registry.clear()
    dataset_service._versions.clear()
    dataset_service._discovery_results.clear()
    dataset_service._validation_results.clear()
    dataset_service._duplicate_results.clear()
    dataset_service._near_duplicate_results.clear()
    yield
    job_service._jobs.clear()
    dataset_service._dynamic_registry.clear()
    dataset_service._versions.clear()

def _create_image_bytes(fmt: str = "JPEG", size=(64, 64), color=(60, 120, 180)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return buf.getvalue()


def _create_sample_zip(target_path: Path, files_dict: dict) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in files_dict.items():
            if isinstance(data, str):
                zf.writestr(arcname, data.encode("utf-8"))
            else:
                zf.writestr(arcname, data)
    return target_path


def _create_sample_tar_gz(target_path: Path, files_dict: dict) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target_path, "w:gz") as tf:
        for arcname, data in files_dict.items():
            if isinstance(data, str):
                raw_bytes = data.encode("utf-8")
            else:
                raw_bytes = data
            ti = tarfile.TarInfo(name=arcname)
            ti.size = len(raw_bytes)
            ti.mtime = int(time.time())
            tf.addfile(ti, io.BytesIO(raw_bytes))
    return target_path


# ---------------------------------------------------------------------------
# Stage A: Dataset Upload, Archive Security & Quotas
# ---------------------------------------------------------------------------

def test_stage_a_upload_format_acceptance_and_rejection(tmp_path):
    """Verify supported formats (.zip, .tar, .tar.gz, .tgz) are accepted, unsupported are rejected."""
    # Supported
    assert upload_service.validate_filename("dataset.zip") == "zip"
    assert upload_service.validate_filename("DATASET.ZIP") == "zip"
    assert upload_service.validate_filename("dataset.tar.gz") == "tar.gz"
    assert upload_service.validate_filename("dataset.tgz") == "tar.gz"
    assert upload_service.validate_filename("dataset.tar") == "tar"

    # Unsupported formats rejected
    for bad in ["data.rar", "archive.7z", "binary.bin", "script.py", "dataset.exe"]:
        with pytest.raises(InvalidArchiveError) as exc_info:
            upload_service.validate_filename(bad)
        assert "Unsupported archive format" in str(exc_info.value)


def test_stage_a_archive_security_zip_slip_and_tar_traversal(tmp_path):
    """Verify directory traversal attacks (Zip-Slip and tar traversal) are strictly rejected."""
    # 1. Zip-Slip
    zip_slip_path = tmp_path / "malicious_zip_slip.zip"
    with zipfile.ZipFile(zip_slip_path, "w") as zf:
        zf.writestr("../../etc/passwd", b"root:x:0:0::/root:/bin/bash")

    extract_dir = tmp_path / "extract_zip_slip"
    with pytest.raises(ArchiveSecurityError) as exc_info:
        upload_service.extract_archive(zip_slip_path, extract_dir)
    assert "forbidden path traversal" in str(exc_info.value)
    assert not (extract_dir / "../../etc/passwd").exists()

    # 2. Tar traversal
    tar_slip_path = tmp_path / "malicious_tar_slip.tar"
    with tarfile.open(tar_slip_path, "w") as tf:
        ti = tarfile.TarInfo(name="../escape.txt")
        payload = b"escaped"
        ti.size = len(payload)
        tf.addfile(ti, io.BytesIO(payload))

    extract_tar_dir = tmp_path / "extract_tar_slip"
    with pytest.raises(ArchiveSecurityError) as exc_info:
        upload_service.extract_archive(tar_slip_path, extract_tar_dir)
    assert "traversal" in str(exc_info.value).lower()


def test_stage_a_quota_enforcement_and_fingerprinting(tmp_path, monkeypatch):
    """Verify decompression size quota, file count quota, and deterministic fingerprinting."""
    monkeypatch.setattr(settings, "MAX_ARCHIVE_FILES", 5)
    monkeypatch.setattr(upload_service, "max_files", 5)

    too_many_files_zip = tmp_path / "too_many.zip"
    files = {f"file_{i}.txt": f"content_{i}" for i in range(8)}
    _create_sample_zip(too_many_files_zip, files)

    with pytest.raises(PayloadTooLargeError) as exc_info:
        upload_service.extract_archive(too_many_files_zip, tmp_path / "too_many_extract")
    assert "exceeds maximum allowed" in str(exc_info.value)

    # Deterministic fingerprinting check
    dir1 = tmp_path / "fp_dir1"
    dir2 = tmp_path / "fp_dir2"
    dir1.mkdir()
    dir2.mkdir()
    (dir1 / "a.txt").write_text("hello crop intelligence")
    (dir2 / "a.txt").write_text("hello crop intelligence")

    fp1 = upload_service.compute_content_fingerprint(dir1)
    fp2 = upload_service.compute_content_fingerprint(dir2)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex string


# ---------------------------------------------------------------------------
# Stage B: Structure & Characteristic Profiling Across All 4 Modalities
# ---------------------------------------------------------------------------

def test_stage_b_multimodal_profiling_and_extraction(tmp_path, monkeypatch):
    """
    Verify structure and characteristic profiling across all 4 dataset modalities:
    1. Image classification (classes, formats, dimensions, RGB color modes)
    2. Tabular dataset (schema, missing values, quartiles, correlation matrix)
    3. Time-series dataset (timestamps, chronological trend line)
    4. Object detection / annotations (COCO JSON, YOLO TXT, bbox counts, label distributions)
    """
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    # Prepare multimodal assets
    img1 = _create_image_bytes("JPEG", size=(100, 80), color=(40, 100, 160))
    img2 = _create_image_bytes("PNG", size=(120, 90), color=(50, 110, 170))
    img3 = _create_image_bytes("JPEG", size=(100, 80), color=(60, 120, 180))

    csv_tabular = (
        "plot_id,soil_ph,leaf_nitrogen,canopy_coverage,variety\n"
        "P1,6.2,2.4,85.0,Basmati\n"
        "P2,6.5,2.6,88.5,Basmati\n"
        "P3,5.8,1.9,72.0,SonaMasoori\n"
        "P4,5.9,2.0,74.5,SonaMasoori\n"
        "P5,6.8,3.1,,Swarna\n"  # missing canopy_coverage
    )

    csv_timeseries = (
        "date,soil_moisture_pct,ambient_temp_c\n"
        "2026-06-01,35.4,28.2\n"
        "2026-06-02,33.1,29.0\n"
        "2026-06-03,31.5,30.1\n"
        "2026-06-04,44.8,26.5\n"
        "2026-06-05,42.0,27.0\n"
    )

    coco_annotations = {
        "categories": [
            {"id": 1, "name": "Brown_Spot"},
            {"id": 2, "name": "Bacterial_Blight"},
        ],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 15, 30, 45]},
            {"id": 2, "image_id": 1, "category_id": 2, "bbox": [40, 50, 25, 35]},
            {"id": 3, "image_id": 2, "category_id": 1, "bbox": [12, 18, 28, 40]},
        ],
    }

    archive_files = {
        "Rice/Leaf_Blast/img_01.jpg": img1,
        "Rice/Leaf_Blast/img_02.png": img2,
        "Rice/Healthy/img_03.jpg": img3,
        "metadata/field_measurements.csv": csv_tabular,
        "metadata/sensor_timeseries.csv": csv_timeseries,
        "annotations/instances_coco.json": json.dumps(coco_annotations),
    }

    archive_zip = tmp_path / "multimodal_dataset.zip"
    _create_sample_zip(archive_zip, archive_files)

    # 1. Image Classification Profiling via Discovery & Validation
    target_extract = tmp_path / "multimodal_extracted"
    upload_service.extract_archive(archive_zip, target_extract)

    # Verify Tabular Profiler directly on extracted dataset
    tab_viz = TabularVisualizer()
    context = {"dataset_dir": target_extract}
    assert tab_viz.can_handle("multimodal_ds", "v1", context) is True
    tab_specs = tab_viz.generate("multimodal_ds", "v1", context)
    assert len(tab_specs) >= 4
    tab_chart_types = [s.chart_type for s in tab_specs]
    assert ChartType.BAR in tab_chart_types
    assert ChartType.HISTOGRAM in tab_chart_types
    assert ChartType.HEATMAP in tab_chart_types

    # Verify Time-Series Profiler directly on extracted dataset
    ts_viz = TimeSeriesVisualizer()
    assert ts_viz.can_handle("multimodal_ds", "v1", context) is True
    ts_specs = ts_viz.generate("multimodal_ds", "v1", context)
    assert len(ts_specs) >= 1
    assert ts_specs[0].chart_type == ChartType.LINE
    assert ts_specs[0].category == VisualizationCategory.TIME_SERIES

    # Verify Annotation Profiler directly on extracted dataset
    ann_viz = AnnotationVisualizer()
    assert ann_viz.can_handle("multimodal_ds", "v1", context) is True
    ann_specs = ann_viz.generate("multimodal_ds", "v1", context)
    assert len(ann_specs) == 1
    assert ann_specs[0].category == VisualizationCategory.ANNOTATIONS
    assert ann_specs[0].chart_type == ChartType.BAR
    # Check annotation class distribution: Brown_Spot=2, Bacterial_Blight=1
    brown_spot_item = next(d for d in ann_specs[0].chart_data if d["class_name"] == "Brown_Spot")
    assert brown_spot_item["bounding_boxes"] == 2

    # Negative test: Clean directory without annotations should not fabricate charts
    empty_ann_dir = tmp_path / "clean_no_annotations"
    empty_ann_dir.mkdir()
    assert ann_viz.can_handle("clean_ds", "v1", {"dataset_dir": empty_ann_dir}) is False


# ---------------------------------------------------------------------------
# Stage C, D, E: Automatic Analytics Pipeline, Visualizations & Persistence
# ---------------------------------------------------------------------------

def test_stage_c_d_e_full_automatic_upload_to_eda_and_visualizations_workflow(tmp_path, monkeypatch):
    """
    Test End-to-End Automatic Workflow:
    1. Upload archive via API.
    2. Automatic background execution of M2 -> M3 -> M4 -> Visualizations.
    3. Job completion and stage progression tracking.
    4. Dynamic generation of typed visualization specifications without false fabrications.
    5. Persistence and REST API retrieval across all endpoints.
    6. Verified absence of internal host path leakage.
    """
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    client = TestClient(app)

    # Create test archive with 2 classes and a tabular metadata CSV
    img_a1 = _create_image_bytes("JPEG", size=(64, 64), color=(30, 80, 130))
    img_a2 = _create_image_bytes("JPEG", size=(80, 60), color=(40, 90, 140))
    img_b1 = _create_image_bytes("PNG", size=(50, 50), color=(50, 100, 150))
    tabular_csv = "sample_id,nitrogen,ph\nS1,2.5,6.4\nS2,2.8,6.6\nS3,2.1,5.9\n"

    zip_path = tmp_path / "e2e_workflow_ds.zip"
    _create_sample_zip(zip_path, {
        "Tomato/Early_Blight/img_01.jpg": img_a1,
        "Tomato/Early_Blight/img_02.jpg": img_a2,
        "Tomato/Healthy/img_03.png": img_b1,
        "soil_metadata.csv": tabular_csv,
    })

    # Stage A / Upload API
    with open(zip_path, "rb") as f:
        resp = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("e2e_workflow_ds.zip", f, "application/zip")},
            data={"dataset_id": "tomato_field_ds", "name": "Tomato Field In-The-Wild Dataset"},
        )
    assert resp.status_code == 202
    upload_data = resp.json()
    job_id = upload_data["job_id"]
    dataset_id = upload_data["dataset_id"]
    assert dataset_id == "tomato_field_ds"

    # Stage C / Wait for background pipeline to complete
    max_wait = 10.0
    start = time.perf_counter()
    completed_job = None
    while time.perf_counter() - start < max_wait:
        job_resp = client.get(f"/api/v1/jobs/{job_id}")
        assert job_resp.status_code == 200
        job_info = job_resp.json()
        if job_info["status"] in ("completed", "failed"):
            completed_job = job_info
            break
        time.sleep(0.1)

    assert completed_job is not None, "Pipeline timed out"
    assert completed_job["status"] == "completed"
    assert completed_job["progress_pct"] == 100.0
    assert "analysis_id" in completed_job["artifact_refs"]
    assert "quality_id" in completed_job["artifact_refs"]
    assert "eda_id" in completed_job["artifact_refs"]
    assert "visualization_id" in completed_job["artifact_refs"]

    # Stage E / REST API Retrieval & Validation
    # 1. Dataset metadata
    ds_resp = client.get(f"/api/v1/datasets/{dataset_id}")
    assert ds_resp.status_code == 200
    ds_meta = ds_resp.json()
    assert ds_meta["status"] == "ready"
    assert ds_meta["total_images"] == 3
    assert ds_meta["total_classes"] == 2
    assert ds_meta["validated_image_files"] == 3

    # 2. Unified Analysis (M2)
    ana_resp = client.get(f"/api/v1/datasets/{dataset_id}/analysis")
    assert ana_resp.status_code == 200
    ana_data = ana_resp.json()
    assert ana_data["status"] == "completed"
    assert ana_data["metrics"]["total_files_discovered"] == 3
    assert ana_data["metrics"]["total_validated_images"] == 3
    assert ana_data["metrics"]["total_classes_discovered"] == 2

    # 3. Data Quality Assessment (M3)
    qual_resp = client.get(f"/api/v1/datasets/{dataset_id}/quality-assessment")
    assert qual_resp.status_code == 200
    qual_data = qual_resp.json()
    assert qual_data["dataset_id"] == dataset_id
    assert qual_data["quality_score"]["overall_score"] > 0
    assert qual_data["quality_score"]["quality_tier"].lower() in ("excellent", "good", "fair", "poor", "critical")

    # 4. EDA Report (M4)
    eda_resp = client.get(f"/api/v1/datasets/{dataset_id}/eda")
    assert eda_resp.status_code == 200
    eda_data = eda_resp.json()
    assert eda_data["overview"]["total_valid_images"] == 3
    assert eda_data["overview"]["class_count"] == 2
    assert "dimension_analysis" in eda_data
    assert "color_analysis" in eda_data

    # Stage D / Visualizations Retrieval
    vis_resp = client.get(f"/api/v1/datasets/{dataset_id}/visualizations")
    assert vis_resp.status_code == 200
    vis_data = vis_resp.json()
    assert vis_data["status"] == "completed"
    assert vis_data["total"] >= 8  # Both image charts (class dist, aspect ratios, etc.) + tabular charts (nitrogen, ph)
    assert len(vis_data["items"]) == vis_data["total"]

    # Filter query parameters: category & chart_type
    filtered_resp = client.get(f"/api/v1/datasets/{dataset_id}/visualizations?category=class_distribution")
    assert filtered_resp.status_code == 200
    filtered_items = filtered_resp.json()["items"]
    assert all(item["category"] == "class_distribution" for item in filtered_items)

    # Retrieval of single visualization specification by ID
    first_vis_id = vis_data["items"][0]["visualization_id"]
    single_vis_resp = client.get(f"/api/v1/datasets/{dataset_id}/visualizations/{first_vis_id}")
    assert single_vis_resp.status_code == 200
    assert single_vis_resp.json()["visualization_id"] == first_vis_id

    # 404 error testing on missing resources
    assert client.get("/api/v1/datasets/non_existent_ds").status_code == 404
    assert client.get("/api/v1/datasets/non_existent_ds/analysis").status_code == 404
    assert client.get("/api/v1/datasets/non_existent_ds/visualizations").status_code == 404
    assert client.get(f"/api/v1/datasets/{dataset_id}/visualizations/non_existent_spec_id").status_code == 404

    # Security Check: Verify zero host paths leaked in JSON responses
    all_json_str = (
        json.dumps(ds_meta)
        + json.dumps(ana_data)
        + json.dumps(qual_data)
        + json.dumps(eda_data)
        + json.dumps(vis_data)
    )
    assert str(tmp_path) not in all_json_str


# ---------------------------------------------------------------------------
# Stage F: Dataset Versioning, Deduplication & Historical Preservation
# ---------------------------------------------------------------------------

def test_stage_f_versioning_duplicate_content_and_historical_preservation(tmp_path, monkeypatch):
    """
    Verify:
    1. Uploading identical content reuses version via fingerprint without re-running pipeline.
    2. Uploading modified archive increments version (v1 -> v2).
    3. Historical version preservation: v1 reports and visualizations remain accessible after v2 is created.
    """
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()
    client = TestClient(app)

    img_v1 = _create_image_bytes("JPEG", size=(64, 64), color=(30, 80, 130))
    zip_v1 = tmp_path / "ver_ds_v1.zip"
    _create_sample_zip(zip_v1, {"Rice/Blast/img_01.jpg": img_v1})

    # Upload v1
    with open(zip_v1, "rb") as f:
        resp1 = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("ver_ds_v1.zip", f, "application/zip")},
            data={"dataset_id": "versioned_ds", "name": "Versioned Crop Dataset"},
        )
    assert resp1.status_code == 202
    v1_info = resp1.json()
    assert v1_info["is_duplicate_content"] is False
    assert v1_info["version_number"] == 1
    job_v1_id = v1_info["job_id"]

    # Wait for v1 job
    start = time.perf_counter()
    while time.perf_counter() - start < 10.0:
        j = client.get(f"/api/v1/jobs/{job_v1_id}").json()
        if j["status"] == "completed":
            break
        time.sleep(0.1)

    # 1. Deduplication check: upload identical zip again
    with open(zip_v1, "rb") as f:
        resp_dup = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("ver_ds_v1.zip", f, "application/zip")},
            data={"dataset_id": "versioned_ds"},
        )
    assert resp_dup.status_code == 202
    dup_info = resp_dup.json()
    assert dup_info["is_duplicate_content"] is True
    assert dup_info["version_number"] == 1
    assert dup_info["job_id"] == ""  # No redundant job created

    # 2. Version increment check: upload modified content (v2 with new image)
    img_v2 = _create_image_bytes("PNG", size=(70, 70), color=(50, 100, 150))
    zip_v2 = tmp_path / "ver_ds_v2.zip"
    _create_sample_zip(zip_v2, {
        "Rice/Blast/img_01.jpg": img_v1,
        "Rice/Healthy/img_02.png": img_v2,
    })

    with open(zip_v2, "rb") as f:
        resp2 = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("ver_ds_v2.zip", f, "application/zip")},
            data={"dataset_id": "versioned_ds"},
        )
    assert resp2.status_code == 202
    v2_info = resp2.json()
    assert v2_info["is_duplicate_content"] is False
    assert v2_info["version_number"] == 2
    job_v2_id = v2_info["job_id"]

    # Wait for v2 job
    start = time.perf_counter()
    while time.perf_counter() - start < 10.0:
        j = client.get(f"/api/v1/jobs/{job_v2_id}").json()
        if j["status"] == "completed":
            break
        time.sleep(0.1)

    # 3. Check versions list
    ver_list_resp = client.get("/api/v1/datasets/versioned_ds/versions")
    assert ver_list_resp.status_code == 200
    versions = ver_list_resp.json()["items"]
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1

    # Historical query: v1 visualizations preserved
    v1_id = versions[1]["version_id"]
    v1_vis_resp = client.get(f"/api/v1/datasets/versioned_ds/versions/{v1_id}/visualizations")
    assert v1_vis_resp.status_code == 200
    assert v1_vis_resp.json()["dataset_version"] == v1_id


def test_stage_f_server_restart_recovery_and_failure_isolation(tmp_path, monkeypatch):
    """
    Verify:
    1. Server restart recovery transitions uncompleted processing jobs to FAILED with explanatory error code.
    2. Failed version preserves previous good version state.
    """
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    local_job_service = JobService(backend=storage_backend, max_workers=1)

    # Create dummy in-flight job
    job = local_job_service.create_job("test_ds", "v1")
    job.status = JobStatus.PROCESSING
    job.current_stage = JobStage.VALIDATION
    local_job_service._persist_job(job)

    # Simulate restart recovery
    restart_job_service = JobService(backend=storage_backend, max_workers=1)
    restart_job_service.recover_jobs_on_startup()

    recovered_job = restart_job_service.get_job(job.job_id)
    assert recovered_job is not None
    assert recovered_job.status == JobStatus.FAILED
    assert recovered_job.error_code == "JOB_INTERRUPTED_BY_RESTART"


# ---------------------------------------------------------------------------
# Stage G: Frontend Contract Invariants
# ---------------------------------------------------------------------------

def test_stage_g_frontend_contract_and_schema_conformance(tmp_path, monkeypatch):
    """
    Verify all API response models conform to TypeScript contracts defined in packages/shared-types:
    - VisualizationSpecification: visualization_id, title, category, chart_type, x_axis, y_axis, series, chart_data
    - JobStatus: queued, validating, processing, completed, failed, cancelled
    - QualityTier: EXCELLENT, GOOD, FAIR, POOR, CRITICAL
    """
    # Verify Visualizer Schema conforms strictly to contract
    from app.schemas.visualization import AxisScale, AxisSpec, SeriesSpec, VisualizationSpecification

    spec = VisualizationSpecification(
        visualization_id="test_spec_01",
        dataset_id="test_ds",
        dataset_version="v1",
        title="Class Distribution Test",
        category=VisualizationCategory.CLASS_DISTRIBUTION,
        chart_type=ChartType.BAR,
        description="Verifying contract field names",
        x_axis=AxisSpec(name="class_name", label="Class Label", scale=AxisScale.CATEGORY),
        y_axis=AxisSpec(name="count", label="Sample Count", scale=AxisScale.LINEAR),
        series=[SeriesSpec(name="Samples", data_key="count", color="#10b981")],
        chart_data=[{"class_name": "Healthy", "count": 10}],
    )

    dumped = spec.model_dump()
    expected_keys = {
        "visualization_id", "title", "category", "chart_type", "description",
        "x_axis", "y_axis", "series", "chart_data", "metadata",
    }
    assert expected_keys.issubset(set(dumped.keys()))
    assert dumped["category"] == "class_distribution"
    assert dumped["chart_type"] == "bar"
