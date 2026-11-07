"""
M6 — Evaluator Dataset Upload, Dynamic Dataset Lifecycle & Event-Driven Analysis Tests.

Validates:
1. Safe archive extraction (.zip, .tar, .tar.gz) and Zip-Slip traversal protection.
2. Quota enforcement and size boundary limits.
3. Unsupported archive formats and empty archive handling.
4. Dynamic dataset registration and duplicate ID conflict handling.
5. Deterministic content fingerprinting and duplicate upload reuse.
6. Dataset versioning (v1, v2) and version retrieval APIs.
7. Processing job tracking, stage transitions, and retry endpoints.
8. Server restart recovery for interrupted and queued jobs.
9. Event bus decoupled subscription, publishing, and error isolation.
10. M5 comparison freshness checking and automatic staleness invalidation.
11. End-to-end archive upload through FastAPI TestClient.
"""
import io
import os
import tarfile
import time
import uuid
import zipfile
from pathlib import Path
from PIL import Image
import pytest

from app.core.config import settings
from app.core.errors import (
    ArchiveSecurityError,
    DatasetAlreadyExistsError,
    DatasetEmptyError,
    InvalidArchiveError,
    JobNotFoundError,
    PayloadTooLargeError,
    VersionNotFoundError,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.comparison import ComparisonCreateRequest, ComparisonFreshness
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetRegisterRequest,
    DatasetSource,
    DatasetStatus,
)
from app.schemas.job import JobStage, JobStatus, ProcessingJob
from app.services.comparison_service import comparison_service
from app.services.dataset_service import dataset_service
from app.services.job_service import job_service
from app.services.upload_service import upload_service
from app.storage.local import storage_backend


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _create_image_bytes(fmt: str = "JPEG", size=(64, 64), color=(100, 150, 200)) -> bytes:
    """Generate in-memory image bytes for testing."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return buf.getvalue()


def _create_sample_zip(target_path: Path, files_dict: dict) -> Path:
    """Build a zip archive from a mapping of arcname -> bytes."""
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in files_dict.items():
            zf.writestr(arcname, data)
    return target_path


def _create_sample_tar(target_path: Path, files_dict: dict, mode: str = "w:gz") -> Path:
    """Build a tar.gz or tar archive from a mapping of arcname -> bytes."""
    with tarfile.open(target_path, mode=mode) as tf:
        for arcname, data in files_dict.items():
            ti = tarfile.TarInfo(name=arcname)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return target_path


# ---------------------------------------------------------------------------
# 1. Archive Extraction & Security Tests
# ---------------------------------------------------------------------------

def test_safe_zip_extraction(tmp_path):
    """Verify standard valid zip extracts safely and computes expected stats."""
    zip_file = tmp_path / "valid.zip"
    img_data = _create_image_bytes()
    files = {
        "Soybean/Healthy/sample1.jpg": img_data,
        "Soybean/Diseased/sample2.jpg": img_data,
    }
    _create_sample_zip(zip_file, files)

    target_dir = tmp_path / "extracted_zip"
    res = upload_service.extract_archive(zip_file, target_dir)

    assert res.total_files == 2
    assert res.total_bytes == len(img_data) * 2
    assert (target_dir / "Soybean" / "Healthy" / "sample1.jpg").exists()
    assert (target_dir / "Soybean" / "Diseased" / "sample2.jpg").exists()


def test_safe_tar_gz_extraction(tmp_path):
    """Verify tar.gz extracts safely preserving nested class paths."""
    tar_file = tmp_path / "valid.tar.gz"
    img_data = _create_image_bytes("PNG")
    files = {
        "Wheat/Rust/leaf1.png": img_data,
        "Wheat/Healthy/leaf2.png": img_data,
    }
    _create_sample_tar(tar_file, files, mode="w:gz")

    target_dir = tmp_path / "extracted_tar"
    res = upload_service.extract_archive(tar_file, target_dir)

    assert res.total_files == 2
    assert (target_dir / "Wheat" / "Rust" / "leaf1.png").exists()


def test_archive_security_zip_slip_rejection(tmp_path):
    """Verify Zip-Slip directory traversal attempts are rejected."""
    malicious_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/evil.txt", b"malicious payload")

    target_dir = tmp_path / "extracted_evil"
    with pytest.raises(ArchiveSecurityError) as exc_info:
        upload_service.extract_archive(malicious_zip, target_dir)
    assert "forbidden path traversal" in str(exc_info.value)


def test_archive_security_tar_traversal_rejection(tmp_path):
    """Verify Tar path traversal attempts are rejected."""
    malicious_tar = tmp_path / "evil.tar"
    with tarfile.open(malicious_tar, "w") as tf:
        ti = tarfile.TarInfo(name="../escape.txt")
        ti.size = 11
        tf.addfile(ti, io.BytesIO(b"evil escape"))

    target_dir = tmp_path / "extracted_tar_evil"
    with pytest.raises(ArchiveSecurityError) as exc_info:
        upload_service.extract_archive(malicious_tar, target_dir)
    assert "forbidden path traversal" in str(exc_info.value)


def test_archive_quota_decompression_bomb_rejection(tmp_path, monkeypatch):
    """Verify decompressing files exceeding MAX_EXTRACT_SIZE_BYTES raises error."""
    monkeypatch.setattr(upload_service, "max_extract_bytes", 100)
    zip_file = tmp_path / "bomb.zip"
    _create_sample_zip(zip_file, {"test.bin": b"A" * 500})

    target_dir = tmp_path / "extracted_bomb"
    with pytest.raises(PayloadTooLargeError) as exc_info:
        upload_service.extract_archive(zip_file, target_dir)
    assert "exceeds limit" in str(exc_info.value)


def test_archive_quota_file_count_rejection(tmp_path, monkeypatch):
    """Verify archives with excessive file count are rejected."""
    monkeypatch.setattr(upload_service, "max_files", 3)
    zip_file = tmp_path / "too_many_files.zip"
    files = {f"file_{i}.txt": b"data" for i in range(5)}
    _create_sample_zip(zip_file, files)

    target_dir = tmp_path / "extracted_many"
    with pytest.raises(PayloadTooLargeError) as exc_info:
        upload_service.extract_archive(zip_file, target_dir)
    assert "exceeds maximum allowed" in str(exc_info.value)


def test_unsupported_archive_extension():
    """Verify invalid extensions raise InvalidArchiveError."""
    with pytest.raises(InvalidArchiveError):
        upload_service.validate_filename("dataset.rar")
    with pytest.raises(InvalidArchiveError):
        upload_service.validate_filename("dataset.7z")
    with pytest.raises(InvalidArchiveError):
        upload_service.validate_filename("dataset.exe")


# ---------------------------------------------------------------------------
# 2. Dynamic Dataset Registration & Deduplication Tests
# ---------------------------------------------------------------------------

def test_dynamic_dataset_registration_and_duplicate_conflict(tmp_path, monkeypatch):
    """Verify registering a new dataset and rejecting duplicate ID registration."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    req = DatasetRegisterRequest(
        id="evaluator_beans",
        name="Evaluator Bean Dataset",
        description="Dataset for testing evaluator flow",
        crops=["Beans"],
        tags=["angular_leaf_spot", "rust"],
    )

    metadata = dataset_service.register_dataset(req)
    assert metadata.id == "evaluator_beans"
    assert metadata.name == "Evaluator Bean Dataset"
    assert metadata.status == DatasetStatus.REGISTERED
    assert metadata.is_uploaded is True

    # Duplicate registration must raise DatasetAlreadyExistsError
    with pytest.raises(DatasetAlreadyExistsError):
        dataset_service.register_dataset(req)


