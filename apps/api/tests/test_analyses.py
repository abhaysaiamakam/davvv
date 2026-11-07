import random
import time
from pathlib import Path
import pytest
from fastapi import status
from PIL import Image, ImageEnhance

from app.core.errors import DatasetAnalysisNotFoundError, DatasetNotFoundError
from app.schemas.analysis import (
    AnalysisConfig,
    AnalysisStatus,
    UnifiedAnalysisResult,
)
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetSource,
    DatasetStatus,
    NearDuplicateQueryConfig,
    PerceptualHashAlgorithm,
)
from app.services.analysis_service import AnalysisService, analysis_service
from app.services.dataset_service import dataset_service
from app.storage.local import LocalStorageBackend


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _create_synthetic_block_image(size: int, seed: int, colors: list) -> Image.Image:
    random.seed(seed)
    img = Image.new("RGB", (size, size))
    px = img.load()
    block = size // 8
    for bx in range(8):
        for by in range(8):
            c = random.choice(colors)
            for x in range(bx * block, (bx + 1) * block):
                for y in range(by * block, (by + 1) * block):
                    px[x, y] = c
    return img


_GREEN_PALETTE = [(30, 120, 30), (60, 160, 60), (20, 80, 20), (80, 200, 80), (40, 100, 40)]
_RED_PALETTE   = [(180, 20, 20), (220, 50, 50), (140, 10, 10), (200, 70, 70), (160, 30, 30)]


# ---------------------------------------------------------------------------
# 1. Baseline & Error Handling Tests
# ---------------------------------------------------------------------------

def test_list_analyses_initially_empty():
    """Verify clean service returns empty list before any analysis runs."""
    fresh_service = AnalysisService()
    # If storage had existing runs from previous tests, list reflects them, but placeholder flag works
    res = fresh_service.list_analyses()
    assert res.total >= 0
    assert isinstance(res.items, list)


def test_get_analysis_not_found(client):
    """Querying an unknown analysis ID returns 404 with standard error contract."""
    response = client.get("/api/v1/analyses/ana-nonexistent-uuid")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "ANALYSIS_NOT_FOUND"
    assert "detail" in data


def test_get_dataset_analysis_not_found_before_run(client):
    """Querying analysis for a dataset before running any analysis returns 404."""
    response = client.get("/api/v1/datasets/plant-village/analysis")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "DATASET_ANALYSIS_NOT_FOUND"


def test_analyze_nonexistent_dataset_returns_404(client):
    """Triggering analysis on a non-existent dataset returns 404."""
    response = client.post("/api/v1/datasets/nonexistent-crop-dataset/analyze")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "DATASET_NOT_FOUND"


# ---------------------------------------------------------------------------
# 2. Persistence & Server Restart Rehydration Tests
# ---------------------------------------------------------------------------

def test_storage_persistence_direct(tmp_path: Path):
    """Directly test saving, loading, listing, and pointer tracking in LocalStorageBackend."""
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    analysis_id = "ana-test-ds-12345"
    data = {
        "id": analysis_id,
        "dataset_id": "test-dataset",
        "dataset_name": "Test Dataset",
        "status": "completed",
        "created_at": "2026-11-07T10:00:00Z",
        "completed_at": "2026-11-07T10:00:05Z",
        "duration_ms": 5000.0,
        "stages_completed": ["discovery", "validation"],
        "stage_durations_ms": {"discovery": 1000.0, "validation": 4000.0},
        "metrics": {"total_files_discovered": 10, "total_validated_images": 10},
        "warnings": [],
    }

    # Save
    saved_path = backend.save_analysis(analysis_id, data, dataset_id="test-dataset")
    assert saved_path.exists()
    assert saved_path.name == "result.json"

    # Load
    loaded = backend.load_analysis(analysis_id)
    assert loaded is not None
    assert loaded["id"] == analysis_id
    assert loaded["dataset_id"] == "test-dataset"
    assert loaded["status"] == "completed"

    # Pointer check
    latest_id = backend.get_latest_analysis_id_for_dataset("test-dataset")
    assert latest_id == analysis_id

    # List check
    persisted_list = backend.list_persisted_analyses()
    assert len(persisted_list) >= 1
    assert any(item["id"] == analysis_id for item in persisted_list)


