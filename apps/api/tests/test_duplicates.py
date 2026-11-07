import hashlib
import os
import pytest
from pathlib import Path

from app.core.errors import DatasetNotValidatedError, DatasetDirectoryNotFoundError
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetSource,
    DatasetStatus,
    DatasetValidationResult,
    ImageValidationRecord,
    ValidationStatus,
)
from app.services.duplicate_detection_service import (
    DuplicateDetectionService,
    duplicate_detection_service,
)
from app.storage.local import LocalStorageBackend


@pytest.fixture
def temp_storage(tmp_path: Path):
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()
    return backend, tmp_path


def test_sha256_streaming_identical_and_different_content(tmp_path: Path):
    """Test that chunked streaming hashing produces expected SHA-256 digests."""
    file_a = tmp_path / "img_a.jpg"
    file_b = tmp_path / "img_b.jpg"
    file_c = tmp_path / "img_c.jpg"

    content_1 = b"CropLens Agricultural Test Byte Stream 1234567890" * 2000
    content_2 = b"Different Disease Image Data 987654321" * 1500

    file_a.write_bytes(content_1)
    file_b.write_bytes(content_1)
    file_c.write_bytes(content_2)

    service = DuplicateDetectionService()
    hash_a = service.compute_file_sha256(file_a)
    hash_b = service.compute_file_sha256(file_b)
    hash_c = service.compute_file_sha256(file_c)

    # Identical content -> identical hash
    assert hash_a == hash_b
    assert hash_a == hashlib.sha256(content_1).hexdigest()

    # Different content -> different hash
    assert hash_a != hash_c
    assert hash_c == hashlib.sha256(content_2).hexdigest()


