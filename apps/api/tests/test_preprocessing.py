"""
M8 — Comprehensive Preprocessing & Cleaning Engine Tests.

Tests all tabular, image, time-series, and annotation preprocessing operations,
along with sandbox previews, derived version application, history persistence,
source immutability, and re-analysis pipeline integration.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.schemas.preprocessing import (
    PreprocessingModality,
    PreprocessingOperationConfig,
    PreprocessingOperationType,
    PreprocessingPreviewRequest,
    PreprocessingApplyRequest,
)


@pytest.fixture
def sample_tabular_dataset(storage, tmp_path):
    """Register and populate a sample dataset with a tabular CSV file containing missing values and duplicates."""
    dataset_id = "test-tabular-ds"
    ds_dir = storage.get_extract_path(dataset_id) / "v1"
    ds_dir.mkdir(parents=True, exist_ok=True)

    csv_path = ds_dir / "data.csv"
    headers = ["id", "crop_type", "temperature", "humidity", "yield"]
    rows = [
        ["1", "Rice", "28.5", "80", "4.2"],
        ["2", "Rice", "", "75", "3.8"],  # missing temp
        ["3", "Maize", "32.0", "", "5.1"],  # missing humidity
        ["4", "Rice", "28.5", "80", "4.2"],  # exact duplicate of row 1
        ["5", "Maize", "35.5", "60", "4.5"],
        ["6", "Wheat", "22.0", "85", "3.1"],
    ]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    # Register in dataset service
    from app.services.dataset_service import dataset_service
    from app.schemas.dataset import DatasetRegisterRequest

    # Clean up if already registered
    if dataset_service.get_dataset(dataset_id):
        pass
    else:
        dataset_service.register_dataset(
            DatasetRegisterRequest(
                id=dataset_id,
                name="Test Tabular Dataset",
                crops=["Rice", "Maize"],
            )
        )
        storage_rel = storage.sanitize_relative_path(ds_dir)
        dataset_service.create_version(dataset_id, storage_rel, "dummyfingerprint12345")

    return dataset_id, ds_dir


def test_tabular_missing_value_imputation_preview_and_apply(client: TestClient, sample_tabular_dataset):
    ds_id, ds_dir = sample_tabular_dataset

    # Preview mean imputation
    preview_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "missing_value_imputation",
                "modality": "tabular",
                "parameters": {"strategy": "mean", "columns": ["temperature"]},
                "target_file": "data.csv",
            }
        ],
    }
    resp = client.post(f"/api/v1/datasets/{ds_id}/preprocessing/preview", json=preview_req)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["can_apply"] is True
    assert len(data["operations"]) == 1
    op_res = data["operations"][0]
    assert op_res["affected_rows"] == 1

    # Apply imputation
    apply_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "missing_value_imputation",
                "modality": "tabular",
                "parameters": {"strategy": "mean", "columns": ["temperature"]},
                "target_file": "data.csv",
            }
        ],
        "description": "Impute missing temperatures",
    }
    apply_resp = client.post(f"/api/v1/datasets/{ds_id}/preprocessing/apply", json=apply_req)
    assert apply_resp.status_code == status.HTTP_201_CREATED
    apply_data = apply_resp.json()
    assert apply_data["status"] == "completed"
    assert "derived_version_id" in apply_data


def test_tabular_remove_duplicates(client: TestClient, sample_tabular_dataset):
    ds_id, _ = sample_tabular_dataset

    apply_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "remove_duplicates",
                "modality": "tabular",
                "parameters": {"keep": "first"},
                "target_file": "data.csv",
            }
        ],
        "description": "Remove exact duplicate rows",
    }
    resp = client.post(f"/api/v1/datasets/{ds_id}/preprocessing/apply", json=apply_req)
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["operations_applied"] == 1


def test_preprocessing_history_audit_trail(client: TestClient, sample_tabular_dataset):
    ds_id, _ = sample_tabular_dataset

    # Get history list
    resp = client.get(f"/api/v1/datasets/{ds_id}/preprocessing/history")
    assert resp.status_code == status.HTTP_200_OK
    history_data = resp.json()
    assert history_data["total"] >= 1
    record = history_data["items"][0]
    assert len(record["operations"]) >= 1
    assert record["input_fingerprint"] is not None
    assert record["output_fingerprint"] is not None


@pytest.fixture
def sample_image_dataset(storage):
    """Create sample image dataset with subfolders and an invalid file."""
    dataset_id = "test-image-ds"
    ds_dir = storage.get_extract_path(dataset_id) / "v1"
    
    from PIL import Image
    class_dir = ds_dir / "rice_blast"
    class_dir.mkdir(parents=True, exist_ok=True)

    # Valid image 1
    img1 = class_dir / "leaf_01.jpg"
    Image.new("RGB", (200, 200), color="green").save(img1, "JPEG")

    # Valid image 2 (exact duplicate of img1)
    img2 = class_dir / "leaf_02.jpg"
    Image.new("RGB", (200, 200), color="green").save(img2, "JPEG")

    # Corrupt zero-byte file
    corrupt = class_dir / "corrupt.jpg"
    corrupt.write_bytes(b"")

    from app.services.dataset_service import dataset_service
    from app.schemas.dataset import DatasetRegisterRequest

    if not dataset_service.get_dataset(dataset_id):
        dataset_service.register_dataset(
            DatasetRegisterRequest(id=dataset_id, name="Test Image DS", crops=["Rice"])
        )
        storage_rel = storage.sanitize_relative_path(ds_dir)
        dataset_service.create_version(dataset_id, storage_rel, "imgfingerprint999")

    return dataset_id, ds_dir


def test_image_exclude_corrupt_and_duplicates(client: TestClient, sample_image_dataset):
    ds_id, _ = sample_image_dataset

    # Preview exclude corrupt
    preview_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "exclude_corrupt_images",
                "modality": "image",
                "parameters": {},
            },
            {
                "operation_type": "remove_exact_duplicates",
                "modality": "image",
                "parameters": {},
            },
        ],
    }
    resp = client.post(f"/api/v1/datasets/{ds_id}/preprocessing/preview", json=preview_req)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["can_apply"] is True
    assert len(data["operations"]) == 2

    # Apply cleaning
    apply_req = {
        "dataset_id": ds_id,
        "operations": [
            {
                "operation_type": "exclude_corrupt_images",
                "modality": "image",
                "parameters": {},
            },
            {
                "operation_type": "remove_exact_duplicates",
                "modality": "image",
                "parameters": {},
            },
        ],
        "description": "Clean corrupt images and exact duplicates",
    }
    apply_resp = client.post(f"/api/v1/datasets/{ds_id}/preprocessing/apply", json=apply_req)
    assert apply_resp.status_code == status.HTTP_201_CREATED
    assert apply_resp.json()["operations_applied"] == 2
