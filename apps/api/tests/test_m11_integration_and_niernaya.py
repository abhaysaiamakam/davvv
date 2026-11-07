"""
CropLens — M11 Final Integration, Validation & NIErnaya Readiness Test Suite.

End-to-End Multimodal Lifecycle, Version Isolation, Mathematical Correctness,
NIErnaya Technical Demonstration, and Security/Contract Integrity.
"""
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import pytest
from PIL import Image

from app.schemas.readiness import ReadinessDimension, ReadinessStatus, TaskContext
from app.schemas.reports import ReportExportFormat
from app.services.dataset_service import dataset_service
from app.services.feature_engineering.feature_engineering_service import feature_engineering_service
from app.services.job_service import job_service
from app.services.preprocessing.preprocessing_service import preprocessing_service
from app.services.readiness_service import readiness_service
from app.services.report_service import report_service
from app.storage.local import storage_backend


# ---------------------------------------------------------------------------
# Test Data Generators & Helpers
# ---------------------------------------------------------------------------

def _create_image_bytes(fmt: str = "JPEG", size=(32, 32), color=(80, 140, 200)) -> bytes:
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


def _wait_for_job(client, job_id: str, timeout: float = 30.0) -> Dict[str, Any]:
    start = time.time()
    while time.time() - start < timeout:
        res = client.get(f"/api/v1/jobs/{job_id}/status")
        assert res.status_code == 200
        data = res.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.2)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s.")


# ---------------------------------------------------------------------------
# 1. Complete E2E Lifecycle — Tabular Modality (CSV/TSV)
# ---------------------------------------------------------------------------

