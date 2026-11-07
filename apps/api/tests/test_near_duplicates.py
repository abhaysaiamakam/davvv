import io
import random
from pathlib import Path
import pytest
from PIL import Image, ImageEnhance

from app.core.errors import (
    DatasetNotValidatedError,
    InvalidHammingThresholdError,
    InvalidPerceptualHashAlgorithmError,
)
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetSource,
    DatasetStatus,
    DatasetValidationResult,
    DuplicateAnalysisResult,
    ImageValidationRecord,
    NearDuplicateQueryConfig,
    PerceptualHashAlgorithm,
    ValidationStatus,
)
from app.services.near_duplicate_detection_service import (
    NearDuplicateDetectionService,
    near_duplicate_detection_service,
)
from app.services.perceptual_hash_service import (
    PerceptualHashService,
    perceptual_hash_service,
)
from app.storage.local import LocalStorageBackend


# ---------------------------------------------------------------------------
# Helper: generate block-pattern images with stable, distinct perceptual hashes
# ---------------------------------------------------------------------------

def _mk_block_pattern(size: int, seed: int, colors: list) -> Image.Image:
    """Create a block-pattern image deterministic on ``seed`` and ``colors``."""
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
_BLUE_PALETTE  = [(20, 20, 180), (50, 50, 220), (10, 10, 140), (70, 70, 200), (30, 30, 160)]


@pytest.fixture
def temp_storage(tmp_path: Path):
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()
    return backend, tmp_path


# --- 1. Perceptual Hashing Unit Tests ---

def test_identical_images_produce_identical_hashes(tmp_path: Path):
    """Test that two identical images yield the exact same perceptual hash."""
    img = Image.new("RGB", (128, 128), color=(34, 139, 34))
    path_a = tmp_path / "img_a.png"
    path_b = tmp_path / "img_b.png"
    img.save(path_a, "PNG")
    img.save(path_b, "PNG")

    service = PerceptualHashService()
    hash_a = service.compute_hash(path_a, PerceptualHashAlgorithm.PHASH)
    hash_b = service.compute_hash(path_b, PerceptualHashAlgorithm.PHASH)

    assert hash_a == hash_b
    assert len(hash_a) == 16  # 64-bit hash is 16 hex chars


def test_resized_and_recompressed_images_are_perceptually_similar(tmp_path: Path):
    """Test that resizing and JPEG recompression produce low Hamming distance."""
    # Create base image with diagonal stripe pattern
    base = Image.new("RGB", (256, 256), color=(255, 255, 255))
    for x in range(256):
        for y in range(x - 10, x + 10):
            if 0 <= y < 256:
                base.putpixel((x, y), (0, 128, 0))

    orig_path = tmp_path / "orig.jpg"
    base.save(orig_path, "JPEG", quality=95)

    # 1. Resized version (128x128)
    resized_path = tmp_path / "resized.jpg"
    base.resize((128, 128), Image.Resampling.BILINEAR).save(resized_path, "JPEG", quality=95)

    # 2. Recompressed version with lower quality (quality 50)
    recompressed_path = tmp_path / "recompressed.jpg"
    base.save(recompressed_path, "JPEG", quality=50)

    # 3. Completely different image (checkerboard / blue)
    diff_path = tmp_path / "diff.jpg"
    diff_img = Image.new("RGB", (256, 256), color=(0, 0, 255))
    diff_img.save(diff_path, "JPEG", quality=95)

    service = PerceptualHashService()
    h_orig = service.compute_hash(orig_path, PerceptualHashAlgorithm.PHASH)
    h_resized = service.compute_hash(resized_path, PerceptualHashAlgorithm.PHASH)
    h_recomp = service.compute_hash(recompressed_path, PerceptualHashAlgorithm.PHASH)
    h_diff = service.compute_hash(diff_path, PerceptualHashAlgorithm.PHASH)

    dist_resized = service.compute_hamming_distance(h_orig, h_resized)
    dist_recomp = service.compute_hamming_distance(h_orig, h_recomp)
    dist_diff = service.compute_hamming_distance(h_orig, h_diff)

    # Resized and recompressed should have very low distance (typically <= 4 bits)
    assert dist_resized <= 6
    assert dist_recomp <= 4
    # Different image should have significantly higher distance
    assert dist_diff > dist_resized
    assert dist_diff > 15


