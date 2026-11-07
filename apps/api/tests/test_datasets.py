from pathlib import Path
from fastapi import status
from fastapi.testclient import TestClient


def test_list_datasets(client):
    response = client.get("/api/v1/datasets")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)

    # Check primary ICAR dataset presence
    icar = next((d for d in data["items"] if d["slug"] == "icar-rice-maize"), None)
    assert icar is not None
    assert icar["name"] == "ICAR Rice and Maize Disease Dataset"
    assert "Rice" in icar["crops"]
    assert "Maize" in icar["crops"]


def test_get_dataset_by_id(client):
    response = client.get("/api/v1/datasets/icar-rice-maize")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["slug"] == "icar-rice-maize"
    assert data["is_curated"] is True


def test_get_dataset_not_found(client):
    response = client.get("/api/v1/datasets/non-existent-dataset-xyz")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "DATASET_NOT_FOUND"
    assert "detail" in data


def test_discover_dataset_unknown_id(client):
    response = client.post("/api/v1/datasets/unknown-ds-999/discover")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "DATASET_NOT_FOUND"


def test_discover_dataset_missing_directory(client):
    # paddy-doctor does not exist in the temporary storage
    response = client.post("/api/v1/datasets/paddy-doctor/discover")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "DATASET_DIRECTORY_NOT_FOUND"
    # Verify no host absolute path is leaked
    assert "/Users/" not in data["detail"]
    assert "curated/paddy-doctor" in data["detail"]


def test_discover_dataset_successful(client, temp_storage_dir):
    # Populate a synthetic dataset under curated/icar-rice-maize in temp storage
    icar_dir = temp_storage_dir / "curated" / "icar-rice-maize"
    blight_dir = icar_dir / "Rice" / "Bacterial_blight"
    blight_dir.mkdir(parents=True, exist_ok=True)
    (blight_dir / "sample_1.jpg").write_bytes(b"\xff\xd8\xffdummy")
    (blight_dir / "sample_2.PNG").write_bytes(b"\x89PNGdummy")

    response = client.post("/api/v1/datasets/icar-rice-maize/discover")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["dataset_id"] == "icar-rice-maize"
    assert data["discovery_status"] == "discovered"
    assert data["discovered_image_files"] == 2
    assert data["discovered_class_directories"] == 1
    assert set(data["supported_extensions_encountered"]) == {".jpg", ".png"}
    assert data["validated_image_files"] is None  # Must remain null in M2.1
    assert data["dataset_root_relative_path"] == "curated/icar-rice-maize"
    assert "/Users/" not in data["dataset_root_relative_path"]

    # Verify that dataset metadata reflects discovery
    ds_resp = client.get("/api/v1/datasets/icar-rice-maize")
    assert ds_resp.status_code == status.HTTP_200_OK
    ds_data = ds_resp.json()
    assert ds_data["status"] == "discovered"
    assert ds_data["total_images"] == 2
    assert ds_data["total_classes"] == 1

    # Verify discovery can be fetched via GET /datasets/{id}/discovery
    disc_resp = client.get("/api/v1/datasets/icar-rice-maize/discovery")
    assert disc_resp.status_code == status.HTTP_200_OK
    assert disc_resp.json()["discovered_image_files"] == 2


def test_validate_dataset_unknown_id(client):
    response = client.post("/api/v1/datasets/unknown-ds-404/validate")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "DATASET_NOT_FOUND"


def test_validate_dataset_before_discovery_returns_error(client):
    # mendeley-rice has not been discovered yet
    response = client.post("/api/v1/datasets/mendeley-rice/validate")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["error_code"] == "DATASET_NOT_DISCOVERED"


def test_validate_dataset_successful_and_retrieval(client, temp_storage_dir):
    from PIL import Image

    icar_dir = temp_storage_dir / "curated" / "icar-rice-maize"
    leaf_dir = icar_dir / "Rice" / "ValidTest"
    leaf_dir.mkdir(parents=True, exist_ok=True)

    # Write 2 valid images and 1 corrupt image
    Image.new("RGB", (160, 120), color="green").save(leaf_dir / "leaf_01.jpg", "JPEG")
    Image.new("RGB", (100, 100), color="yellow").save(leaf_dir / "leaf_02.png", "PNG")
    (leaf_dir / "leaf_corrupt.jpg").write_bytes(b"CORRUPT_NOT_IMAGE")

    # 1. Discover first
    disc_resp = client.post("/api/v1/datasets/icar-rice-maize/discover")
    assert disc_resp.status_code == status.HTTP_200_OK

    # 2. Trigger validation
    val_resp = client.post("/api/v1/datasets/icar-rice-maize/validate")
    assert val_resp.status_code == status.HTTP_200_OK
    val_data = val_resp.json()

    assert val_data["dataset_id"] == "icar-rice-maize"
    assert val_data["validation_status"] == "validated"
    assert val_data["total_validated_images"] >= 2
    assert val_data["total_corrupted_images"] >= 1
    assert len(val_data["corrupted_files"]) >= 1

    # Verify no absolute paths leaked in records
    for cf in val_data["corrupted_files"]:
        assert "/Users/" not in cf["relative_path"]

    # 3. Retrieve via GET /validation
    get_val = client.get("/api/v1/datasets/icar-rice-maize/validation")
    assert get_val.status_code == status.HTTP_200_OK
    assert get_val.json()["total_validated_images"] == val_data["total_validated_images"]

    # 4. Verify dataset metadata was updated
    ds_resp = client.get("/api/v1/datasets/icar-rice-maize")
    assert ds_resp.status_code == status.HTTP_200_OK
    ds = ds_resp.json()
    assert ds["status"] == "validated"
    assert ds["validated_image_files"] == val_data["total_validated_images"]
    assert ds["corrupted_image_files"] == val_data["total_corrupted_images"]