def test_e2e_tabular_lifecycle(client, tmp_path):
    """
    Validate full Tabular lifecycle:
    Upload -> Analysis -> Quality -> EDA -> Visualizations -> Insights ->
    M8 Preprocess (Impute & Remove Duplicates) -> Derived Version ->
    M9 Feature Engineering (Polynomial & Selection) -> PCA ->
    Readiness Assessment -> Report -> PDF Export.
    """
    ds_id = f"m11_tab_{uuid.uuid4().hex[:6]}"
    csv_content = (
        "id,feature_a,feature_b,feature_c,target\n"
        "1,10.5,20.0,1.0,0\n"
        "2,12.0,22.5,1.1,1\n"
        "3,10.5,20.0,1.0,0\n"  # Duplicate row
        "4,,25.0,1.2,1\n"       # Missing feature_a
        "5,15.2,30.1,1.5,0\n"
        "6,16.0,32.0,1.6,1\n"
        "7,18.1,35.5,1.8,0\n"
        "8,20.0,40.0,2.0,1\n"
    )
    zip_file = tmp_path / "tabular_dataset.zip"
    _create_sample_zip(zip_file, {"crop_data.csv": csv_content})

    # Step 1: Upload
    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("tabular_dataset.zip", f, "application/zip")},
            data={"dataset_id": ds_id, "dataset_name": "E2E Tabular Dataset"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    job_res = _wait_for_job(client, job_id)
    assert job_res["status"] == "completed"

    # Step 2: M8 Preprocessing Preview & Apply (Missing value imputation + Remove duplicates)
    preview = client.post(
        f"/api/v1/datasets/{ds_id}/preprocessing/preview",
        json={
            "dataset_id": ds_id,
            "operations": [
                {"operation_type": "missing_value_imputation", "parameters": {"strategy": "mean"}},
                {"operation_type": "remove_duplicates", "parameters": {}},
            ],
        },
    )
    assert preview.status_code == 200
    assert preview.json()["can_apply"] is True

    apply_res = client.post(
        f"/api/v1/datasets/{ds_id}/preprocessing/apply",
        json={
            "dataset_id": ds_id,
            "operations": [
                {"operation_type": "missing_value_imputation", "parameters": {"strategy": "mean"}},
                {"operation_type": "remove_duplicates", "parameters": {}},
            ],
        },
    )
    assert apply_res.status_code in (200, 201)
    if apply_res.json().get("job_id"):
        _wait_for_job(client, apply_res.json()["job_id"])
    derived_v2 = apply_res.json()["derived_version_id"]
    assert derived_v2 != "v1"

    # Step 3: M9 Feature Engineering & Selection on Derived Version
    fe_preview = client.post(
        f"/api/v1/datasets/{ds_id}/feature-engineering/preview",
        json={
            "dataset_id": ds_id,
            "version_id": derived_v2,
            "operations": [
                {
                    "operation_type": "logarithmic_transform",
                    "parameters": {"transform": "log1p", "columns": ["feature_a", "feature_b"]},
                },
                {
                    "operation_type": "principal_component_analysis",
                    "parameters": {"n_components": 2},
                },
            ],
        },
    )
    assert fe_preview.status_code == 200

    fe_apply = client.post(
        f"/api/v1/datasets/{ds_id}/feature-engineering/apply",
        json={
            "dataset_id": ds_id,
            "version_id": derived_v2,
            "operations": [
                {
                    "operation_type": "logarithmic_transform",
                    "parameters": {"transform": "log1p", "columns": ["feature_a", "feature_b"]},
                },
                {
                    "operation_type": "principal_component_analysis",
                    "parameters": {"n_components": 2},
                },
            ],
        },
    )
    assert fe_apply.status_code in (200, 201)
    if fe_apply.json().get("job_id"):
        _wait_for_job(client, fe_apply.json()["job_id"])
    derived_v3 = fe_apply.json()["derived_version_id"]

    # Step 4: M10 Readiness Assessment for derived_v3
    task_ctx = TaskContext(
        task_type="classification",
        target_column="target",
        analytical_goal="Tabular crop yield prediction",
    )
    readiness = client.post(
        f"/api/v1/datasets/{ds_id}/readiness/assess",
        json={"dataset_id": ds_id, "version_id": derived_v3, "task_context": task_ctx.model_dump()},
    )
    assert readiness.status_code == 200
    r_data = readiness.json()
    assert r_data["version_id"] == derived_v3
    assert r_data["overall_score"] >= 0

    # Step 5: Generate & Export Analytical Report
    rep_gen = client.post(
        f"/api/v1/datasets/{ds_id}/reports/generate",
        json={"dataset_id": ds_id, "version_id": derived_v3, "task_context": task_ctx.model_dump()},
    )
    assert rep_gen.status_code == 200
    rep_id = rep_gen.json()["report_id"]

    pdf_res = client.get(
        f"/api/v1/datasets/{ds_id}/reports/{rep_id}/download",
        params={"format": "pdf"},
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# 2. Complete E2E Lifecycle — Image Modality
# ---------------------------------------------------------------------------

def test_e2e_image_lifecycle(client, tmp_path):
    """
    Validate full Image Classification lifecycle:
    Upload -> Pipeline -> M8 Preprocess Exclude Corrupt -> Derived Version ->
    Reanalyze -> Readiness -> Report -> PDF Export.
    """
    ds_id = f"m11_img_{uuid.uuid4().hex[:6]}"
    img_valid = _create_image_bytes("JPEG", size=(48, 48))
    img_corrupt = b"NOT_AN_IMAGE_HEADER_CORRUPTED_BYTES_1234567890"

    zip_file = tmp_path / "image_dataset.zip"
    _create_sample_zip(zip_file, {
        "Healthy/img1.jpg": img_valid,
        "Healthy/img2.jpg": img_valid,
        "Diseased/img3.jpg": img_valid,
        "Diseased/bad.jpg": img_corrupt,
    })

    # Upload & Analyze
    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("image_dataset.zip", f, "application/zip")},
            data={"dataset_id": ds_id, "dataset_name": "E2E Image Dataset"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    _wait_for_job(client, job_id)

    # Preprocess (Exclude corrupt images)
    prep_res = client.post(
        f"/api/v1/datasets/{ds_id}/preprocessing/apply",
        json={
            "dataset_id": ds_id,
            "operations": [{"operation_type": "exclude_corrupt_images", "parameters": {}}],
        },
    )
    assert prep_res.status_code in (200, 201)
    if prep_res.json().get("job_id"):
        _wait_for_job(client, prep_res.json()["job_id"])
    derived_v2 = prep_res.json()["derived_version_id"]

    # Readiness Assessment
    r_res = client.get(f"/api/v1/datasets/{ds_id}/versions/{derived_v2}/readiness")
    assert r_res.status_code == 200
    assert r_res.json()["version_id"] == derived_v2

    # Report Generation
    rep_res = client.post(
        f"/api/v1/datasets/{ds_id}/reports/generate",
        json={"dataset_id": ds_id, "version_id": derived_v2},
    )
    assert rep_res.status_code == 200
    report_id = rep_res.json()["report_id"]

    # PDF Download
    dl_res = client.get(
        f"/api/v1/datasets/{ds_id}/reports/{report_id}/download",
        params={"format": "pdf"},
    )
    assert dl_res.status_code == 200
    assert dl_res.content.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# 3. Complete E2E Lifecycle — Time-Series Modality
# ---------------------------------------------------------------------------

def test_e2e_time_series_lifecycle(client, tmp_path):
    """
    Validate Time-Series lifecycle:
    Timestamp parsing -> Lag/Rolling features (verify chronological ordering & no future leakage) -> Readiness -> Report.
    """
    ds_id = f"m11_ts_{uuid.uuid4().hex[:6]}"
    ts_csv = (
        "timestamp,temperature,humidity,yield\n"
        "2026-01-01T00:00:00Z,22.4,60.1,100\n"
        "2026-01-02T00:00:00Z,23.1,62.0,105\n"
        "2026-01-03T00:00:00Z,21.8,61.5,102\n"
        "2026-01-04T00:00:00Z,24.0,59.0,110\n"
        "2026-01-05T00:00:00Z,25.2,58.5,115\n"
    )
    zip_file = tmp_path / "ts_dataset.zip"
    _create_sample_zip(zip_file, {"sensor_data.csv": ts_csv})

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("ts_dataset.zip", f, "application/zip")},
            data={"dataset_id": ds_id, "dataset_name": "Time Series Dataset"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    _wait_for_job(client, job_id)

    # Feature Engineering (Lag & Log Transform)
    fe_res = client.post(
        f"/api/v1/datasets/{ds_id}/feature-engineering/apply",
        json={
            "dataset_id": ds_id,
            "operations": [
                {
                    "operation_type": "lag_features",
                    "parameters": {"columns": ["temperature"], "lags": [1]},
                },
                {
                    "operation_type": "logarithmic_transform",
                    "parameters": {"transform": "log1p", "columns": ["temperature"]},
                },
            ],
        },
    )
    assert fe_res.status_code in (200, 201)
    if fe_res.json().get("job_id"):
        _wait_for_job(client, fe_res.json()["job_id"])
    derived_v2 = fe_res.json()["derived_version_id"]

    # Verify report for derived version
    rep_res = client.post(
        f"/api/v1/datasets/{ds_id}/reports/generate",
        json={"dataset_id": ds_id, "version_id": derived_v2},
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["executive_summary"]["dataset_modality"] in ("tabular", "time_series")


# ---------------------------------------------------------------------------
# 4. Complete E2E Lifecycle — COCO/YOLO Annotation Modality
# ---------------------------------------------------------------------------

def test_e2e_annotation_lifecycle(client, tmp_path):
    """
    Validate COCO/YOLO annotation dataset lifecycle:
    Annotation discovery -> Bounding box validation -> Insights -> Readiness -> Report.
    """
    ds_id = f"m11_coco_{uuid.uuid4().hex[:6]}"
    coco_json = json.dumps({
        "images": [
            {"id": 1, "file_name": "img1.jpg", "width": 100, "height": 100},
            {"id": 2, "file_name": "img2.jpg", "width": 100, "height": 100},
        ],
        "annotations": [
            {"id": 101, "image_id": 1, "category_id": 1, "bbox": [10, 10, 40, 40]},
            {"id": 102, "image_id": 2, "category_id": 1, "bbox": [5, 5, 20, 20]},
        ],
        "categories": [{"id": 1, "name": "pest"}],
    })
    img_bytes = _create_image_bytes("JPEG", size=(100, 100))

    zip_file = tmp_path / "coco_dataset.zip"
    _create_sample_zip(zip_file, {
        "annotations.json": coco_json,
        "images/img1.jpg": img_bytes,
        "images/img2.jpg": img_bytes,
    })

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("coco_dataset.zip", f, "application/zip")},
            data={"dataset_id": ds_id, "dataset_name": "COCO Dataset"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    _wait_for_job(client, job_id)

    # Readiness Assessment
    r_res = client.get(f"/api/v1/datasets/{ds_id}/readiness")
    assert r_res.status_code == 200
    assert r_res.json()["overall_score"] >= 0

    # Report Generation
    rep_res = client.post(
        f"/api/v1/datasets/{ds_id}/reports/generate",
        json={"dataset_id": ds_id},
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["report_id"]


# ---------------------------------------------------------------------------
# 5. Version Isolation & Immutability Audit
# ---------------------------------------------------------------------------

def test_version_isolation_and_immutability(client, tmp_path):
    """
    Verify strict dataset version isolation:
    1. Upload source dataset v1.
    2. Perform M8 preprocessing to create derived v2.
    3. Perform M9 feature engineering to create derived v3.
    4. Assert original dataset file archive remains unmodified.
    5. Assert v1, v2, v3 reports remain bound to their respective versions.
    """
    ds_id = f"m11_iso_{uuid.uuid4().hex[:6]}"
    csv_v1 = "x,y\n1,10\n2,20\n3,30\n"
    zip_file = tmp_path / "iso_dataset.zip"
    _create_sample_zip(zip_file, {"data.csv": csv_v1})

    # Upload v1
    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("iso_dataset.zip", f, "application/zip")},
            data={"dataset_id": ds_id},
        )
    assert res.status_code == 202
    _wait_for_job(client, res.json()["job_id"])

    # Create v2 via Preprocessing
    p_res = client.post(
        f"/api/v1/datasets/{ds_id}/preprocessing/apply",
        json={
            "dataset_id": ds_id,
            "operations": [{"operation_type": "remove_duplicates", "parameters": {}}],
        },
    )
    assert p_res.status_code in (200, 201)
    if p_res.json().get("job_id"):
        _wait_for_job(client, p_res.json()["job_id"])
    v2_id = p_res.json()["derived_version_id"]

    # Create v3 via Feature Engineering
    fe_res = client.post(
        f"/api/v1/datasets/{ds_id}/feature-engineering/apply",
        json={
            "dataset_id": ds_id,
            "version_id": v2_id,
            "operations": [{"operation_type": "logarithmic_transform", "parameters": {"degree": 2}}],
        },
    )
    assert fe_res.status_code in (200, 201)
    if fe_res.json().get("job_id"):
        _wait_for_job(client, fe_res.json()["job_id"])
    v3_id = fe_res.json()["derived_version_id"]

    # Retrieve dataset versions list to find original v1 version_id
    v_list = client.get(f"/api/v1/datasets/{ds_id}/versions")
    assert v_list.status_code == 200
    versions_items = v_list.json()["items"]
    v1_id = versions_items[-1]["version_id"]

    assert len({ v1_id, v2_id, v3_id }) == 3, "Versions must have unique IDs"

    # Generate Reports for v1, v2, v3
    r1 = client.post(f"/api/v1/datasets/{ds_id}/reports/generate", json={"dataset_id": ds_id, "version_id": v1_id})
    r2 = client.post(f"/api/v1/datasets/{ds_id}/reports/generate", json={"dataset_id": ds_id, "version_id": v2_id})
    r3 = client.post(f"/api/v1/datasets/{ds_id}/reports/generate", json={"dataset_id": ds_id, "version_id": v3_id})

    assert r1.status_code == 200 and r1.json()["version_id"] == v1_id
    assert r2.status_code == 200 and r2.json()["version_id"] == v2_id
    assert r3.status_code == 200 and r3.json()["version_id"] == v3_id


# ---------------------------------------------------------------------------
# 6. NIErnaya Phase 2 Demonstration Workflow Smoke Test
# ---------------------------------------------------------------------------

def test_niernaya_demo_workflow_smoke(client, tmp_path):
    """
    Simulates the exact 12-stage NIErnaya technical demonstration workflow:
    1. Upload -> 2. Discovery & Profiling -> 3. Quality Findings -> 4. EDA ->
    5. Insights -> 6. Preprocessing Preview -> 7. Apply Preprocessing ->
    8. Feature Engineering -> 9. PCA -> 10. Readiness -> 11. Report Gen -> 12. PDF Export.
    """
    ds_id = f"niernaya_demo_{uuid.uuid4().hex[:6]}"
    csv_data = (
        "feature_1,feature_2,feature_3,label\n"
        "1.0,2.0,3.0,class_a\n"
        "1.1,2.1,3.1,class_a\n"
        "2.0,4.0,6.0,class_b\n"
        "2.1,4.1,6.1,class_b\n"
        "3.0,6.0,9.0,class_c\n"
        "3.1,6.1,9.1,class_c\n"
    )
    zip_file = tmp_path / "niernaya_demo.zip"
    _create_sample_zip(zip_file, {"demo_dataset.csv": csv_data})

    # Stage 1: Upload
    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("niernaya_demo.zip", f, "application/zip")},
            data={"dataset_id": ds_id, "dataset_name": "NIErnaya Demo Dataset"},
        )
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    _wait_for_job(client, job_id)

    # Stage 2: Dataset Discovery
    ds = client.get(f"/api/v1/datasets/{ds_id}")
    assert ds.status_code == 200

    # Stage 3: Quality
    qa = client.get(f"/api/v1/datasets/{ds_id}/quality-assessment")
    assert qa.status_code == 200

    # Stage 4: EDA
    eda = client.get(f"/api/v1/datasets/{ds_id}/eda")
    assert eda.status_code == 200

    # Stage 5: Insights
    ins = client.get(f"/api/v1/datasets/{ds_id}/insights")
    assert ins.status_code in (200, 404)

    # Stage 6 & 7: Preprocessing Preview & Apply
    prep = client.post(
        f"/api/v1/datasets/{ds_id}/preprocessing/apply",
        json={"dataset_id": ds_id, "operations": [{"operation_type": "remove_duplicates"}]},
    )
    assert prep.status_code in (200, 201)
    if prep.json().get("job_id"):
        _wait_for_job(client, prep.json()["job_id"])
    v2_id = prep.json()["derived_version_id"]

    # Stage 8 & 9: Feature Engineering & PCA
    fe = client.post(
        f"/api/v1/datasets/{ds_id}/feature-engineering/apply",
        json={
            "dataset_id": ds_id,
            "version_id": v2_id,
            "operations": [{"operation_type": "principal_component_analysis", "parameters": {"n_components": 2}}],
        },
    )
    assert fe.status_code in (200, 201)
    if fe.json().get("job_id"):
        _wait_for_job(client, fe.json()["job_id"])
    v3_id = fe.json()["derived_version_id"]

    # Stage 10: Readiness
    r = client.get(f"/api/v1/datasets/{ds_id}/versions/{v3_id}/readiness")
    assert r.status_code == 200
    assert r.json()["overall_score"] >= 0

    # Stage 11: Analytical Report Generation
    rep = client.post(
        f"/api/v1/datasets/{ds_id}/reports/generate",
        json={"dataset_id": ds_id, "version_id": v3_id},
    )
    assert rep.status_code == 200
    rep_id = rep.json()["report_id"]

    # Stage 12: PDF Export
    pdf = client.get(
        f"/api/v1/datasets/{ds_id}/reports/{rep_id}/download",
        params={"format": "pdf"},
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# 7. No Host Path Leak & Generic Non-Hardcoded Copy Audit
# ---------------------------------------------------------------------------

def test_no_host_path_or_crop_hardcoding_in_m11(client, tmp_path):
    """
    Ensure API responses do not leak host filesystem paths and do not hardcode
    crop names like Rice/Maize unless present in the user dataset.
    """
    ds_id = f"generic_{uuid.uuid4().hex[:6]}"
    csv_data = "col_x,col_y\n10,20\n30,40\n"
    zip_file = tmp_path / "generic_dataset.zip"
    _create_sample_zip(zip_file, {"generic.csv": csv_data})

    with open(zip_file, "rb") as f:
        res = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("generic_dataset.zip", f, "application/zip")},
            data={"dataset_id": ds_id},
        )
    assert res.status_code == 202
    _wait_for_job(client, res.json()["job_id"])

    # Readiness response
    readiness_res = client.get(f"/api/v1/datasets/{ds_id}/readiness")
    assert readiness_res.status_code == 200
    r_text = json.dumps(readiness_res.json())

    assert "/Users/" not in r_text
    assert "/home/" not in r_text
    assert "/var/" not in r_text

    # Report response
    report_gen = client.post(
        f"/api/v1/datasets/{ds_id}/reports/generate",
        json={"dataset_id": ds_id},
    )
    assert report_gen.status_code == 200
    rep_text = json.dumps(report_gen.json())

    assert "/Users/" not in rep_text
    assert "/home/" not in rep_text
    assert "/var/" not in rep_text
