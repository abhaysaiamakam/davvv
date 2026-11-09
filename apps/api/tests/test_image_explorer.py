import base64
import io
import json
import time
import uuid
import zipfile
import pytest

from PIL import Image

from app.schemas.preprocessing import PreprocessingOperationConfig, PreprocessingOperationType
from app.services.image_explorer_service import ImageExplorerService, image_explorer_service
from app.services.dataset_service import dataset_service
from app.storage.local import storage_backend


def _make_image(path, size=(64, 32), color=(20, 140, 60)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_image_listing_is_paged_class_aware_and_does_not_return_paths(tmp_path):
    _make_image(tmp_path / "healthy" / "one.png")
    _make_image(tmp_path / "healthy" / "two.png")
    _make_image(tmp_path / "diseased" / "three.png")
    service = ImageExplorerService()
    service._version_root = lambda dataset_id, version_id: tmp_path

    result = service.list_images("dataset-a", "version-a", page=2, page_size=2)

    assert result.total == 3
    assert [item.image_count for item in result.classes] == [1, 2]
    assert len(result.items) == 1
    assert result.items[0].image_id
    assert result.items[0].width == 64
    assert result.items[0].height == 32
    assert "relative_path" not in result.items[0].model_dump()
    assert str(tmp_path) not in result.model_dump_json()


def test_image_listing_filters_crop_using_version_relative_class_hierarchy(tmp_path, monkeypatch):
    _make_image(tmp_path / "Rice" / "Disease" / "Brown_spot" / "rice.jpg")
    _make_image(tmp_path / "Maize" / "Disease" / "Leaf_blight" / "maize.jpg")
    service = ImageExplorerService()
    monkeypatch.setattr(service, "_version_root", lambda dataset_id, version_id: tmp_path)

    rice = service.list_images("dataset-a", "version-a", page_size=10, crop="Rice")

    assert rice.total == 1
    assert rice.items[0].filename == "rice.jpg"
    assert rice.items[0].class_name == "Rice/Disease/Brown_spot"


def test_image_id_lookup_is_bound_to_files_inside_version(tmp_path):
    _make_image(tmp_path / "class-a" / "image.png")
    service = ImageExplorerService()
    record = service._records(tmp_path)[0]
    image_id = service._id(record[0])

    assert service._resolve_image(tmp_path, image_id)[3] == record[3]
    assert service._resolve_image(tmp_path, "../" + image_id) is None
    assert service._resolve_image(tmp_path, "0" * 32) is None


def test_image_listing_reports_multiple_formats_and_corrupt_files(tmp_path, monkeypatch):
    _make_image(tmp_path / "healthy" / "leaf.png")
    jpg = tmp_path / "diseased" / "leaf.jpg"
    jpg.parent.mkdir(parents=True)
    Image.new("RGB", (20, 10), (100, 40, 30)).save(jpg, "JPEG")
    corrupt = tmp_path / "diseased" / "broken.png"
    corrupt.write_bytes(b"not an image")
    service = ImageExplorerService()
    monkeypatch.setattr(service, "_version_root", lambda dataset_id, version_id: tmp_path)

    result = service.list_images("dataset-a", "version-a", page_size=10)

    assert result.total == 3
    assert {item.format for item in result.items if item.status == "valid"} == {"PNG", "JPEG"}
    assert sum(item.status == "corrupt" for item in result.items) == 1


def test_coco_annotations_use_source_labels_boxes_and_optional_confidence(tmp_path, monkeypatch):
    _make_image(tmp_path / "images" / "leaf.png", size=(100, 50))
    _make_image(tmp_path / "images" / "other.png", size=(80, 40))
    annotation_file = tmp_path / "annotations" / "instances.json"
    annotation_file.parent.mkdir()
    annotation_file.write_text(json.dumps({
        "images": [{"id": 7, "file_name": "images/leaf.png", "width": 100, "height": 50}, {"id": 8, "file_name": "images/other.png", "width": 80, "height": 40}],
        "categories": [{"id": 3, "name": "Leaf spot"}, {"id": 9, "name": "Healthy leaf"}],
        "annotations": [
            {"id": 18, "image_id": 7, "category_id": 3, "bbox": [4, 5, 20, 10], "score": 0.87},
            {"id": 19, "image_id": 7, "category_id": 3, "bbox": [30, 8, 15, 12]},
        ],
    }))
    service = ImageExplorerService()
    monkeypatch.setattr(service, "_version_root", lambda dataset_id, version_id: tmp_path)
    image_id = service._id("images/leaf.png")

    result = service.get_annotations("dataset-a", "version-a", image_id)

    assert result.annotation_format == "coco"
    assert result.image_width == 100 and result.image_height == 50
    assert result.annotation_count == 2
    assert result.annotations[0].label == "Leaf spot"
    assert (result.annotations[0].x, result.annotations[0].y, result.annotations[0].width, result.annotations[0].height) == (4, 5, 20, 10)
    assert result.annotations[0].confidence == 0.87
    assert result.annotations[1].confidence is None
    assert [(row.label, row.annotation_count, row.image_count) for row in result.classes] == [("Leaf spot", 2, 1), ("Healthy leaf", 0, 0)]
    filtered = service.list_images("dataset-a", "version-a", annotation_class_id="3")
    assert filtered.total == 1 and filtered.items[0].filename == "leaf.png"
    with pytest.raises(ValueError, match="annotation-linked"):
        service.preview_preprocessing(
            "dataset-a", "version-a", image_id,
            PreprocessingOperationConfig(operation_type=PreprocessingOperationType.RESIZE_IMAGES, parameters={"max_dim": 16}),
        )


def test_yolo_annotations_map_real_class_names_and_only_existing_confidence(tmp_path, monkeypatch):
    _make_image(tmp_path / "images" / "train" / "leaf.jpg", size=(100, 50))
    labels = tmp_path / "labels" / "train" / "leaf.txt"
    labels.parent.mkdir(parents=True)
    labels.write_text("1 0.5 0.5 0.4 0.2 0.91\n0 0.25 0.2 0.1 0.2\n")
    (tmp_path / "data.yaml").write_text("names:\n  - healthy\n  - rust\n")
    service = ImageExplorerService()
    monkeypatch.setattr(service, "_version_root", lambda dataset_id, version_id: tmp_path)
    image_id = service._id("images/train/leaf.jpg")

    result = service.get_annotations("dataset-a", "version-a", image_id)

    assert result.annotation_format == "yolo"
    assert result.annotation_count == 2
    rust = next(item for item in result.annotations if item.class_id == "1")
    assert rust.label == "rust"
    assert (rust.x, rust.y, rust.width, rust.height) == (30, 20, 40, 10)
    assert rust.confidence == 0.91
    healthy = next(item for item in result.annotations if item.class_id == "0")
    assert healthy.label == "healthy" and healthy.confidence is None


def test_annotation_api_returns_coco_evidence_for_versioned_image(client, tmp_path, monkeypatch):
    _make_image(tmp_path / "images" / "leaf.png", size=(40, 20))
    annotations = tmp_path / "instances.json"
    annotations.write_text(json.dumps({
        "images": [{"id": 11, "file_name": "images/leaf.png"}],
        "categories": [{"id": 4, "name": "Actual label"}],
        "annotations": [{"id": 12, "image_id": 11, "category_id": 4, "bbox": [2, 3, 9, 7]}],
    }))
    monkeypatch.setattr(image_explorer_service, "_version_root", lambda dataset_id, version_id: tmp_path)
    image_id = image_explorer_service._id("images/leaf.png")

    response = client.get(f"/api/v1/datasets/uploaded/versions/version-1/images/{image_id}/annotations")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["annotation_format"] == "coco"
    assert result["annotations"][0]["label"] == "Actual label"
    assert result["annotations"][0]["x"] == 2
    assert result["annotations"][0]["confidence"] is None


def test_preprocessing_preview_runs_real_operation_in_isolated_copy(tmp_path, monkeypatch):
    source = tmp_path / "class-a" / "image.png"
    _make_image(source)
    service = ImageExplorerService()
    monkeypatch.setattr(service, "_version_root", lambda dataset_id, version_id: tmp_path)
    image_id = service._id("class-a/image.png")
    config = PreprocessingOperationConfig(
        operation_type=PreprocessingOperationType.RESIZE_IMAGES,
        parameters={"max_dim": 16},
    )

    result = service.preview_preprocessing("dataset-a", "version-a", image_id, config)

    assert result.original_metadata["width"] == 64
    assert result.preview_metadata["width"] == 16
    assert result.preview_metadata["height"] == 8
    assert result.original_data_url.startswith("data:image/jpeg;base64,")
    assert result.preview_data_url.startswith("data:image/jpeg;base64,")
    with Image.open(source) as original:
        assert original.size == (64, 32)
    preview_bytes = base64.b64decode(result.preview_data_url.split(",", 1)[1])
    with Image.open(io.BytesIO(preview_bytes)) as preview:
        assert preview.size == (16, 8)


def test_image_explorer_api_versioned_upload_gallery_preview_and_derived_copy(client):
    dataset_id = f"image-explorer-{uuid.uuid4().hex[:8]}"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for relative in ("train/healthy/leaf.png", "train/diseased/leaf.png"):
            payload = io.BytesIO()
            Image.new("RGB", (64, 32), (25, 120, 60)).save(payload, "PNG")
            bundle.writestr(relative, payload.getvalue())
    archive.seek(0)

    uploaded = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("image-data.zip", archive, "application/zip")},
        data={"dataset_id": dataset_id, "name": "Image Explorer API test"},
    )
    assert uploaded.status_code == 202, uploaded.text
    upload_info = uploaded.json()
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{upload_info['job_id']}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.03)
    assert job["status"] == "completed", job

    version_id = upload_info["version_id"]
    base = f"/api/v1/datasets/{dataset_id}/versions/{version_id}/images"
    gallery = client.get(base, params={"page": 1, "page_size": 1})
    assert gallery.status_code == 200, gallery.text
    data = gallery.json()
    assert data["modality"] == "image"
    assert data["class_structure"] == "directory"
    assert data["total"] == 2
    assert {item["class_name"] for item in data["classes"]} == {"healthy", "diseased"}
    assert len(data["items"]) == 1
    image = data["items"][0]
    assert image["width"] == 64 and image["height"] == 32
    assert "relative_path" not in image
    assert "image_path" not in str(gallery.request.url)

    image_base = f"{base}/{image['image_id']}"
    annotations = client.get(f"{image_base}/annotations")
    assert annotations.status_code == 200 and annotations.json()["annotation_format"] == "none"
    metadata = client.get(image_base)
    assert metadata.status_code == 200
    assert metadata.json()["image_id"] == image["image_id"]
    assert metadata.json()["width"] == 64 and metadata.json()["height"] == 32
    thumbnail = client.get(f"{image_base}/thumbnail")
    full_image = client.get(f"{image_base}/preview")
    assert thumbnail.status_code == 200 and thumbnail.headers["content-type"] == "image/jpeg"
    assert full_image.status_code == 200 and full_image.headers["content-type"] == "image/png"

    before = client.post(
        f"{image_base}/preprocessing-preview",
        json={"operation": {"operation_type": "resize_images", "parameters": {"max_dim": 16}}},
    )
    assert before.status_code == 200, before.text
    preview = before.json()
    assert preview["original_metadata"]["width"] == 64
    assert preview["preview_metadata"]["width"] == 16

    applied = client.post(
        f"/api/v1/datasets/{dataset_id}/preprocessing/apply",
        json={
            "dataset_id": dataset_id,
            "version_id": version_id,
            "operations": [{"operation_type": "resize_images", "parameters": {"max_dim": 16}}],
        },
    )
    assert applied.status_code == 201, applied.text
    derived_id = applied.json()["derived_version_id"]
    source_version = dataset_service.get_version(dataset_id, version_id)
    source_file = storage_backend.base_dir / source_version.storage_relative_path / "train" / image["class_name"] / image["filename"]
    with Image.open(source_file) as original:
        assert original.size == (64, 32)

    derived_gallery = client.get(f"/api/v1/datasets/{dataset_id}/versions/{derived_id}/images")
    assert derived_gallery.status_code == 200, derived_gallery.text
    assert all(item["width"] == 16 and item["height"] == 8 for item in derived_gallery.json()["items"])
    for _ in range(100):
        derived_job = client.get(f"/api/v1/jobs/{applied.json()['job_id']}").json()
        if derived_job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.03)
    assert derived_job["status"] == "completed", derived_job

    invalid = client.get(f"{base}/../thumbnail")
    assert invalid.status_code == 404