def test_detect_duplicates_unknown_id(client: TestClient):
    response = client.post("/api/v1/datasets/non-existent-dataset/duplicates/detect")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "DATASET_NOT_FOUND"


def test_detect_duplicates_before_validation_returns_error(client: TestClient):
    # 'paddy-doctor' has not been validated
    response = client.post("/api/v1/datasets/paddy-doctor/duplicates/detect")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error_code"] == "DATASET_NOT_VALIDATED"


def test_get_duplicates_before_detection_returns_404(client: TestClient):
    response = client.get("/api/v1/datasets/paddy-doctor/duplicates")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "DUPLICATE_ANALYSIS_NOT_FOUND"


def test_detect_duplicates_successful_and_retrieval(client: TestClient, temp_storage_dir: Path):
    """End-to-end test for discovery -> validation -> duplicate detection -> retrieval."""
    from PIL import Image

    curated_dir = temp_storage_dir / "curated" / "icar-rice-maize"
    blast_dir = curated_dir / "Rice" / "blast_dup"
    blast_dir.mkdir(parents=True, exist_ok=True)

    # Create two identical JPEG images and one distinct JPEG image
    img1 = Image.new("RGB", (64, 64), color="blue")
    img1.save(blast_dir / "img1.jpg", "JPEG")
    # Exact byte duplicate of img1
    (blast_dir / "img2.jpg").write_bytes((blast_dir / "img1.jpg").read_bytes())
    # Distinct image
    Image.new("RGB", (64, 64), color="red").save(blast_dir / "img3.jpg", "JPEG")

    # 1. Discover
    disc_resp = client.post("/api/v1/datasets/icar-rice-maize/discover")
    assert disc_resp.status_code == status.HTTP_200_OK

    # 2. Validate
    val_resp = client.post("/api/v1/datasets/icar-rice-maize/validate")
    assert val_resp.status_code == status.HTTP_200_OK
    val_data = val_resp.json()
    assert val_data["total_validated_images"] >= 3

    # 3. Detect duplicates
    dup_resp = client.post("/api/v1/datasets/icar-rice-maize/duplicates/detect")
    assert dup_resp.status_code == status.HTTP_200_OK
    dup_data = dup_resp.json()

    assert dup_data["dataset_id"] == "icar-rice-maize"
    assert dup_data["total_eligible_images"] >= 3
    assert dup_data["successfully_hashed_images"] >= 3
    assert dup_data["exact_duplicate_groups"] >= 1
    assert dup_data["duplicate_instances_count"] >= 1
    assert dup_data["images_in_duplicate_groups"] >= 2
    assert dup_data["duplicate_percentage"] > 0.0

    # Group assertions
    group = next(g for g in dup_data["groups"] if "Rice/blast_dup/img1.jpg" in [g["representative"]["relative_path"], *[d["relative_path"] for d in g["duplicates"]]])
    assert group["representative"]["relative_path"] == "Rice/blast_dup/img1.jpg"
    assert group["duplicates"][0]["relative_path"] == "Rice/blast_dup/img2.jpg"
    assert group["is_cross_class"] is False

    # 4. Retrieve via GET /duplicates
    get_dup = client.get("/api/v1/datasets/icar-rice-maize/duplicates")
    assert get_dup.status_code == status.HTTP_200_OK
    assert get_dup.json()["exact_duplicate_groups"] == dup_data["exact_duplicate_groups"]

    # 5. Dataset metadata should reflect duplicate count
    ds_resp = client.get("/api/v1/datasets/icar-rice-maize")
    assert ds_resp.status_code == status.HTTP_200_OK
    ds = ds_resp.json()
    assert ds["duplicate_groups_count"] == dup_data["exact_duplicate_groups"]


