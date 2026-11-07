import io
import os
import tempfile
from pathlib import Path
from PIL import Image
import pytest

from app.core.errors import DatasetDirectoryNotFoundError, DatasetNotDiscoveredError
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetSource,
    DatasetStatus,
    ValidationStatus,
)
from app.services.dataset_discovery_service import dataset_discovery_service
from app.services.image_validation_service import (
    ImageValidationService,
    image_validation_service,
)
from app.storage.local import LocalStorageBackend


@pytest.fixture
def temp_val_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def test_validate_valid_images_all_formats(temp_val_dir):
    # Setup test directory
    sub = temp_val_dir / "valid_subset"
    sub.mkdir(parents=True, exist_ok=True)

    # 1. Valid RGB JPEG
    jpeg_path = sub / "sample_rgb.jpg"
    Image.new("RGB", (120, 60), color=(16, 185, 129)).save(jpeg_path, "JPEG")

    # 2. Valid RGBA PNG
    png_path = sub / "sample_rgba.png"
    Image.new("RGBA", (80, 80), color=(34, 197, 94, 255)).save(png_path, "PNG")

    # 3. Valid WebP
    webp_path = sub / "sample_webp.webp"
    Image.new("RGB", (200, 100), color="blue").save(webp_path, "WEBP")

    # 4. Valid Grayscale (L) PNG
    gray_path = sub / "sample_gray.png"
    Image.new("L", (50, 50), color=120).save(gray_path, "PNG")

    # 5. Valid Unusual Aspect Ratio (10 x 500)
    unusual_path = sub / "sample_unusual.jpg"
    Image.new("RGB", (10, 500), color="yellow").save(unusual_path, "JPEG")

    # Execute per-image validation
    rec_jpeg = image_validation_service.validate_image_file(jpeg_path, temp_val_dir)
    assert rec_jpeg.status == ValidationStatus.VALID
    assert rec_jpeg.format == "JPEG"
    assert rec_jpeg.width == 120
    assert rec_jpeg.height == 60
    assert rec_jpeg.aspect_ratio == 2.0
    assert rec_jpeg.color_mode == "RGB"
    assert rec_jpeg.channels == 3
    assert rec_jpeg.file_size_bytes > 0

    rec_png = image_validation_service.validate_image_file(png_path, temp_val_dir)
    assert rec_png.status == ValidationStatus.VALID
    assert rec_png.format == "PNG"
    assert rec_png.color_mode == "RGBA"
    assert rec_png.channels == 4

    rec_webp = image_validation_service.validate_image_file(webp_path, temp_val_dir)
    assert rec_webp.status == ValidationStatus.VALID
    assert rec_webp.format == "WEBP"

    rec_gray = image_validation_service.validate_image_file(gray_path, temp_val_dir)
    assert rec_gray.status == ValidationStatus.VALID
    assert rec_gray.color_mode == "L"
    assert rec_gray.channels == 1

    rec_unusual = image_validation_service.validate_image_file(unusual_path, temp_val_dir)
    assert rec_unusual.status == ValidationStatus.VALID
    assert rec_unusual.width == 10
    assert rec_unusual.height == 500
    assert rec_unusual.aspect_ratio == 0.02


