"""
M9 — Comprehensive Feature Engineering & Selection Tests.

Tests mathematical transformations, feature selection (variance threshold, correlation matrix),
PCA dimensionality reduction, sandbox previews, derived version application, history audit trails,
and pipeline re-analysis integration.
"""
from __future__ import annotations

import csv
import hashlib
import time
from pathlib import Path
import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture
def sample_tabular_fe_dataset(storage):
    dataset_id = "test-fe-ds"
    ds_dir = storage.get_extract_path(dataset_id) / "v1"
    ds_dir.mkdir(parents=True, exist_ok=True)

    csv_path = ds_dir / "features_data.csv"
    headers = ["id", "val_a", "val_b", "val_c", "date_col"]
    rows = [
        ["1", "10.5", "20.1", "5.0", "2026-01-15"],
        ["2", "15.0", "30.2", "5.1", "2026-02-20"],
        ["3", "20.5", "40.5", "5.2", "2026-03-10"],
        ["4", "25.0", "50.0", "5.0", "2026-04-05"],
        ["5", "30.0", "60.1", "5.3", "2026-05-12"],
    ]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    from app.services.dataset_service import dataset_service
    from app.schemas.dataset import DatasetRegisterRequest

    if not dataset_service.get_dataset(dataset_id):
        dataset_service.register_dataset(
            DatasetRegisterRequest(id=dataset_id, name="Test FE Dataset", crops=["Maize"])
        )
        storage_rel = storage.sanitize_relative_path(ds_dir)
        dataset_service.create_version(dataset_id, storage_rel, "fefingerprint123")

    return dataset_id, ds_dir


def test_get_available_features(client: TestClient, sample_tabular_fe_dataset):
    ds_id, _ = sample_tabular_fe_dataset
    resp = client.get(f"/api/v1/datasets/{ds_id}/feature-engineering/features")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "current_features" in data
    assert "operations" in data
    assert len(data["current_features"]) == 5


def test_mathematical_transform_preview_and_apply(client: TestClient, sample_tabular_fe_dataset):
    ds_id, source_dir = sample_tabular_fe_dataset
    original_hash = hashlib.sha256((source_dir / "features_data.csv").read_bytes()).hexdigest()

    preview_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "logarithmic_transform",
                "modality": "tabular",
                "parameters": {"transform": "log1p", "columns": ["val_a"]},
                "target_file": "features_data.csv",
            }
        ],
    }
    resp = client.post(f"/api/v1/datasets/{ds_id}/feature-engineering/preview", json=preview_req)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["can_apply"] is True
    assert "val_a_log1p" in data["operations"][0]["generated_features"]

    apply_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "logarithmic_transform",
                "modality": "tabular",
                "parameters": {"transform": "log1p", "columns": ["val_a"]},
                "target_file": "features_data.csv",
            }
        ],
        "description": "Apply log1p transform to val_a",
    }
    apply_resp = client.post(f"/api/v1/datasets/{ds_id}/feature-engineering/apply", json=apply_req)
    assert apply_resp.status_code == status.HTTP_201_CREATED
    apply_data = apply_resp.json()
    assert apply_data["status"] == "completed"
    assert apply_data["new_features_count"] == 1
    assert apply_data["derived_version_id"]
    assert apply_data["job_id"]
    job_resp = client.get(f"/api/v1/jobs/{apply_data['job_id']}")
    assert job_resp.status_code == status.HTTP_200_OK
    assert job_resp.json()["dataset_version"] == apply_data["derived_version_id"]
    deadline = time.monotonic() + 5
    while job_resp.json()["status"] not in ("completed", "failed") and time.monotonic() < deadline:
        time.sleep(0.02)
        job_resp = client.get(f"/api/v1/jobs/{apply_data['job_id']}")
    assert job_resp.json()["status"] == "completed", job_resp.json()
    from app.services.dataset_service import dataset_service
    assert dataset_service.get_version(ds_id, apply_data["derived_version_id"]).status.value == "ready"
    assert dataset_service.get_version(ds_id, apply_data["source_version_id"]).status.value == "registered"
    from app.services.data_quality_service import data_quality_service
    from app.services.eda_service import eda_service
    assert data_quality_service.get_latest_assessment_for_dataset(ds_id, apply_data["derived_version_id"]).version_id == apply_data["derived_version_id"]
    assert eda_service.get_latest_report_for_dataset(ds_id, apply_data["derived_version_id"]).version_id == apply_data["derived_version_id"]
    assert hashlib.sha256((source_dir / "features_data.csv").read_bytes()).hexdigest() == original_hash


def test_variance_threshold_and_pca(client: TestClient, sample_tabular_fe_dataset):
    ds_id, _ = sample_tabular_fe_dataset

    apply_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "variance_threshold_selection",
                "modality": "tabular",
                "parameters": {"threshold": 0.001},
                "target_file": "features_data.csv",
            },
            {
                "operation_type": "principal_component_analysis",
                "modality": "tabular",
                "parameters": {"n_components": 2},
                "target_file": "features_data.csv",
            },
        ],
        "description": "Variance selection followed by PCA",
    }
    resp = client.post(f"/api/v1/datasets/{ds_id}/feature-engineering/apply", json=apply_req)
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["operations_applied"] == 2


def test_feature_engineering_history(client: TestClient, sample_tabular_fe_dataset):
    ds_id, _ = sample_tabular_fe_dataset
    resp = client.get(f"/api/v1/datasets/{ds_id}/feature-engineering/history")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"][0]["operations"]) >= 1