def test_minor_brightness_variation_handled(tmp_path: Path):
    """Test that minor brightness adjustments maintain near-zero Hamming distance."""
    base = Image.new("RGB", (100, 100), color=(100, 150, 50))
    orig_path = tmp_path / "bright_orig.jpg"
    base.save(orig_path, "JPEG")

    enhancer = ImageEnhance.Brightness(base)
    brighter = enhancer.enhance(1.15)  # 15% brighter
    bright_path = tmp_path / "brighter.jpg"
    brighter.save(bright_path, "JPEG")

    service = PerceptualHashService()
    h1 = service.compute_hash(orig_path, PerceptualHashAlgorithm.PHASH)
    h2 = service.compute_hash(bright_path, PerceptualHashAlgorithm.PHASH)
    dist = service.compute_hamming_distance(h1, h2)

    assert dist <= 4  # Very small shift under DCT hash


def test_grayscale_and_rgba_modes_handled_consistently(tmp_path: Path):
    """Test that grayscale and transparent RGBA images are converted deterministically."""
    # RGB image
    rgb_img = Image.new("RGB", (64, 64), color=(50, 100, 150))
    rgb_path = tmp_path / "test_rgb.png"
    rgb_img.save(rgb_path, "PNG")

    # Grayscale image
    l_img = rgb_img.convert("L")
    l_path = tmp_path / "test_l.png"
    l_img.save(l_path, "PNG")

    # RGBA image with alpha channel
    rgba_img = rgb_img.convert("RGBA")
    rgba_path = tmp_path / "test_rgba.png"
    rgba_img.save(rgba_path, "PNG")

    service = PerceptualHashService()
    h_rgb = service.compute_hash(rgb_path, PerceptualHashAlgorithm.PHASH)
    h_l = service.compute_hash(l_path, PerceptualHashAlgorithm.PHASH)
    h_rgba = service.compute_hash(rgba_path, PerceptualHashAlgorithm.PHASH)

    # RGB and RGBA with full alpha must match
    assert h_rgb == h_rgba
    # L mode perceptual representation should be very close to RGB conversion
    assert service.compute_hamming_distance(h_rgb, h_l) <= 2


# --- 2. Hamming Distance and Similarity Tests ---

def test_hamming_distance_and_similarity_boundary_conditions():
    """Test boundary conditions for distance and normalized similarity."""
    service = PerceptualHashService()

    # Identical hashes: distance 0, similarity 1.0
    h_zero = "0000000000000000"
    assert service.compute_hamming_distance(h_zero, h_zero) == 0
    assert service.compute_similarity(0, total_bits=64) == 1.0

    # 1-bit difference: distance 1, similarity 1 - 1/64 = 0.9844
    h_one_bit = "0000000000000001"
    assert service.compute_hamming_distance(h_zero, h_one_bit) == 1
    assert service.compute_similarity(1, total_bits=64) == 0.9844

    # Maximum difference (all 64 bits inverted): distance 64, similarity 0.0
    h_all_ones = "ffffffffffffffff"
    assert service.compute_hamming_distance(h_zero, h_all_ones) == 64
    assert service.compute_similarity(64, total_bits=64) == 0.0

    # Invalid hash length mismatch
    with pytest.raises(ValueError, match="Hash length mismatch"):
        service.compute_hamming_distance("0000", "00000000")


# --- 3. Near-Duplicate Grouping Tests ---