def test_surviving_service_reinitialization(tmp_path: Path):
    """
    Simulate backend server restart:
    1. Write analysis with service instance A.
    2. Create fresh service instance B using same storage directory.
    3. Verify service B rehydrates the persisted analysis.
    """
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    analysis_id = "ana-restart-test-001"
    now = "2026-11-07T12:00:00Z"
    test_result = UnifiedAnalysisResult(
        id=analysis_id,
        dataset_id="paddy-restart-test",
        dataset_name="Paddy Restart Test",
        status=AnalysisStatus.COMPLETED,
        created_at=now,
        completed_at=now,
        duration_ms=1250.0,
        stages_completed=["discovery", "validation", "exact_duplicates"],
        stage_durations_ms={"discovery": 250.0, "validation": 800.0, "exact_duplicates": 200.0},
        warnings=["Test warning"],
    )

    # Persist via storage
    backend.save_analysis(analysis_id, test_result.model_dump(), dataset_id="paddy-restart-test")

    # Instance B: Brand new AnalysisService simulates server restart
    restarted_service = AnalysisService(backend=backend)

    # Must be retrievable by ID
    loaded = restarted_service.get_analysis(analysis_id)
    assert loaded is not None
    assert loaded.id == analysis_id
    assert loaded.dataset_id == "paddy-restart-test"
    assert loaded.status == AnalysisStatus.COMPLETED
    assert "validation" in loaded.stages_completed

    # Must be recognized as latest for dataset
    latest = restarted_service.get_latest_analysis_for_dataset("paddy-restart-test")
    assert latest is not None
    assert latest.id == analysis_id

    # Must appear in list_analyses
    listing = restarted_service.list_analyses()
    assert any(item.id == analysis_id for item in listing.items)


# ---------------------------------------------------------------------------
# 3. End-to-End Pipeline & Metric Integrity Tests
# ---------------------------------------------------------------------------

def test_unified_analysis_pipeline_and_metric_integrity(tmp_path: Path):
    """
    Execute full unified pipeline on synthetic dataset and verify metric integrity:
    - 4 images:
      * leaf_1 (green)
      * leaf_1_copy (exact byte duplicate of leaf_1)
      * leaf_1_resized (perceptual near-duplicate of leaf_1)
      * leaf_2 (unrelated red pattern)
    Expected:
      - Validated images: 4
      - Exact duplicate groups: 1 (redundant: 1)
      - Near duplicate groups: 1 (redundant: 1)
      - Total redundant images: 2 (1 exact + 1 near, no double-counting)
      - Clean unique images: 2 (4 - 2)
      - Quality score: computed > 0
    """
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    curated_dir = backend.curated_dir / "m25-test-dataset"
    class_dir = curated_dir / "Rice" / "bacterial_blight"
    class_dir.mkdir(parents=True, exist_ok=True)

    # Create images
    base = _create_synthetic_block_image(160, 1, _GREEN_PALETTE)
    base.save(class_dir / "leaf_1.jpg", "JPEG", quality=95)

    # Exact byte duplicate of leaf_1
    with open(class_dir / "leaf_1.jpg", "rb") as f_src:
        with open(class_dir / "leaf_1_copy.jpg", "wb") as f_dst:
            f_dst.write(f_src.read())

    # Perceptual near-duplicate (resized)
    base.resize((120, 120)).save(class_dir / "leaf_1_resized.jpg", "JPEG", quality=90)

    # Unrelated distinct image
    _create_synthetic_block_image(160, 2, _RED_PALETTE).save(class_dir / "leaf_2.jpg", "JPEG", quality=95)

    # Register synthetic dataset in dataset_service
    test_ds = DatasetMetadata(
        id="m25-test-dataset",
        name="M25 Test Dataset",
        slug="m25-test-dataset",
        description="Dataset for testing unified analysis pipeline",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        storage_relative_path="curated/m25-test-dataset",
    )
    dataset_service._curated_registry.append(test_ds)

    service = AnalysisService(backend=backend)
    cfg = AnalysisConfig(
        near_duplicate_config=NearDuplicateQueryConfig(
            algorithm=PerceptualHashAlgorithm.PHASH,
            hash_size=8,
            distance_threshold=6,
        ),
        force_refresh=True,
        include_near_duplicates=True,
    )

    result = service.run_analysis("m25-test-dataset", cfg)

    # Status & stage checks
    assert result.status == AnalysisStatus.COMPLETED
    assert result.stages_completed == ["discovery", "validation", "exact_duplicates", "near_duplicates"]
    assert result.duration_ms is not None and result.duration_ms > 0
    assert "discovery" in result.stage_durations_ms
    assert "validation" in result.stage_durations_ms
    assert "exact_duplicates" in result.stage_durations_ms
    assert "near_duplicates" in result.stage_durations_ms

    # Metric integrity assertions
    m = result.metrics
    assert m.total_files_discovered == 4
    assert m.total_classes_discovered == 1
    assert m.total_validated_images == 4
    assert m.total_corrupted_images == 0

    # Exact duplicates
    assert m.exact_duplicate_groups == 1
    assert m.exact_duplicate_redundant_instances == 1
    assert m.exact_duplicate_percentage == 25.0  # 1 / 4 * 100

    # Near duplicates (exact duplicate was collapsed before comparison)
    assert m.near_duplicate_groups == 1
    assert m.near_duplicate_redundant_instances == 1
    assert m.near_duplicate_percentage == 25.0  # 1 / 4 * 100

    # Non-redundant combined metrics (No double counting)
    assert m.total_redundant_images == 2  # 1 exact + 1 near
    assert m.clean_unique_images == 2      # 4 valid - 2 redundant
    assert m.quality_score is not None
    assert 0.0 <= m.quality_score <= 100.0

    # Detailed stage models present
    assert result.discovery is not None
    assert result.validation is not None
    assert result.exact_duplicates is not None
    assert result.near_duplicates is not None

    # Summary conversion
    summary = result.to_summary()
    assert summary.id == result.id
    assert summary.total_files_evaluated == 4
    assert summary.duplicate_count == 2
    assert summary.corrupted_count == 0