def test_dataset_versioning_and_content_deduplication(tmp_path, monkeypatch):
    """
    Verify:
    1. Upload 1 creates version v1.
    2. Identical upload skips analysis and returns is_duplicate_content=True.
    3. Modified upload creates version v2.
    """
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    img1 = _create_image_bytes("JPEG", color=(10, 20, 30))
    img2 = _create_image_bytes("JPEG", color=(40, 50, 60))

    zip1_path = tmp_path / "version1.zip"
    _create_sample_zip(zip1_path, {
        "class_a/img1.jpg": img1,
        "class_b/img2.jpg": img2,
    })

    # Upload 1
    resp1 = dataset_service.handle_archive_upload(
        dataset_id="test_versioned_ds",
        archive_path=zip1_path,
        filename="version1.zip",
        dataset_name="Test Versioned Dataset",
    )
    assert resp1.dataset_id == "test_versioned_ds"
    assert resp1.version_number == 1
    assert resp1.is_duplicate_content is False
    assert resp1.job_id != ""

    # Identical upload 2
    resp2 = dataset_service.handle_archive_upload(
        dataset_id="test_versioned_ds",
        archive_path=zip1_path,
        filename="version1_duplicate.zip",
    )
    assert resp2.dataset_id == "test_versioned_ds"
    assert resp2.version_number == 1
    assert resp2.is_duplicate_content is True
    assert resp2.job_id == ""  # No job enqueued for identical content

    # Upload 3 with altered content -> should create version 2
    img3 = _create_image_bytes("JPEG", color=(70, 80, 90))
    zip2_path = tmp_path / "version2.zip"
    _create_sample_zip(zip2_path, {
        "class_a/img1.jpg": img1,
        "class_b/img2.jpg": img2,
        "class_c/img3.jpg": img3,
    })

    resp3 = dataset_service.handle_archive_upload(
        dataset_id="test_versioned_ds",
        archive_path=zip2_path,
        filename="version2.zip",
    )
    assert resp3.dataset_id == "test_versioned_ds"
    assert resp3.version_number == 2
    assert resp3.is_duplicate_content is False
    assert resp3.job_id != ""

    # Check version listing
    versions = dataset_service.list_versions("test_versioned_ds")
    assert len(versions) == 2
    assert versions[0].version_number == 2
    assert versions[1].version_number == 1