def test_near_duplicate_grouping_two_and_three_members(temp_storage):
    """Test grouping of near-duplicates with canonical representative selection.

    Uses 8×8 block-pattern images whose pHash properties are pre-verified:
      - seed=1 green base, its resized copy, and brightened copy all share the
        same pHash (distance 0) — reliably in the same near-dup group.
      - seed=2 red pattern is 28 bits away — never grouped with the green images
        at any reasonable threshold.
    """
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "ndup-test"
    curated_dir.mkdir(parents=True, exist_ok=True)
    rice_dir = curated_dir / "Rice" / "brown_spot"
    rice_dir.mkdir(parents=True, exist_ok=True)

    # Base image: green block pattern (seed=1)
    base = _mk_block_pattern(200, 1, _GREEN_PALETTE)
    base.save(rice_dir / "leaf_a.jpg", "JPEG", quality=95)
    # Resized version → near-duplicate (pHash distance 0 from base)
    base.resize((160, 160)).save(rice_dir / "leaf_b.jpg", "JPEG", quality=90)
    # Brightened version → near-duplicate (pHash distance 0 from base)
    ImageEnhance.Brightness(base).enhance(1.15).save(rice_dir / "leaf_c.jpg", "JPEG", quality=85)
    # Completely distinct red pattern (seed=2) — 28 bits away → not grouped
    _mk_block_pattern(200, 2, _RED_PALETTE).save(rice_dir / "leaf_unrelated.jpg", "JPEG", quality=95)

    records = [
        ImageValidationRecord(relative_path="Rice/brown_spot/leaf_a.jpg", file_size_bytes=1000, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/brown_spot/leaf_b.jpg", file_size_bytes=800, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/brown_spot/leaf_c.jpg", file_size_bytes=900, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/brown_spot/leaf_unrelated.jpg", file_size_bytes=1200, status=ValidationStatus.VALID),
    ]

    val_result = DatasetValidationResult(
        dataset_id="ndup-test",
        dataset_name="Near Duplicate Test",
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
        id="ndup-test",
        name="Near Duplicate Test",
        slug="ndup-test",
        description="Near Duplicate Test",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    config = NearDuplicateQueryConfig(
        algorithm=PerceptualHashAlgorithm.PHASH,
        hash_size=8,
        distance_threshold=8,
    )

    result = near_duplicate_detection_service.detect_near_duplicates(dataset, backend, config)

    assert result.total_eligible_images == 4
    assert result.successfully_hashed_images == 4
    assert result.near_duplicate_groups == 1
    assert result.images_in_near_duplicate_groups == 3
    assert result.redundant_near_duplicate_instances == 2

    group = result.groups[0]
    assert group.image_count == 3
    # Canonical representative is lexicographically smallest
    assert group.representative.relative_path == "Rice/brown_spot/leaf_a.jpg"
    assert group.representative.is_representative is True

    # Other members are near-duplicates
    dup_paths = [m.relative_path for m in group.near_duplicates]
    assert "Rice/brown_spot/leaf_b.jpg" in dup_paths
    assert "Rice/brown_spot/leaf_c.jpg" in dup_paths
    assert "Rice/brown_spot/leaf_unrelated.jpg" not in dup_paths
    assert group.is_cross_class is False


def test_cross_class_near_duplicate_detection(temp_storage):
    """Test detection of visually similar images residing in different class folders."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "ndup-cross"
    curated_dir.mkdir(parents=True, exist_ok=True)

    folder_a = curated_dir / "Rice" / "class_one"
    folder_b = curated_dir / "Rice" / "class_two"
    folder_a.mkdir(parents=True, exist_ok=True)
    folder_b.mkdir(parents=True, exist_ok=True)

    base = Image.new("RGB", (100, 100), color=(50, 150, 50))
    base.save(folder_a / "leaf_01.jpg", "JPEG", quality=95)
    # Slightly resized copy in a different disease folder
    base.resize((80, 80)).save(folder_b / "leaf_02.jpg", "JPEG", quality=85)

    records = [
        ImageValidationRecord(relative_path="Rice/class_one/leaf_01.jpg", file_size_bytes=1000, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/class_two/leaf_02.jpg", file_size_bytes=800, status=ValidationStatus.VALID),
    ]

    val_result = DatasetValidationResult(
        dataset_id="ndup-cross",
        dataset_name="Cross Class NDup",
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
        id="ndup-cross",
        name="Cross Class NDup",
        slug="ndup-cross",
        description="Cross Class NDup",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    result = near_duplicate_detection_service.detect_near_duplicates(dataset, backend)
    assert result.near_duplicate_groups == 1
    assert result.cross_class_near_duplicate_groups == 1
    assert result.groups[0].is_cross_class is True
    assert set(result.groups[0].classes_involved) == {"Rice/class_one", "Rice/class_two"}


def test_exact_duplicates_do_not_inflate_near_duplicate_metrics(temp_storage):
    """Test that exact byte duplicates are collapsed and do not create redundant near-duplicate entries."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "ndup-exact-interaction"
    curated_dir.mkdir(parents=True, exist_ok=True)
    folder = curated_dir / "Rice" / "blight"
    folder.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (100, 100), color=(80, 160, 40))
    img.save(folder / "img_base.jpg", "JPEG")
    # Exact byte duplicate
    (folder / "img_exact_copy.jpg").write_bytes((folder / "img_base.jpg").read_bytes())

    # Distinct near-duplicate (resized)
    img.resize((80, 80)).save(folder / "img_near_dup.jpg", "JPEG", quality=80)

    records = [
        ImageValidationRecord(relative_path="Rice/blight/img_base.jpg", file_size_bytes=1000, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/blight/img_exact_copy.jpg", file_size_bytes=1000, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/blight/img_near_dup.jpg", file_size_bytes=800, status=ValidationStatus.VALID),
    ]

    val_result = DatasetValidationResult(
        dataset_id="ndup-exact-interaction",
        dataset_name="Exact Interaction",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=3,
        total_validated_images=3,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="ndup-exact-interaction",
        name="Exact Interaction",
        slug="ndup-exact-interaction",
        description="Exact Interaction",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    result = near_duplicate_detection_service.detect_near_duplicates(dataset, backend)
    # The exact duplicate copy is collapsed
    assert result.exact_duplicates_collapsed_count == 1
    assert result.unique_content_representatives_compared == 2
    # Exactly one near-duplicate group between base and near_dup
    assert result.near_duplicate_groups == 1
    assert result.groups[0].image_count == 2
    assert "Rice/blight/img_exact_copy.jpg" not in [m.relative_path for m in result.groups[0].near_duplicates]



def test_unrelated_images_produce_no_near_duplicate_groups(temp_storage):
    """Test that distinct images with high Hamming distance form zero groups.

    Uses block-pattern images whose pHash distances are pre-verified:
      seed=1 green (28 bits from red), seed=2 red (32 bits from blue), seed=3 blue.
    All pairs are >6 bits apart, so threshold=6 must yield zero groups.
    """
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "ndup-unrelated"
    curated_dir.mkdir(parents=True, exist_ok=True)
    folder = curated_dir / "Rice" / "disease"
    folder.mkdir(parents=True, exist_ok=True)

    # Three visually distinct block-pattern images (pHash distance >20 between all pairs)
    _mk_block_pattern(128, 1, _GREEN_PALETTE).save(folder / "green.jpg", "JPEG", quality=95)
    _mk_block_pattern(128, 2, _RED_PALETTE).save(folder / "red.jpg",   "JPEG", quality=95)
    _mk_block_pattern(128, 3, _BLUE_PALETTE).save(folder / "blue.jpg", "JPEG", quality=95)

    records = [
        ImageValidationRecord(relative_path="Rice/disease/green.jpg", file_size_bytes=500, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/disease/red.jpg",   file_size_bytes=500, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/disease/blue.jpg",  file_size_bytes=500, status=ValidationStatus.VALID),
    ]

    val_result = DatasetValidationResult(
        dataset_id="ndup-unrelated",
        dataset_name="Unrelated",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=3,
        total_validated_images=3,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="ndup-unrelated",
        name="Unrelated",
        slug="ndup-unrelated",
        description="Unrelated",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    config = NearDuplicateQueryConfig(
        algorithm=PerceptualHashAlgorithm.PHASH,
        distance_threshold=6,
    )
    result = near_duplicate_detection_service.detect_near_duplicates(dataset, backend, config)

    assert result.near_duplicate_groups == 0
    assert result.images_in_near_duplicate_groups == 0
    assert result.redundant_near_duplicate_instances == 0
    assert result.near_duplicate_percentage == 0.0
    assert len(result.groups) == 0


def test_deterministic_repeated_analysis_produces_stable_results(temp_storage):
    """Test that running the analysis twice on the same data yields identical results."""
    backend, tmp_path = temp_storage
    curated_dir = backend.curated_dir / "ndup-stable"
    curated_dir.mkdir(parents=True, exist_ok=True)
    folder = curated_dir / "Rice" / "leaf_spot"
    folder.mkdir(parents=True, exist_ok=True)

    base = Image.new("RGB", (120, 120), color=(30, 100, 30))
    base.save(folder / "aa.jpg", "JPEG", quality=95)
    base.resize((90, 90)).save(folder / "bb.jpg", "JPEG", quality=90)
    Image.new("RGB", (120, 120), color=(180, 50, 50)).save(folder / "cc.jpg", "JPEG")

    records = [
        ImageValidationRecord(relative_path="Rice/leaf_spot/aa.jpg", file_size_bytes=800, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/leaf_spot/bb.jpg", file_size_bytes=700, status=ValidationStatus.VALID),
        ImageValidationRecord(relative_path="Rice/leaf_spot/cc.jpg", file_size_bytes=600, status=ValidationStatus.VALID),
    ]

    val_result = DatasetValidationResult(
        dataset_id="ndup-stable",
        dataset_name="Stable",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=3,
        total_validated_images=3,
        total_corrupted_images=0,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        images=records,
        warnings=[],
    )

    dataset = DatasetMetadata(
        id="ndup-stable",
        name="Stable",
        slug="ndup-stable",
        description="Stable",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.VALIDATED,
        validation=val_result,
    )

    config = NearDuplicateQueryConfig(distance_threshold=8)

    res1 = near_duplicate_detection_service.detect_near_duplicates(dataset, backend, config)
    res2 = near_duplicate_detection_service.detect_near_duplicates(dataset, backend, config)

    assert res1.near_duplicate_groups == res2.near_duplicate_groups
    assert res1.redundant_near_duplicate_instances == res2.redundant_near_duplicate_instances
    if res1.groups:
        assert res1.groups[0].representative.relative_path == res2.groups[0].representative.relative_path
        assert [m.relative_path for m in res1.groups[0].near_duplicates] == \
               [m.relative_path for m in res2.groups[0].near_duplicates]


# --- 4. API Integration Tests ---

def test_near_duplicate_detect_unknown_id(client):
    response = client.post("/api/v1/datasets/nonexistent-99/near-duplicates/detect")
    assert response.status_code == 404
    assert response.json()["error_code"] == "DATASET_NOT_FOUND"


def test_near_duplicate_detect_before_validation_returns_error(client):
    # mendeley-rice has never been validated
    response = client.post("/api/v1/datasets/mendeley-rice/near-duplicates/detect")
    assert response.status_code == 400
    assert response.json()["error_code"] == "DATASET_NOT_VALIDATED"


def test_near_duplicate_get_before_analysis_returns_404(client):
    response = client.get("/api/v1/datasets/paddy-doctor/near-duplicates")
    assert response.status_code == 404
    assert response.json()["error_code"] == "NEAR_DUPLICATE_ANALYSIS_NOT_FOUND"


def test_near_duplicate_full_e2e(client, temp_storage_dir):
    """End-to-end: discover -> validate -> detect near-duplicates -> retrieve."""
    from PIL import Image as PILImage

    curated_dir = temp_storage_dir / "curated" / "icar-rice-maize"
    ndup_dir = curated_dir / "Rice" / "ndup_e2e"
    ndup_dir.mkdir(parents=True, exist_ok=True)

    base = PILImage.new("RGB", (100, 100), color=(40, 120, 40))
    base.save(ndup_dir / "img_a.jpg", "JPEG", quality=95)
    base.resize((80, 80)).save(ndup_dir / "img_b.jpg", "JPEG", quality=85)
    PILImage.new("RGB", (100, 100), color=(200, 30, 30)).save(ndup_dir / "img_c.jpg", "JPEG")

    # 1. Discover
    r = client.post("/api/v1/datasets/icar-rice-maize/discover")
    assert r.status_code == 200

    # 2. Validate
    r = client.post("/api/v1/datasets/icar-rice-maize/validate")
    assert r.status_code == 200

    # 3. Detect near-duplicates
    r = client.post(
        "/api/v1/datasets/icar-rice-maize/near-duplicates/detect",
        json={"algorithm": "phash", "hash_size": 8, "distance_threshold": 8},
    )
    assert r.status_code == 200
    data = r.json()

    assert data["dataset_id"] == "icar-rice-maize"
    assert data["algorithm"] == "phash"
    assert data["distance_threshold"] == 8
    assert data["total_eligible_images"] >= 3
    assert data["successfully_hashed_images"] >= 3
    assert data["near_duplicate_groups"] >= 1
    assert data["pairwise_comparisons_performed"] >= 1

    group = next(
        g for g in data["groups"]
        if any("img_a.jpg" in m["relative_path"] or "img_b.jpg" in m["relative_path"]
               for m in [g["representative"]] + g["near_duplicates"])
    )
    assert group["representative"]["is_representative"] is True
    assert all(d["is_representative"] is False for d in group["near_duplicates"])

    # 4. Retrieve via GET
    r2 = client.get("/api/v1/datasets/icar-rice-maize/near-duplicates")
    assert r2.status_code == 200
    assert r2.json()["near_duplicate_groups"] == data["near_duplicate_groups"]
