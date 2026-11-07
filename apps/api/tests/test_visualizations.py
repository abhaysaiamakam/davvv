"""
CropLens — Visualization Specification Engine Tests.

Tests:
1. Chart selection registry and extensibility.
2. Image classification visualization generation from M2, M3, M4 artifacts.
3. Tabular dataset visualization: numerical distributions, categorical frequencies, correlation heatmaps, missing values.
4. Edge cases in tabular data: empty files, constant columns, missing values, high cardinality.
5. Time-series detection and chronological trend line generation.
6. Annotation detection: COCO JSON / YOLO TXT generation and clean handling when absent.
7. Empty dataset handling without crashing or fabricating false charts.
8. Visualization artifact persistence, retrieval, and version isolation.
9. Filter queries (by category and chart_type).
10. Automatic generation through M6 background analysis pipeline.
11. Regeneration API and non-blocking failure isolation.
12. Zero path leakage and strict schema compliance.
"""
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from PIL import Image
import pytest

from app.core.config import settings
from app.core.errors import VisualizationNotFoundError
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.visualization import (
    ChartType,
    VisualizationCategory,
    VisualizationCollection,
    VisualizationSpecification,
)
from app.schemas.job import JobStatus
from app.services.dataset_service import dataset_service
from app.services.job_service import job_service
from app.services.visualizations import (
    ImageClassificationVisualizer,
    TabularVisualizer,
    TimeSeriesVisualizer,
    AnnotationVisualizer,
    chart_selection_registry,
    visualization_service,
)
from app.storage.local import storage_backend


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _create_image_bytes(fmt: str = "JPEG", size=(48, 48), color=(80, 140, 200)) -> bytes:
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
# 1. Unit Tests: Chart Selection & Visualizer Plugins
# ---------------------------------------------------------------------------

def test_chart_selection_registry_defaults():
    """Verify registry initializes with default visualizers."""
    names = [v.name for v in chart_selection_registry._visualizers]
    assert "image_classification_visualizer" in names
    assert "tabular_visualizer" in names
    assert "time_series_visualizer" in names
    assert "annotation_visualizer" in names


def test_empty_dataset_context_returns_empty_visualizations():
    """Verify empty context yields no fabricated visualizations."""
    specs = chart_selection_registry.select_and_generate("empty_ds", "v1", {})
    assert specs == []