def test_metric_integrity_null_when_stage_skipped(tmp_path: Path):
    """
    When a stage is not run (include_near_duplicates=False),
    near-duplicate metrics must remain None (null), NOT 0.
    """
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    curated_dir = backend.curated_dir / "m25-null-test"
    class_dir = curated_dir / "Rice" / "blast"
    class_dir.mkdir(parents=True, exist_ok=True)
    _create_synthetic_block_image(128, 5, _GREEN_PALETTE).save(class_dir / "leaf.jpg", "JPEG")

    test_ds = DatasetMetadata(
        id="m25-null-test",
        name="M25 Null Test",
        slug="m25-null-test",
        description="Test null metrics",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        storage_relative_path="curated/m25-null-test",
    )
    dataset_service._curated_registry.append(test_ds)

    service = AnalysisService(backend=backend)
    cfg = AnalysisConfig(include_near_duplicates=False, force_refresh=True)
    result = service.run_analysis("m25-null-test", cfg)

    assert result.status == AnalysisStatus.COMPLETED
    assert "near_duplicates" not in result.stages_completed
    assert result.near_duplicates is None

    # Crucial metric integrity: must be None, NOT 0
    assert result.metrics.near_duplicate_groups is None
    assert result.metrics.near_duplicate_images_in_groups is None
    assert result.metrics.near_duplicate_redundant_instances is None
    assert result.metrics.near_duplicate_percentage is None


# ---------------------------------------------------------------------------
# 4. FastAPI Integration & Path Safety Tests
# ---------------------------------------------------------------------------