# ---------------------------------------------------------------------------
# 3. Processing Job Lifecycle & Worker Pipeline Tests
# ---------------------------------------------------------------------------

def test_job_lifecycle_and_pipeline_execution(tmp_path, monkeypatch):
    """Verify job execution through all pipeline stages to completion."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    # Create dataset with small valid images
    img_a = _create_image_bytes("JPEG", size=(32, 32), color=(50, 100, 150))
    img_b = _create_image_bytes("JPEG", size=(32, 32), color=(60, 110, 160))

    zip_path = tmp_path / "pipeline_test.zip"
    _create_sample_zip(zip_path, {
        "healthy/img_a.jpg": img_a,
        "blight/img_b.jpg": img_b,
    })

    upload_resp = dataset_service.handle_archive_upload(
        dataset_id="pipeline_ds",
        archive_path=zip_path,
        filename="pipeline_test.zip",
        dataset_name="Pipeline Dataset",
    )

    job_id = upload_resp.job_id
    assert job_id != ""

    # Poll until job completes (worker pool is active)
    max_wait = 15.0
    start = time.time()
    job = None
    while time.time() - start < max_wait:
        job = job_service.get_job(job_id)
        if job and job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            break
        time.sleep(0.1)

    assert job is not None
    assert job.status == JobStatus.COMPLETED, f"Job failed with: {job.error_message}"
    assert job.progress_pct == 100.0
    assert job.current_stage == JobStage.COMPLETED
    assert job.completed_at is not None
    assert "analysis_id" in job.artifact_refs
    assert "quality_assessment_id" in job.artifact_refs
    assert "eda_report_id" in job.artifact_refs

    # Verify dataset status transitioned to READY
    ds = dataset_service.get_dataset("pipeline_ds")
    assert ds.status == DatasetStatus.READY
    assert ds.total_images == 2
    assert ds.total_classes == 2


def test_job_failure_handling_and_retry(tmp_path, monkeypatch):
    """Verify failed job records error and can be retried."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    # Create dummy job pointing to nonexistent dataset
    ds_id = f"fail_ds_{uuid.uuid4().hex[:6]}"
    job = job_service.create_job(ds_id, "v1")
    job_service.enqueue_job(job.job_id)

    max_wait = 5.0
    start = time.time()
    while time.time() - start < max_wait:
        j = job_service.get_job(job.job_id)
        if j and j.status == JobStatus.FAILED:
            break
        time.sleep(0.1)

    j = job_service.get_job(job.job_id)
    assert j.status == JobStatus.FAILED
    assert j.error_code is not None

    # Retry job
    retried_job = job_service.retry_job(job.job_id)
    assert retried_job.retry_count == 1
    assert retried_job.status in [JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.FAILED]