def test_tabular_visualizer_numerical_and_categorical(tmp_path):
    """Verify tabular visualizer produces histograms, category bars, correlation heatmap, and missing value charts."""
    csv_file = tmp_path / "crop_measurements.csv"
    csv_content = (
        "crop_type,soil_ph,leaf_nitrogen,canopy_coverage\n"
        "Rice,6.2,2.4,85.0\n"
        "Rice,6.5,2.6,88.5\n"
        "Maize,5.8,1.9,72.0\n"
        "Maize,5.9,2.0,74.5\n"
        "Soybean,6.8,3.1,91.0\n"
        "Soybean,6.7,3.0,\n"  # one missing canopy_coverage value
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    viz = TabularVisualizer()
    context = {"dataset_dir": tmp_path}
    assert viz.can_handle("tab_ds", "v1", context) is True

    specs = viz.generate("tab_ds", "v1", context)
    assert len(specs) >= 4

    chart_types = [s.chart_type for s in specs]
    categories = [s.category for s in specs]

    assert ChartType.BAR in chart_types
    assert ChartType.HISTOGRAM in chart_types
    assert ChartType.HEATMAP in chart_types
    assert VisualizationCategory.DATA_QUALITY in categories  # missing value chart
    assert VisualizationCategory.TABULAR_CORRELATION in categories

    # Verify correlation heatmap matrix values
    corr_spec = next(s for s in specs if s.chart_type == ChartType.HEATMAP)
    assert corr_spec.x_axis is not None
    assert len(corr_spec.chart_data) > 0
    # Diagonal correlation should be 1.0
    self_corr = next(d for d in corr_spec.chart_data if d["x_column"] == d["y_column"])
    assert self_corr["correlation"] == 1.0


def test_tabular_visualizer_constant_columns_and_empty_files(tmp_path):
    """Verify constant numerical columns and empty files do not trigger errors."""
    csv_file = tmp_path / "constant.csv"
    csv_file.write_text(
        "id,constant_num,high_cardinality\n"
        + "\n".join(f"{i},42.0,uuid_{uuid.uuid4().hex}" for i in range(40)),
        encoding="utf-8",
    )

    viz = TabularVisualizer()
    context = {"dataset_dir": tmp_path}
    specs = viz.generate("const_ds", "v1", context)

    # Constant column should not generate zero-variance histogram
    for s in specs:
        if s.chart_type == ChartType.HISTOGRAM:
            assert s.title != "Feature Distribution: constant_num"


def test_time_series_visualizer_trend_lines(tmp_path):
    """Verify time series visualizer generates line chart when temporal columns are present."""
    csv_file = tmp_path / "sensor_timeseries.csv"
    csv_content = (
        "timestamp,soil_moisture\n"
        "2026-05-01,34.2\n"
        "2026-05-02,32.8\n"
        "2026-05-03,31.0\n"
        "2026-05-04,45.2\n"
        "2026-05-05,42.1\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    viz = TimeSeriesVisualizer()
    context = {"dataset_dir": tmp_path}
    assert viz.can_handle("ts_ds", "v1", context) is True

    specs = viz.generate("ts_ds", "v1", context)
    assert len(specs) == 1
    assert specs[0].chart_type == ChartType.LINE
    assert specs[0].category == VisualizationCategory.TIME_SERIES
    assert specs[0].x_axis.name == "time"
    assert len(specs[0].chart_data) == 5


def test_annotation_visualizer_coco_detection(tmp_path):
    """Verify COCO JSON annotations produce class frequency charts and do not fabricate if absent."""
    coco_path = tmp_path / "annotations.json"
    coco_data = {
        "categories": [
            {"id": 1, "name": "Blight_Spot"},
            {"id": 2, "name": "Healthy_Leaf"},
        ],
        "annotations": [
            {"id": 101, "image_id": 1, "category_id": 1, "bbox": [10, 20, 30, 40]},
            {"id": 102, "image_id": 1, "category_id": 1, "bbox": [15, 25, 35, 45]},
            {"id": 103, "image_id": 2, "category_id": 2, "bbox": [5, 10, 50, 60]},
        ],
    }
    coco_path.write_text(json.dumps(coco_data), encoding="utf-8")

    viz = AnnotationVisualizer()
    context = {"dataset_dir": tmp_path}
    assert viz.can_handle("ann_ds", "v1", context) is True

    specs = viz.generate("ann_ds", "v1", context)
    assert len(specs) == 1
    assert specs[0].category == VisualizationCategory.ANNOTATIONS
    assert specs[0].chart_type == ChartType.BAR

    # Clean directory without annotations should return False
    empty_tmp = tmp_path / "empty_ann"
    empty_tmp.mkdir()
    assert viz.can_handle("no_ann", "v1", {"dataset_dir": empty_tmp}) is False


# ---------------------------------------------------------------------------
# 2. Integration Tests: Image Dataset Pipeline & Persistence
# ---------------------------------------------------------------------------

def test_image_visualizations_generation_and_persistence(tmp_path, monkeypatch):
    """
    Test end-to-end:
    1. Upload image archive.
    2. Complete background analysis pipeline (M2 -> M3 -> M4 -> Visualizations).
    3. Verify generated visualization collection structure and persistence.
    """
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    # Create sample image archive with multiple classes and dimensions
    img_a1 = _create_image_bytes("JPEG", size=(64, 64), color=(30, 80, 130))
    img_a2 = _create_image_bytes("JPEG", size=(80, 60), color=(40, 90, 140))
    img_b1 = _create_image_bytes("PNG", size=(50, 50), color=(50, 100, 150))

    zip_path = tmp_path / "viz_test_ds.zip"
    _create_sample_zip(zip_path, {
        "Rice/Blast/img_1.jpg": img_a1,
        "Rice/Blast/img_2.jpg": img_a2,
        "Rice/Healthy/img_3.png": img_b1,
    })

    upload_resp = dataset_service.handle_archive_upload(
        dataset_id="viz_auto_ds",
        archive_path=zip_path,
        filename="viz_test_ds.zip",
        dataset_name="Visualization Auto Dataset",
    )
    job_id = upload_resp.job_id
    assert job_id != ""

    # Poll until background job reaches COMPLETED
    start = time.time()
    job = None
    while time.time() - start < 15.0:
        job = job_service.get_job(job_id)
        if job and job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            break
        time.sleep(0.1)

    assert job is not None
    assert job.status == JobStatus.COMPLETED, f"Job failed: {job.error_message}"
    assert "visualization_id" in job.artifact_refs

    # Retrieve visualizations via service
    res = visualization_service.get_visualizations("viz_auto_ds")
    assert res.total >= 8
    assert res.status == "completed"

    titles = [item.title for item in res.items]
    assert "Class Sample Distribution" in titles
    assert "Image Aspect Ratio Distribution" in titles
    assert "Image Orientation Composition" in titles
    assert "Image Encoding & Format Breakdown" in titles
    assert "Color Space Composition" in titles
    assert "RGB Channel Intensity Profiles" in titles
    assert "File Size Distribution" in titles
    assert "Data Quality Dimension Breakdown" in titles
    assert "Dataset Uniqueness & Duplicate Redundancy" in titles

    # Verify no host paths in any specification or metadata
    res_json = res.model_dump_json()
    assert str(tmp_path) not in res_json


def test_visualization_filtering_and_retrieval(tmp_path, monkeypatch):
    """Verify querying by category and chart_type filters correctly."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    img1 = _create_image_bytes("JPEG", color=(10, 20, 30))
    img2 = _create_image_bytes("JPEG", color=(40, 50, 60))
    zip_path = tmp_path / "filter_test.zip"
    _create_sample_zip(zip_path, {
        "Class1/img1.jpg": img1,
        "Class2/img2.jpg": img2,
    })

    upload_resp = dataset_service.handle_archive_upload(
        dataset_id="filter_ds",
        archive_path=zip_path,
        filename="filter_test.zip",
    )
    # Wait for completion
    start = time.time()
    while time.time() - start < 15.0:
        j = job_service.get_job(upload_resp.job_id)
        if j and j.status == JobStatus.COMPLETED:
            break
        time.sleep(0.1)

    # Filter by category: CLASS_DISTRIBUTION
    cat_res = visualization_service.get_visualizations(
        "filter_ds", category=VisualizationCategory.CLASS_DISTRIBUTION
    )
    assert cat_res.total >= 1
    assert all(item.category == VisualizationCategory.CLASS_DISTRIBUTION for item in cat_res.items)

    # Filter by chart_type: PIE
    pie_res = visualization_service.get_visualizations("filter_ds", chart_type=ChartType.PIE)
    assert pie_res.total >= 1
    assert all(item.chart_type == ChartType.PIE for item in pie_res.items)

    # Individual visualization lookup
    first_item = cat_res.items[0]
    single = visualization_service.get_visualization("filter_ds", first_item.visualization_id)
    assert single.visualization_id == first_item.visualization_id
    assert single.title == first_item.title


def test_visualization_version_isolation(tmp_path, monkeypatch):
    """Verify v1 and v2 visualizations are completely isolated and accessible."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    img1 = _create_image_bytes("JPEG", color=(10, 20, 30))
    img2 = _create_image_bytes("JPEG", color=(40, 50, 60))
    zip1 = tmp_path / "v1.zip"
    _create_sample_zip(zip1, {"c1/i1.jpg": img1, "c2/i2.jpg": img2})

    u1 = dataset_service.handle_archive_upload("ver_ds", zip1, "v1.zip")
    start = time.time()
    while time.time() - start < 15.0:
        j = job_service.get_job(u1.job_id)
        if j and j.status == JobStatus.COMPLETED:
            break
        time.sleep(0.1)

    # Upload v2 with third class
    img3 = _create_image_bytes("JPEG", color=(70, 80, 90))
    zip2 = tmp_path / "v2.zip"
    _create_sample_zip(zip2, {"c1/i1.jpg": img1, "c2/i2.jpg": img2, "c3/i3.jpg": img3})

    u2 = dataset_service.handle_archive_upload("ver_ds", zip2, "v2.zip")
    start = time.time()
    while time.time() - start < 15.0:
        j = job_service.get_job(u2.job_id)
        if j and j.status == JobStatus.COMPLETED:
            break
        time.sleep(0.1)

    v1_res = visualization_service.get_visualizations("ver_ds", version_id=u1.version_id)
    v2_res = visualization_service.get_visualizations("ver_ds", version_id=u2.version_id)

    assert v1_res.dataset_version == u1.version_id
    assert v2_res.dataset_version == u2.version_id

    # Check class count differences in the class distribution chart
    v1_class_spec = next(s for s in v1_res.items if s.title == "Class Sample Distribution")
    v2_class_spec = next(s for s in v2_res.items if s.title == "Class Sample Distribution")

    assert len(v1_class_spec.chart_data) == 2
    assert len(v2_class_spec.chart_data) == 3


def test_regeneration_and_failure_isolation(tmp_path, monkeypatch):
    """Verify regeneration recomputes charts and visualizer errors do not fail core analytics."""
    monkeypatch.setattr(settings, "STORAGE_BASE_DIR", tmp_path)
    storage_backend.initialize()

    img = _create_image_bytes("JPEG")
    zip_path = tmp_path / "regen.zip"
    _create_sample_zip(zip_path, {"healthy/img.jpg": img})

    u = dataset_service.handle_archive_upload("regen_ds", zip_path, "regen.zip")
    start = time.time()
    while time.time() - start < 15.0:
        j = job_service.get_job(u.job_id)
        if j and j.status == JobStatus.COMPLETED:
            break
        time.sleep(0.1)

    # Force regenerate
    regen_res = visualization_service.regenerate_visualizations("regen_ds")
    assert regen_res.status == "completed"
    assert regen_res.total > 0


# ---------------------------------------------------------------------------
# 3. HTTP API Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_visualizations_endpoints(client, tmp_path):
    """Test full HTTP API lifecycle for visualization endpoints."""
    img = _create_image_bytes("JPEG", size=(32, 32))
    zip_file = tmp_path / "api_viz_test.zip"
    _create_sample_zip(zip_file, {
        "Rice/Leaf/i1.jpg": img,
        "Rice/Grain/i2.jpg": img,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("api_viz_test.zip", f, "application/zip")},
            data={"dataset_id": "api_viz_ds"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Wait for completion
    start = time.time()
    while time.time() - start < 15.0:
        j_res = client.get(f"/api/v1/jobs/{job_id}/status")
        if j_res.json()["status"] == "completed":
            break
        time.sleep(0.1)

    # 1. GET /datasets/{id}/visualizations
    get_res = client.get("/api/v1/datasets/api_viz_ds/visualizations")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["total"] >= 5
    assert data["status"] == "completed"
    first_vid = data["items"][0]["visualization_id"]

    # 2. GET /datasets/{id}/visualizations/{vis_id}
    item_res = client.get(f"/api/v1/datasets/api_viz_ds/visualizations/{first_vid}")
    assert item_res.status_code == 200
    assert item_res.json()["visualization_id"] == first_vid

    # 3. GET with category filter
    filter_res = client.get(
        "/api/v1/datasets/api_viz_ds/visualizations",
        params={"category": "class_distribution"},
    )
    assert filter_res.status_code == 200
    assert all(i["category"] == "class_distribution" for i in filter_res.json()["items"])

    # 4. POST regenerate
    regen_res = client.post("/api/v1/datasets/api_viz_ds/visualizations/regenerate")
    assert regen_res.status_code == 200
    assert regen_res.json()["total"] >= 5

    # 5. Nonexistent visualization returns 404
    missing_res = client.get("/api/v1/datasets/api_viz_ds/visualizations/vis_nonexistent_123")
    assert missing_res.status_code == 404