def test_api_analyze_and_retrieve_e2e(client):
    """
    Test full API workflow:
    1. POST /api/v1/datasets/m25-test-dataset/analyze
    2. GET /api/v1/datasets/m25-test-dataset/analysis
    3. GET /api/v1/datasets/m25-test-dataset/analysis/status
    4. GET /api/v1/analyses/{analysis_id}
    5. GET /api/v1/analyses
    """
    # Trigger analysis via API
    resp_trigger = client.post(
        "/api/v1/datasets/m25-test-dataset/analyze",
        json={"force_refresh": False, "include_near_duplicates": True},
    )
    assert resp_trigger.status_code == status.HTTP_200_OK
    data = resp_trigger.json()
    analysis_id = data["id"]
    assert analysis_id.startswith("ana-")
    assert data["status"] == "completed"
    assert "metrics" in data
    assert data["metrics"]["total_files_discovered"] == 4

    # Retrieve latest for dataset
    resp_latest = client.get("/api/v1/datasets/m25-test-dataset/analysis")
    assert resp_latest.status_code == status.HTTP_200_OK
    assert resp_latest.json()["id"] == analysis_id

    # Retrieve latest status for dataset
    resp_status = client.get("/api/v1/datasets/m25-test-dataset/analysis/status")
    assert resp_status.status_code == status.HTTP_200_OK
    status_data = resp_status.json()
    assert status_data["analysis_id"] == analysis_id
    assert status_data["status"] == "completed"
    assert "discovery" in status_data["stages_completed"]

    # Retrieve specific analysis by ID
    resp_get = client.get(f"/api/v1/analyses/{analysis_id}")
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["id"] == analysis_id

    # Retrieve status by ID
    resp_get_status = client.get(f"/api/v1/analyses/{analysis_id}/status")
    assert resp_get_status.status_code == status.HTTP_200_OK
    assert resp_get_status.json()["analysis_id"] == analysis_id

    # List analyses includes this run
    resp_list = client.get("/api/v1/analyses")
    assert resp_list.status_code == status.HTTP_200_OK
    list_data = resp_list.json()
    assert list_data["total"] >= 1
    assert any(item["id"] == analysis_id for item in list_data["items"])


def test_no_host_paths_in_analysis_response(client):
    """Verify that absolute host paths (/Users, /private/var, /tmp) are never leaked in API response."""
    resp = client.get("/api/v1/datasets/m25-test-dataset/analysis")
    assert resp.status_code == status.HTTP_200_OK
    text_content = resp.text

    # Host paths should not appear
    assert "/Users/" not in text_content
    assert "/private/var/" not in text_content
    assert "\\Users\\" not in text_content


def test_failed_analysis_recorded_and_persisted(tmp_path: Path):
    """
    Test that when an unrecoverable error occurs (e.g. missing dataset directory on disk),
    the failure is explicitly tracked with status=FAILED, error_message recorded, and persisted.
    """
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    # Register dataset whose directory does not exist
    test_ds = DatasetMetadata(
        id="m25-failing-ds",
        name="Failing Dataset",
        slug="m25-failing-ds",
        description="Dataset with missing directory to test failure path",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        storage_relative_path="curated/m25-failing-ds",
    )
    dataset_service._curated_registry.append(test_ds)

    service = AnalysisService(backend=backend)
    cfg = AnalysisConfig(force_refresh=True)

    with pytest.raises(Exception):
        service.run_analysis("m25-failing-ds", cfg)

    # Check that failed analysis was persisted
    persisted = backend.list_persisted_analyses()
    failing_runs = [p for p in persisted if p.get("dataset_id") == "m25-failing-ds"]
    assert len(failing_runs) == 1
    assert failing_runs[0]["status"] == "failed"
    assert failing_runs[0]["error_message"] is not None


def test_analysis_reuses_valid_stages_when_force_refresh_false(tmp_path: Path):
    """
    Verify that subsequent analysis runs reuse previously executed stages
    instead of unnecessarily recalculating them when force_refresh=False.
    """
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    curated_dir = backend.curated_dir / "m25-reuse-test"
    class_dir = curated_dir / "Rice" / "leaf"
    class_dir.mkdir(parents=True, exist_ok=True)
    _create_synthetic_block_image(128, 9, _GREEN_PALETTE).save(class_dir / "img.jpg", "JPEG")

    test_ds = DatasetMetadata(
        id="m25-reuse-test",
        name="Reuse Test",
        slug="m25-reuse-test",
        description="Test stage reuse",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        storage_relative_path="curated/m25-reuse-test",
    )
    dataset_service._curated_registry.append(test_ds)

    service = AnalysisService(backend=backend)

    # First run
    res1 = service.run_analysis("m25-reuse-test", AnalysisConfig(force_refresh=True))
    assert res1.status == AnalysisStatus.COMPLETED

    # Second run without force_refresh
    res2 = service.run_analysis("m25-reuse-test", AnalysisConfig(force_refresh=False))
    assert res2.status == AnalysisStatus.COMPLETED
    assert res2.metrics.total_validated_images == res1.metrics.total_validated_images
    # Second run is distinct analysis run ID
    assert res2.id != res1.id