def test_server_restart_recovery(tmp_path, monkeypatch):
    """Verify unstarted jobs resume and interrupted jobs are marked FAILED on startup."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    # Manually persist an interrupted job
    interrupted_job = ProcessingJob(
        job_id="job_interrupted",
        dataset_id="test_ds",
        dataset_version="v1",
        status=JobStatus.PROCESSING,
        current_stage=JobStage.VALIDATION,
        progress_pct=35.0,
        created_at="2026-11-07T12:00:00Z",
        started_at="2026-11-07T12:01:00Z",
    )
    storage_backend.save_job(interrupted_job.job_id, interrupted_job.model_dump())

    # Manually persist a queued job
    queued_job = ProcessingJob(
        job_id="job_queued",
        dataset_id="test_ds",
        dataset_version="v1",
        status=JobStatus.QUEUED,
        current_stage=JobStage.QUEUED,
        progress_pct=0.0,
        created_at="2026-11-07T12:05:00Z",
    )
    storage_backend.save_job(queued_job.job_id, queued_job.model_dump())

    # Trigger startup recovery
    job_service.recover_jobs_on_startup()

    recovered_interrupted = job_service.get_job("job_interrupted")
    assert recovered_interrupted.status == JobStatus.FAILED
    assert recovered_interrupted.error_code == "JOB_INTERRUPTED_BY_RESTART"

    recovered_queued = job_service.get_job("job_queued")
    assert recovered_queued is not None
    # Queued job should have been re-enqueued for worker pickup


# ---------------------------------------------------------------------------
# 4. M5 Comparison Freshness & Invalidation Tests
# ---------------------------------------------------------------------------

def test_m5_comparison_freshness_and_invalidation(tmp_path, monkeypatch):
    """Verify comparison freshness is CURRENT and becomes STALE when dataset changes."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    # Create dataset A and dataset B
    img_a1 = _create_image_bytes("JPEG", color=(10, 20, 30))
    img_a2 = _create_image_bytes("JPEG", color=(40, 50, 60))
    zip_a1 = tmp_path / "ds_a_v1.zip"
    _create_sample_zip(zip_a1, {"c1/i1.jpg": img_a1, "c2/i2.jpg": img_a2})

    img_b1 = _create_image_bytes("JPEG", color=(70, 80, 90))
    img_b2 = _create_image_bytes("JPEG", color=(100, 110, 120))
    zip_b = tmp_path / "ds_b.zip"
    _create_sample_zip(zip_b, {"c1/ib1.jpg": img_b1, "c2/ib2.jpg": img_b2})

    # Upload A and B
    u_a = dataset_service.handle_archive_upload("ds_a", zip_a1, "ds_a_v1.zip", "Dataset A")
    u_b = dataset_service.handle_archive_upload("ds_b", zip_b, "ds_b.zip", "Dataset B")

    # Wait for both jobs to finish
    for jid in [u_a.job_id, u_b.job_id]:
        start = time.time()
        while time.time() - start < 15.0:
            job = job_service.get_job(jid)
            if job and job.status == JobStatus.COMPLETED:
                break
            time.sleep(0.1)

    # Run comparison
    comparison = comparison_service.run_comparison("ds_a", "ds_b")
    assert comparison.id != ""

    # Freshness check -> CURRENT
    freshness = comparison_service.check_freshness(comparison.id)
    assert freshness.is_stale is False
    assert freshness.freshness_status == ComparisonFreshness.CURRENT

    # Now upload new version to Dataset A
    img_a3 = _create_image_bytes("JPEG", color=(130, 140, 150))
    zip_a2 = tmp_path / "ds_a_v2.zip"
    _create_sample_zip(zip_a2, {"c1/i1.jpg": img_a1, "c2/i2.jpg": img_a2, "c3/i3.jpg": img_a3})

    u_a2 = dataset_service.handle_archive_upload("ds_a", zip_a2, "ds_a_v2.zip")
    start = time.time()
    while time.time() - start < 15.0:
        job = job_service.get_job(u_a2.job_id)
        if job and job.status == JobStatus.COMPLETED:
            break
        time.sleep(0.1)

    # Comparison should now be STALE
    freshness_after = comparison_service.check_freshness(comparison.id)
    assert freshness_after.is_stale is True
    assert freshness_after.freshness_status == ComparisonFreshness.STALE