def test_duplicate_grouping_two_and_three_members(temp_storage):
    """Test grouping of exact duplicates with canonical representative selection."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "test-grouping"
    curated_dir.mkdir(parents=True, exist_ok=True)

    rice_dir = curated_dir / "Rice" / "blast"
    rice_dir.mkdir(parents=True, exist_ok=True)

    bytes_duplicate = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xDB\x00C\x00ABCDEFGHIJK"
    bytes_unique = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xDB\x00C\x00UNIQUE_CONTENT"

    # Create 3 identical files and 1 distinct file
    (rice_dir / "img_z.jpg").write_bytes(bytes_duplicate)
    (rice_dir / "img_a.jpg").write_bytes(bytes_duplicate)
    (rice_dir / "img_m.jpg").write_bytes(bytes_duplicate)
    (rice_dir / "img_unique.jpg").write_bytes(bytes_unique)

    # Construct validation result with all 4 valid images
    records = [
        ImageValidationRecord(
            relative_path="Rice/blast/img_z.jpg",
            file_size_bytes=len(bytes_duplicate),
            format="JPEG",
            width=100,
            height=100,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        ),
        ImageValidationRecord(
            relative_path="Rice/blast/img_a.jpg",
            file_size_bytes=len(bytes_duplicate),
            format="JPEG",
            width=100,
            height=100,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        ),
        ImageValidationRecord(
            relative_path="Rice/blast/img_m.jpg",
            file_size_bytes=len(bytes_duplicate),
            format="JPEG",
            width=100,
            height=100,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        ),
        ImageValidationRecord(
            relative_path="Rice/blast/img_unique.jpg",
            file_size_bytes=len(bytes_unique),
            format="JPEG",
            width=100,
            height=100,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        ),
    ]

    val_result = DatasetValidationResult(
        dataset_id="test-grouping",
        dataset_name="Test Grouping",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=4,
        total_validated_images=4,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="test-grouping",
        name="Test Grouping",
        slug="test-grouping",
        description="Test dataset",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    result = duplicate_detection_service.detect_duplicates(dataset, backend)

    assert result.total_eligible_images == 4
    assert result.successfully_hashed_images == 4
    assert result.hashing_failures == 0
    assert result.unique_content_groups == 2
    assert result.exact_duplicate_groups == 1
    assert result.duplicate_instances_count == 2
    assert result.images_in_duplicate_groups == 3
    # 2 redundant copies out of 4 hashed images = 50.0%
    assert result.duplicate_percentage == 50.0

    group = result.groups[0]
    assert group.image_count == 3
    # Canonical representative must be lexicographically smallest relative path
    assert group.representative.relative_path == "Rice/blast/img_a.jpg"
    assert group.representative.is_representative is True

    # Remaining 2 members are duplicates
    assert len(group.duplicates) == 2
    duplicate_paths = [d.relative_path for d in group.duplicates]
    assert duplicate_paths == ["Rice/blast/img_m.jpg", "Rice/blast/img_z.jpg"]
    assert all(d.is_representative is False for d in group.duplicates)
    assert group.is_cross_class is False


def test_cross_class_duplicate_detection(temp_storage):
    """Test detection of identical content across two distinct class folders."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "test-cross-class"
    curated_dir.mkdir(parents=True, exist_ok=True)

    class_1 = curated_dir / "Rice" / "bacterial_blight"
    class_2 = curated_dir / "Rice" / "tungro"
    class_1.mkdir(parents=True, exist_ok=True)
    class_2.mkdir(parents=True, exist_ok=True)

    shared_content = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xDB\x00C\x00CROSS_CLASS"
    (class_1 / "image_01.jpg").write_bytes(shared_content)
    (class_2 / "image_02.jpg").write_bytes(shared_content)

    records = [
        ImageValidationRecord(
            relative_path="Rice/bacterial_blight/image_01.jpg",
            file_size_bytes=len(shared_content),
            format="JPEG",
            width=200,
            height=200,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        ),
        ImageValidationRecord(
            relative_path="Rice/tungro/image_02.jpg",
            file_size_bytes=len(shared_content),
            format="JPEG",
            width=200,
            height=200,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        ),
    ]

    val_result = DatasetValidationResult(
        dataset_id="test-cross-class",
        dataset_name="Test Cross Class",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=2,
        total_validated_images=2,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="test-cross-class",
        name="Test Cross Class",
        slug="test-cross-class",
        description="Test dataset",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    result = duplicate_detection_service.detect_duplicates(dataset, backend)

    assert result.exact_duplicate_groups == 1
    assert result.cross_class_duplicate_groups == 1
    group = result.groups[0]
    assert group.is_cross_class is True
    assert set(group.classes_involved) == {"Rice/bacterial_blight", "Rice/tungro"}
    assert group.representative.class_name == "Rice/bacterial_blight"
    assert group.duplicates[0].class_name == "Rice/tungro"


def test_single_file_dataset_produces_no_duplicates(temp_storage):
    """Test that dataset with single valid file produces zero duplicate groups."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "test-single"
    curated_dir.mkdir(parents=True, exist_ok=True)

    single_file = curated_dir / "single.jpg"
    single_file.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xDB\x00C\x00SINGLE")

    records = [
        ImageValidationRecord(
            relative_path="single.jpg",
            file_size_bytes=len(single_file.read_bytes()),
            format="JPEG",
            width=50,
            height=50,
            aspect_ratio=1.0,
            color_mode="RGB",
            channels=3,
            status=ValidationStatus.VALID,
        )
    ]

    val_result = DatasetValidationResult(
        dataset_id="test-single",
        dataset_name="Test Single",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=1,
        total_validated_images=1,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="test-single",
        name="Test Single",
        slug="test-single",
        description="Single file dataset",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    result = duplicate_detection_service.detect_duplicates(dataset, backend)
    assert result.total_eligible_images == 1
    assert result.successfully_hashed_images == 1
    assert result.unique_content_groups == 1
    assert result.exact_duplicate_groups == 0
    assert result.duplicate_instances_count == 0
    assert result.duplicate_percentage == 0.0
    assert len(result.groups) == 0


def test_hashing_failure_gracefully_handled(temp_storage):
    """Test that a file deleted or unreadable after validation does not crash detection."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "test-missing-file"
    curated_dir.mkdir(parents=True, exist_ok=True)

    existing_file = curated_dir / "exists.jpg"
    existing_file.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xDB\x00C\x00DATA")

    # Record includes a file that was deleted after validation
    records = [
        ImageValidationRecord(
            relative_path="exists.jpg",
            file_size_bytes=len(existing_file.read_bytes()),
            status=ValidationStatus.VALID,
        ),
        ImageValidationRecord(
            relative_path="removed.jpg",
            file_size_bytes=100,
            status=ValidationStatus.VALID,
        ),
    ]

    val_result = DatasetValidationResult(
        dataset_id="test-missing-file",
        dataset_name="Test Missing File",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=2,
        total_validated_images=2,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="test-missing-file",
        name="Test Missing File",
        slug="test-missing-file",
        description="Dataset with missing file",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    result = duplicate_detection_service.detect_duplicates(dataset, backend)
    assert result.total_eligible_images == 2
    assert result.successfully_hashed_images == 1
    assert result.hashing_failures == 1
    assert len(result.warnings) >= 1
    assert "File missing on filesystem when hashing: removed.jpg" in result.warnings[0]