def test_validate_corrupted_and_invalid_images(temp_val_dir):
    sub = temp_val_dir / "invalid_subset"
    sub.mkdir(parents=True, exist_ok=True)

    # 1. Zero-byte file
    zero_file = sub / "zero_bytes.jpg"
    zero_file.write_bytes(b"")

    # 2. Random bytes with .jpg extension (malformed header)
    random_file = sub / "fake_header.jpg"
    random_file.write_bytes(b"PLAIN_RANDOM_TEXT_NOT_IMAGE_DATA_1234567890")

    # 3. Truncated image
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color="red").save(buf, "JPEG")
    valid_bytes = buf.getvalue()
    truncated_bytes = valid_bytes[: len(valid_bytes) // 4]
    truncated_file = sub / "truncated.jpg"
    truncated_file.write_bytes(truncated_bytes)

    # 4. Unsupported extension
    unsupported_file = sub / "document.pdf"
    unsupported_file.write_bytes(b"%PDF-1.4 dummy")

    # 5. Missing / deleted file
    deleted_file = sub / "already_deleted.jpg"

    rec_zero = image_validation_service.validate_image_file(zero_file, temp_val_dir)
    assert rec_zero.status == ValidationStatus.CORRUPT
    assert "Zero-byte" in (rec_zero.error_message or "")

    rec_random = image_validation_service.validate_image_file(random_file, temp_val_dir)
    assert rec_random.status == ValidationStatus.CORRUPT

    rec_truncated = image_validation_service.validate_image_file(truncated_file, temp_val_dir)
    assert rec_truncated.status == ValidationStatus.CORRUPT
    assert rec_truncated.error_message is not None

    rec_unsupported = image_validation_service.validate_image_file(unsupported_file, temp_val_dir)
    assert rec_unsupported.status == ValidationStatus.UNSUPPORTED

    rec_deleted = image_validation_service.validate_image_file(deleted_file, temp_val_dir)
    assert rec_deleted.status == ValidationStatus.UNREADABLE


def test_validate_dataset_aggregation(temp_val_dir):
    # Setup mixed dataset
    c1 = temp_val_dir / "Class_A"
    c2 = temp_val_dir / "Class_B"
    c1.mkdir(parents=True, exist_ok=True)
    c2.mkdir(parents=True, exist_ok=True)

    # 2 valid images in Class_A
    Image.new("RGB", (100, 100), color="green").save(c1 / "img1.jpg", "JPEG")
    Image.new("RGB", (200, 150), color="red").save(c1 / "img2.jpg", "JPEG")

    # 1 zero-byte file in Class_B
    (c2 / "corrupt_zero.jpg").write_bytes(b"")

    # 1 random bytes file in Class_B
    (c2 / "corrupt_random.png").write_bytes(b"NOT_A_PNG")

    dataset = DatasetMetadata(
        id="test-mixed-ds",
        name="Test Mixed Dataset",
        slug="test-mixed-ds",
        description="Testing validation aggregation",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T00:00:00Z",
        updated_at="2026-11-07T00:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.DISCOVERED,
        tags=[],
    )

    storage = LocalStorageBackend()
    storage.resolve_dataset_path = lambda d: temp_val_dir
    storage.sanitize_relative_path = lambda p: "curated/test-mixed-ds"

    result = image_validation_service.validate_dataset(dataset, storage)

    assert result.total_discovered_images == 4
    assert result.total_validated_images == 2
    assert result.total_corrupted_images == 2
    assert result.total_unreadable_images == 0
    assert result.total_processing_errors == 0
    assert len(result.corrupted_files) == 2
    assert result.validation_status == DatasetStatus.VALIDATED

    # Verify dimension statistics across valid images
    dim = result.dimension_summary
    assert dim is not None
    assert dim.min_width == 100
    assert dim.max_width == 200
    assert dim.min_height == 100
    assert dim.max_height == 150
    assert dim.mean_width == 150.0
    assert dim.mean_height == 125.0

    # Color mode and format distribution
    assert result.color_mode_distribution == {"RGB": 2}
    assert result.format_distribution == {"JPEG": 2}


def test_validate_dataset_missing_directory():
    storage = LocalStorageBackend()
    dataset = DatasetMetadata(
        id="missing-val-ds",
        name="Missing Dataset",
        slug="missing-val-ds",
        description="Non-existent directory",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T00:00:00Z",
        updated_at="2026-11-07T00:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.DISCOVERED,
        tags=[],
    )

    storage.resolve_dataset_path = lambda d: Path("/non/existent/path/for/test/xyz")
    with pytest.raises(DatasetDirectoryNotFoundError):
        image_validation_service.validate_dataset(dataset, storage)

