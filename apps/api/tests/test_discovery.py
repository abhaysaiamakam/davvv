import os
import tempfile
from pathlib import Path
import pytest

from app.core.errors import DatasetDirectoryNotFoundError
from app.schemas.dataset import DatasetMetadata, DatasetSource, DatasetStatus
from app.services.dataset_discovery_service import (
    DatasetDiscoveryService,
    dataset_discovery_service,
)
from app.storage.local import LocalStorageBackend


@pytest.fixture
def temp_dataset_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def test_discovery_valid_nested_classes(temp_dataset_dir):
    # Setup nested agricultural structure
    rice_blight = temp_dataset_dir / "Rice" / "Disease" / "01_Bacterial_blight"
    rice_healthy = temp_dataset_dir / "Rice" / "Healthy"
    maize_healthy = temp_dataset_dir / "Maize" / "Healthy"

    for d in [rice_blight, rice_healthy, maize_healthy]:
        d.mkdir(parents=True, exist_ok=True)

    # Write dummy images
    (rice_blight / "leaf_01.jpg").write_bytes(b"\xff\xd8\xffdummy_jpeg_01")
    (rice_blight / "leaf_02.jpeg").write_bytes(b"\xff\xd8\xffdummy_jpeg_02")
    (rice_healthy / "healthy_01.png").write_bytes(b"\x89PNGdummy_png")
    (maize_healthy / "corn_01.webp").write_bytes(b"RIFFdummy_webp")

    classes, total_images, extensions, unreadable, warnings = (
        dataset_discovery_service.scan_directory(temp_dataset_dir)
    )

    assert total_images == 4
    assert len(classes) == 3
    assert extensions == [".jpeg", ".jpg", ".png", ".webp"]
    assert unreadable == 0
    assert len(warnings) == 0

    # Verify deterministic alphabetical ordering
    class_names = [c.class_name for c in classes]
    assert class_names == [
        "Maize/Healthy",
        "Rice/Disease/01_Bacterial_blight",
        "Rice/Healthy",
    ]

    # Verify counts per class
    counts = {c.class_name: c.image_count for c in classes}
    assert counts["Maize/Healthy"] == 1
    assert counts["Rice/Disease/01_Bacterial_blight"] == 2
    assert counts["Rice/Healthy"] == 1


def test_discovery_case_insensitive_supported_extensions(temp_dataset_dir):
    ext_dir = temp_dataset_dir / "All_Formats"
    ext_dir.mkdir(parents=True, exist_ok=True)

    test_extensions = [
        "test.JPG",
        "test.JPEG",
        "test.PNG",
        "test.BMP",
        "test.WEBP",
        "test.TIF",
        "test.TIFF",
        "test_lower.bmp",
        "test_lower.png",
    ]
    for filename in test_extensions:
        (ext_dir / filename).write_bytes(b"image_content")

    classes, total_images, extensions, unreadable, warnings = (
        dataset_discovery_service.scan_directory(temp_dataset_dir)
    )

    assert total_images == len(test_extensions)
    assert set(extensions) == {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
    assert unreadable == 0


def test_discovery_unsupported_files_ignored(temp_dataset_dir):
    data_dir = temp_dataset_dir / "Mixed_Content"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Images
    (data_dir / "valid.jpg").write_bytes(b"image")
    (data_dir / "valid.png").write_bytes(b"image")

    # Non-images to ignore safely
    (data_dir / "dataset_manifest.csv").write_text("id,class")
    (data_dir / "corrupted.txt").write_text("notes")
    (data_dir / "audit.py").write_text("print('audit')")
    (data_dir / ".DS_Store").write_bytes(b"\x00")
    (data_dir / "README.md").write_text("# Readme")

    classes, total_images, extensions, unreadable, warnings = (
        dataset_discovery_service.scan_directory(temp_dataset_dir)
    )

    assert total_images == 2
    assert extensions == [".jpg", ".png"]
    assert len(classes) == 1
    assert classes[0].image_count == 2
    assert unreadable == 0


def test_discovery_empty_dataset_directory(temp_dataset_dir):
    classes, total_images, extensions, unreadable, warnings = (
        dataset_discovery_service.scan_directory(temp_dataset_dir)
    )

    assert total_images == 0
    assert len(classes) == 0
    assert extensions == []


def test_discovery_service_missing_directory(temp_storage_dir):
    storage = LocalStorageBackend()
    dataset = DatasetMetadata(
        id="missing-dataset",
        name="Missing Dataset",
        slug="missing-dataset",
        description="Non-existent dataset",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T00:00:00Z",
        updated_at="2026-11-07T00:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        tags=[],
    )

    with pytest.raises(DatasetDirectoryNotFoundError) as exc_info:
        dataset_discovery_service.discover_dataset(dataset, storage)

    assert "missing-dataset" in str(exc_info.value.detail)


def test_discovery_service_file_instead_of_directory(temp_dataset_dir):
    dummy_file = temp_dataset_dir / "not_a_dir.txt"
    dummy_file.write_text("I am a text file")

    storage = LocalStorageBackend()
    dataset = DatasetMetadata(
        id="file-dataset",
        name="File Dataset",
        slug="file-dataset",
        description="Target is a file",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T00:00:00Z",
        updated_at="2026-11-07T00:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        tags=[],
    )

    # Mock resolve_dataset_path to return dummy_file
    storage.resolve_dataset_path = lambda d: dummy_file
    result = dataset_discovery_service.discover_dataset(dataset, storage)

    assert result.discovery_status == DatasetStatus.INVALID
    assert result.discovered_image_files == 0
    assert any("is a file, not a directory" in w for w in result.warnings)


def test_discovery_symlink_pointing_outside_dataset_root(temp_dataset_dir):
    # Setup dataset root and an external forbidden directory
    outside_dir = temp_dataset_dir / "external_forbidden"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "escaped_image.jpg"
    outside_file.write_bytes(b"forbidden_data")

    dataset_root = temp_dataset_dir / "dataset_root"
    valid_class = dataset_root / "ValidClass"
    valid_class.mkdir(parents=True, exist_ok=True)
    (valid_class / "inside.jpg").write_bytes(b"valid_data")

    # Create a symlink pointing outside
    try:
        os.symlink(str(outside_file), str(valid_class / "symlink_escaped.jpg"))
        os.symlink(str(outside_dir), str(dataset_root / "symlink_escaped_dir"))
    except OSError:
        pytest.skip("Symlink creation not supported on this platform/filesystem")

    classes, total_images, extensions, unreadable, warnings = (
        dataset_discovery_service.scan_directory(dataset_root)
    )

    # Only the inside.jpg should be counted, escaped files/dirs must be skipped
    assert total_images == 1
    assert unreadable >= 1
    assert any("Symlink" in w and "outside" in w for w in warnings)


def test_discovery_deterministic_class_ordering(temp_dataset_dir):
    # Create classes in random/reverse alphabetical order
    for name in ["Zebra_Class", "Apple_Class", "Mango_Class", "Banana_Class"]:
        cd = temp_dataset_dir / name
        cd.mkdir(parents=True, exist_ok=True)
        (cd / "img.jpg").write_bytes(b"data")

    classes, total_images, extensions, unreadable, warnings = (
        dataset_discovery_service.scan_directory(temp_dataset_dir)
    )

    class_names = [c.class_name for c in classes]
    assert class_names == ["Apple_Class", "Banana_Class", "Mango_Class", "Zebra_Class"]