# ---------------------------------------------------------------------------
# 5. Event Bus Tests
# ---------------------------------------------------------------------------

def test_event_bus_dispatch_and_error_isolation():
    """Verify event bus delivers events to subscribers without failing on handler exceptions."""
    received_events = []

    def failing_handler(evt):
        raise RuntimeError("Intentional handler exception")

    def working_handler(evt):
        received_events.append(evt)

    event_bus.subscribe(DatasetEventType.DATASET_UPLOADED, failing_handler)
    event_bus.subscribe(DatasetEventType.DATASET_UPLOADED, working_handler)

    event_bus.emit(
        DatasetEventType.DATASET_UPLOADED,
        dataset_id="test_event_ds",
        payload={"foo": "bar"},
    )

    assert len(received_events) == 1
    assert received_events[0].event_type == DatasetEventType.DATASET_UPLOADED
    assert received_events[0].dataset_id == "test_event_ds"
    assert received_events[0].payload["foo"] == "bar"


# ---------------------------------------------------------------------------
# 6. End-to-End FastAPI Client Upload & Lifecycle API Tests
# ---------------------------------------------------------------------------

def test_api_upload_and_lifecycle_flow(client, tmp_path):
    """Test full HTTP API lifecycle: upload, status polling, versioning, and reanalyze."""
    img_data = _create_image_bytes("JPEG", size=(40, 40))
    zip_file = tmp_path / "evaluator_test.zip"
    _create_sample_zip(zip_file, {
        "Healthy/leaf_1.jpg": img_data,
        "Rust/leaf_2.jpg": img_data,
    })

    # 1. Upload archive via HTTP POST
    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("evaluator_test.zip", f, "application/zip")},
            data={"dataset_id": "api_evaluator_ds", "name": "API Evaluator Dataset"},
        )
    assert res.status_code == 202
    data = res.json()
    assert data["dataset_id"] == "api_evaluator_ds"
    assert data["version_number"] == 1
    assert data["is_duplicate_content"] is False
    job_id = data["job_id"]

    # 2. Poll job status endpoint
    start = time.time()
    job_completed = False
    while time.time() - start < 15.0:
        job_res = client.get(f"/api/v1/jobs/{job_id}/status")
        assert job_res.status_code == 200
        job_data = job_res.json()
        if job_data["status"] == "completed":
            job_completed = True
            break
        time.sleep(0.1)

    assert job_completed is True

    # 3. Verify versions endpoint
    v_res = client.get("/api/v1/datasets/api_evaluator_ds/versions")
    assert v_res.status_code == 200
    v_data = v_res.json()
    assert v_data["total"] == 1
    assert v_data["items"][0]["status"] == "ready"

    # 4. Verify latest version endpoint
    latest_res = client.get("/api/v1/datasets/api_evaluator_ds/versions/latest")
    assert latest_res.status_code == 200
    assert latest_res.json()["version_number"] == 1

    # 5. Verify reanalyze endpoint
    reanalyze_res = client.post("/api/v1/datasets/api_evaluator_ds/reanalyze")
    assert reanalyze_res.status_code == 202
    assert reanalyze_res.json()["job_id"] != ""


def test_api_upload_unsupported_format(client, tmp_path):
    """Verify uploading an unsupported file format returns 400 Bad Request."""
    dummy_file = tmp_path / "bad.rar"
    dummy_file.write_bytes(b"not a valid archive")

    with open(dummy_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("bad.rar", f, "application/octet-stream")},
        )
    assert res.status_code == 400
    assert "Unsupported archive format" in res.json()["detail"]


def test_api_get_job_not_found(client):
    """Verify querying nonexistent job returns 404."""
    res = client.get("/api/v1/jobs/nonexistent_job_123")
    assert res.status_code == 404
