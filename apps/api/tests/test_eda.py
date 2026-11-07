"""
Comprehensive pytest test suite for M4: EDA Engine.

Tests cover:
- Class distribution statistics (entropy, Gini, CV, imbalance ratio)
- Dimension analysis (orientation classification, missing metadata)
- Aspect ratio analysis (extreme values, zero-height protection)
- Format analysis (single and multiple formats)
- Color analysis (grayscale, RGB, RGBA)
- File size statistics
- Findings generation (stable IDs)
- Persistence and rehydration
- FastAPI endpoint integration
- No host path leakage
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import pytest
from fastapi import status

from app.schemas.analysis import AnalysisStatus, UnifiedAnalysisMetrics, UnifiedAnalysisResult
from app.schemas.dataset import (
    ClassDiscoveryInfo,
    DatasetDiscoveryResult,
    DatasetSource,
    DatasetStatus,
    DatasetValidationResult,
    DimensionSummary,
    DuplicateAnalysisResult,
    ImageValidationRecord,
    NearDuplicateAnalysisResult,
    ValidationStatus,
)
from app.schemas.eda import (
    EdaReport,
    EdaStatus,
)
from app.services.eda_service import EdaService, _compute_entropy, _compute_gini
from app.storage.local import LocalStorageBackend


# ---------------------------------------------------------------------------
# Helpers: synthetic data builders
# ---------------------------------------------------------------------------

def _make_img(
    relative_path: str,
    width: Optional[int] = 640,
    height: Optional[int] = 480,
    color_mode: str = "RGB",
    fmt: str = "JPEG",
    file_size_bytes: int = 50_000,
    status: ValidationStatus = ValidationStatus.VALID,
) -> ImageValidationRecord:
    ar = (width / height) if (width and height and height > 0) else None
    return ImageValidationRecord(
        relative_path=relative_path,
        file_size_bytes=file_size_bytes,
        format=fmt,
        width=width,
        height=height,
        aspect_ratio=ar,
        color_mode=color_mode,
        channels=3 if color_mode == "RGB" else (4 if color_mode == "RGBA" else 1),
        status=status,
    )


def _make_discovery(
    dataset_id: str = "test-ds",
    classes: Optional[List[ClassDiscoveryInfo]] = None,
) -> DatasetDiscoveryResult:
    if classes is None:
        classes = [
            ClassDiscoveryInfo(class_name="Cat", relative_path="Cat", image_count=50),
            ClassDiscoveryInfo(class_name="Dog", relative_path="Dog", image_count=50),
        ]
    return DatasetDiscoveryResult(
        dataset_id=dataset_id,
        dataset_name="Test Dataset",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        dataset_root_relative_path=f"curated/{dataset_id}",
        discovery_status=DatasetStatus.DISCOVERED,
        discovered_image_files=sum(c.image_count for c in classes),
        discovered_class_directories=len(classes),
        classes=classes,
        ingestion_timestamp="2026-11-07T12:00:00Z",
    )


def _make_validation(
    dataset_id: str = "test-ds",
    images: Optional[List[ImageValidationRecord]] = None,
    formats: Optional[dict] = None,
    color_modes: Optional[dict] = None,
) -> DatasetValidationResult:
    imgs = images or []
    valid = [i for i in imgs if i.status == ValidationStatus.VALID]
    corrupt = [i for i in imgs if i.status != ValidationStatus.VALID]
    return DatasetValidationResult(
        dataset_id=dataset_id,
        dataset_name="Test Dataset",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=len(imgs),
        total_validated_images=len(valid),
        total_corrupted_images=len(corrupt),
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp="2026-11-07T12:00:00Z",
        format_distribution=formats or {"JPEG": len(valid)},
        color_mode_distribution=color_modes or {"RGB": len(valid)},
        images=imgs,
    )


def _make_analysis(
    dataset_id: str = "test-ds",
    discovery: Optional[DatasetDiscoveryResult] = None,
    validation: Optional[DatasetValidationResult] = None,
) -> UnifiedAnalysisResult:
    disc = discovery or _make_discovery(dataset_id)
    val = validation or _make_validation(dataset_id)
    now = "2026-11-07T12:00:00Z"
    total_valid = val.total_validated_images

    exact_res = DuplicateAnalysisResult(
        dataset_id=dataset_id,
        dataset_name="Test Dataset",
        analysis_timestamp=now,
        total_eligible_images=total_valid,
        successfully_hashed_images=total_valid,
        unique_content_groups=total_valid,
        exact_duplicate_groups=0,
        duplicate_instances_count=0,
        images_in_duplicate_groups=0,
        duplicate_percentage=0.0,
        cross_class_duplicate_groups=0,
    )

    near_res = NearDuplicateAnalysisResult(
        dataset_id=dataset_id,
        dataset_name="Test Dataset",
        analysis_timestamp=now,
        algorithm="phash",
        hash_size=8,
        distance_threshold=10,
        similarity_threshold=0.8438,
        total_eligible_images=total_valid,
        successfully_hashed_images=total_valid,
        unique_perceptual_hashes=total_valid,
        exact_duplicates_collapsed_count=0,
        unique_content_representatives_compared=total_valid,
        pairwise_comparisons_performed=0,
        near_duplicate_groups=0,
        images_in_near_duplicate_groups=0,
        redundant_near_duplicate_instances=0,
        near_duplicate_percentage=0.0,
        cross_class_near_duplicate_groups=0,
        analysis_duration_ms=100.0,
    )

    metrics = UnifiedAnalysisMetrics(
        total_files_discovered=disc.discovered_image_files or 0,
        total_classes_discovered=len(disc.classes),
        total_validated_images=total_valid,
        total_corrupted_images=val.total_corrupted_images,
        exact_duplicate_groups=0,
        exact_duplicate_redundant_instances=0,
        exact_duplicate_percentage=0.0,
        near_duplicate_groups=0,
        near_duplicate_images_in_groups=0,
        near_duplicate_redundant_instances=0,
        near_duplicate_percentage=0.0,
        total_redundant_images=0,
        clean_unique_images=total_valid,
        cross_class_exact_duplicate_groups=0,
        cross_class_near_duplicate_groups=0,
    )

    return UnifiedAnalysisResult(
        id=f"ana-{dataset_id}-test",
        dataset_id=dataset_id,
        dataset_name="Test Dataset",
        status=AnalysisStatus.COMPLETED,
        created_at=now,
        completed_at=now,
        duration_ms=500.0,
        stages_completed=["discovery", "validation", "exact_duplicates", "near_duplicates"],
        metrics=metrics,
        discovery=disc,
        validation=val,
        exact_duplicates=exact_res,
        near_duplicates=near_res,
    )


# ---------------------------------------------------------------------------
# 1. Class Distribution Tests
# ---------------------------------------------------------------------------

def test_eda_class_distribution_balanced(tmp_path: Path):
    """Near-perfectly balanced classes produce high normalized entropy (> 0.9)."""
    classes = [
        ClassDiscoveryInfo(class_name=f"Class_{i}", relative_path=f"Class_{i}", image_count=100)
        for i in range(5)
    ]
    imgs = [_make_img(f"Class_{i}/img_{j}.jpg") for i in range(5) for j in range(100)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_class_distribution(disc, val, imgs)

    assert result.total_classes == 5
    assert result.classes_with_images == 5
    assert result.empty_classes == []
    assert result.normalized_entropy is not None
    assert result.normalized_entropy > 0.9
    assert result.gini_coefficient < 0.1


def test_eda_class_distribution_imbalanced(tmp_path: Path):
    """Heavily imbalanced classes produce low normalized entropy and high CV."""
    classes = [
        ClassDiscoveryInfo(class_name="Majority", relative_path="Majority", image_count=900),
        ClassDiscoveryInfo(class_name="Minority", relative_path="Minority", image_count=10),
    ]
    imgs = (
        [_make_img(f"Majority/img_{j}.jpg") for j in range(900)]
        + [_make_img(f"Minority/img_{j}.jpg") for j in range(10)]
    )
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_class_distribution(disc, val, imgs)

    assert result.coefficient_of_variation is not None
    assert result.coefficient_of_variation > 0.5
    assert result.imbalance_ratio is not None
    assert result.imbalance_ratio == pytest.approx(90.0, rel=0.01)
    assert result.normalized_entropy is not None
    assert result.normalized_entropy < 0.9


def test_eda_class_distribution_empty_class(tmp_path: Path):
    """Empty class is correctly identified and listed."""
    classes = [
        ClassDiscoveryInfo(class_name="Full", relative_path="Full", image_count=50),
        ClassDiscoveryInfo(class_name="Empty", relative_path="Empty", image_count=0),
    ]
    imgs = [_make_img(f"Full/img_{j}.jpg") for j in range(50)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_class_distribution(disc, val, imgs)

    assert "Empty" in result.empty_classes
    assert result.classes_with_images == 1
    assert result.min_count == 0


def test_eda_class_distribution_single_class(tmp_path: Path):
    """Single class: entropy=0, normalized_entropy=0.0, CV=None (mean=count so std=0)."""
    classes = [ClassDiscoveryInfo(class_name="Only", relative_path="Only", image_count=100)]
    imgs = [_make_img(f"Only/img_{j}.jpg") for j in range(100)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_class_distribution(disc, val, imgs)

    assert result.entropy == 0.0
    # With a single class, normalized entropy = 0.0
    assert result.normalized_entropy == 0.0
    # min == max, so imbalance_ratio = 1.0
    assert result.imbalance_ratio is not None
    assert result.imbalance_ratio == pytest.approx(1.0)


def test_eda_class_distribution_entropy_normalized_range(tmp_path: Path):
    """Normalized entropy is always in [0.0, 1.0] for multi-class distributions."""
    classes = [
        ClassDiscoveryInfo(class_name=f"C{i}", relative_path=f"C{i}", image_count=(i + 1) * 10)
        for i in range(6)
    ]
    imgs = [_make_img(f"C{i}/img_{j}.jpg") for i in range(6) for j in range((i + 1) * 10)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_class_distribution(disc, val, imgs)

    assert result.normalized_entropy is not None
    assert 0.0 <= result.normalized_entropy <= 1.0


def test_eda_class_distribution_imbalance_ratio_undefined_when_min_zero(tmp_path: Path):
    """imbalance_ratio is None when any class has 0 images (min=0 → division undefined)."""
    counts = [0, 50, 100]
    result_gini = _compute_gini(counts)
    result_entropy, norm_e = _compute_entropy(counts)

    classes = [
        ClassDiscoveryInfo(class_name=f"C{i}", relative_path=f"C{i}", image_count=c)
        for i, c in enumerate(counts)
    ]
    imgs = [_make_img(f"C1/img_{j}.jpg") for j in range(50)] + [_make_img(f"C2/img_{j}.jpg") for j in range(100)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_class_distribution(disc, val, imgs)

    assert result.imbalance_ratio is None


def test_eda_gini_perfectly_equal():
    """Gini coefficient is ~0 for perfectly equal distributions."""
    counts = [100, 100, 100, 100]
    gini = _compute_gini(counts)
    assert gini == pytest.approx(0.0, abs=1e-6)


def test_eda_entropy_max_at_equal_distribution():
    """Normalized entropy is 1.0 for perfectly equal distributions."""
    counts = [50, 50, 50, 50]
    entropy, normalized = _compute_entropy(counts)
    assert normalized is not None
    assert normalized == pytest.approx(1.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 2. Dimension Analysis Tests
# ---------------------------------------------------------------------------

def test_eda_dimension_portrait_landscape_square(tmp_path: Path):
    """Images are correctly classified as portrait, landscape, and square."""
    imgs = [
        _make_img("c/p.jpg", width=300, height=600),   # portrait AR=0.5
        _make_img("c/l.jpg", width=1920, height=1080), # landscape AR=1.78
        _make_img("c/s.jpg", width=512, height=512),   # square AR=1.0
    ]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_dimension_analysis(imgs)

    assert result.portrait_count == 1
    assert result.landscape_count == 1
    assert result.square_count == 1
    assert result.portrait_pct == pytest.approx(33.33, rel=0.01)


def test_eda_dimension_missing_metadata(tmp_path: Path):
    """Images with None width/height don't crash and are excluded from stats."""
    imgs = [
        _make_img("c/valid.jpg", width=640, height=480),
        _make_img("c/no_meta.jpg", width=None, height=None),
    ]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_dimension_analysis(imgs)

    # Only 1 image has valid dimensions
    assert result.min_width == 640
    assert result.max_width == 640
    # Square/portrait/landscape counts should still work
    assert result.portrait_count + result.landscape_count + result.square_count == 1


def test_eda_dimension_unique_dimensions(tmp_path: Path):
    """unique_dimensions correctly counts distinct WxH pairs."""
    imgs = [
        _make_img("c/a.jpg", width=100, height=100),
        _make_img("c/b.jpg", width=100, height=100),  # same as above
        _make_img("c/c.jpg", width=200, height=200),
        _make_img("c/d.jpg", width=300, height=150),
    ]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_dimension_analysis(imgs)
    assert result.unique_dimensions == 3


# ---------------------------------------------------------------------------
# 3. Aspect Ratio Tests
# ---------------------------------------------------------------------------

def test_eda_aspect_ratio_extreme_values(tmp_path: Path):
    """Extreme aspect ratios (<0.5 or >2.0) are correctly counted."""
    imgs = [
        _make_img("c/narrow.jpg", width=100, height=400),  # AR=0.25 — very narrow
        _make_img("c/wide.jpg", width=1000, height=200),   # AR=5.0 — very wide
        _make_img("c/normal.jpg", width=640, height=480),  # AR=1.33 — normal
    ]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_aspect_ratio_analysis(imgs)

    assert result.extreme_low_count == 1
    assert result.extreme_high_count == 1
    assert result.min_ar == pytest.approx(0.25, rel=0.01)
    assert result.max_ar == pytest.approx(5.0, rel=0.01)


def test_eda_aspect_ratio_zero_height_protection(tmp_path: Path):
    """Images with height=0 do not cause ZeroDivisionError."""
    imgs = [
        _make_img("c/zero.jpg", width=640, height=0),
        _make_img("c/valid.jpg", width=640, height=480),
    ]
    service = EdaService(backend=LocalStorageBackend())
    # Should not raise
    result = service._compute_aspect_ratio_analysis(imgs)
    assert result.mean_ar is not None
    assert result.mean_ar == pytest.approx(640 / 480, rel=0.01)


def test_eda_aspect_ratio_bins_total(tmp_path: Path):
    """The sum of bin counts equals total images with valid aspect ratios."""
    imgs = [_make_img(f"c/img_{i}.jpg", width=640, height=480) for i in range(10)]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_aspect_ratio_analysis(imgs)
    total_in_bins = sum(b.count for b in result.distribution_bins)
    assert total_in_bins == 10


# ---------------------------------------------------------------------------
# 4. Format Analysis Tests
# ---------------------------------------------------------------------------

def test_eda_format_analysis_single_format(tmp_path: Path):
    """Single format returns unique_format_count=1 and correct most_common."""
    val = _make_validation(formats={"JPEG": 100})
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_format_analysis(val)

    assert result.unique_format_count == 1
    assert result.most_common_format == "JPEG"
    assert result.least_common_format is None  # only 1 format


def test_eda_format_analysis_multiple_formats(tmp_path: Path):
    """Multiple formats produce correct distribution and percentages."""
    val = _make_validation(formats={"JPEG": 80, "PNG": 15, "TIFF": 5})
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_format_analysis(val)

    assert result.unique_format_count == 3
    assert result.most_common_format == "JPEG"
    assert result.least_common_format == "TIFF"
    assert result.format_percentages["JPEG"] == pytest.approx(80.0, rel=0.01)
    assert result.format_percentages["PNG"] == pytest.approx(15.0, rel=0.01)


# ---------------------------------------------------------------------------
# 5. Color Analysis Tests
# ---------------------------------------------------------------------------

def test_eda_color_grayscale_rgb_rgba(tmp_path: Path):
    """Grayscale, RGB, and RGBA images are counted correctly."""
    imgs = [
        _make_img("c/gray.jpg", color_mode="L", fmt="JPEG"),
        _make_img("c/rgb1.jpg", color_mode="RGB", fmt="JPEG"),
        _make_img("c/rgb2.jpg", color_mode="RGB", fmt="JPEG"),
        _make_img("c/rgba.png", color_mode="RGBA", fmt="PNG"),
    ]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_color_analysis(imgs)

    assert result.grayscale_count == 1
    assert result.rgb_count == 2
    assert result.rgba_count == 1
    assert result.color_mode_distribution.get("L", 0) == 1
    assert result.color_mode_distribution.get("RGB", 0) == 2
    assert result.color_mode_distribution.get("RGBA", 0) == 1


def test_eda_color_sampling_no_crash_no_real_files(tmp_path: Path):
    """Color analysis completes without raising even when image files don't exist."""
    imgs = [_make_img(f"c/img_{i}.jpg", color_mode="RGB") for i in range(10)]
    service = EdaService(backend=LocalStorageBackend())
    # Should not raise — files don't exist, pixel sampling will be skipped gracefully
    result = service._compute_color_analysis(imgs, seed=42)
    # rgb_mean may be None (files not on disk) but no crash
    assert isinstance(result.sampling_seed, int)
    assert result.sampling_seed == 42


# ---------------------------------------------------------------------------
# 6. File Size Statistics Tests
# ---------------------------------------------------------------------------

def test_eda_file_size_statistics(tmp_path: Path):
    """Basic file size stats are computed correctly."""
    sizes = [10_000, 20_000, 30_000, 40_000, 50_000]
    imgs = [_make_img(f"c/img_{i}.jpg", file_size_bytes=sizes[i]) for i in range(5)]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_file_size_analysis(imgs)

    assert result.min_bytes == 10_000
    assert result.max_bytes == 50_000
    assert result.total_bytes == sum(sizes)
    assert result.mean_bytes == pytest.approx(30_000.0, rel=0.01)
    assert result.min_human is not None
    assert result.total_human is not None
    assert "KB" in result.min_human or "B" in result.min_human


def test_eda_file_size_bins_sum(tmp_path: Path):
    """Sum of size bin counts equals total image count."""
    imgs = [_make_img(f"c/img_{i}.jpg", file_size_bytes=50_000) for i in range(20)]
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_file_size_analysis(imgs)
    total_in_bins = sum(b.count for b in result.size_distribution_bins)
    assert total_in_bins == 20


def test_eda_file_size_empty_list(tmp_path: Path):
    """Empty image list returns zero total_bytes and all None stats."""
    service = EdaService(backend=LocalStorageBackend())
    result = service._compute_file_size_analysis([])
    assert result.total_bytes == 0
    assert result.min_bytes is None
    assert result.max_bytes is None


# ---------------------------------------------------------------------------
# 7. Findings Tests
# ---------------------------------------------------------------------------

def test_eda_findings_stable_ids(tmp_path: Path):
    """The same input data always produces findings with the same IDs."""
    classes = [
        ClassDiscoveryInfo(class_name="A", relative_path="A", image_count=50),
        ClassDiscoveryInfo(class_name="B", relative_path="B", image_count=50),
    ]
    imgs = [_make_img(f"{'A' if i < 50 else 'B'}/img_{i}.jpg") for i in range(100)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())

    class_dist = service._compute_class_distribution(disc, val, imgs)
    dim = service._compute_dimension_analysis(imgs)
    fmt = service._compute_format_analysis(val)
    color = service._compute_color_analysis(imgs)
    ar = service._compute_aspect_ratio_analysis(imgs)
    fs = service._compute_file_size_analysis(imgs)

    from app.schemas.eda import DatasetOverview
    overview = DatasetOverview(
        dataset_id="test-ds",
        dataset_name="Test Dataset",
        total_discovered_files=100,
        total_valid_images=100,
        total_invalid_images=0,
        class_count=2,
        classes_with_images=2,
        empty_class_count=0,
        format_count=1,
        unique_dimension_count=1,
        total_size_bytes=5_000_000,
        total_size_human="5.0 MB",
        analysis_id=None,
        quality_assessment_id=None,
        eda_methodology_version="v1.0",
    )

    findings_1 = service._generate_findings(overview, class_dist, dim, fmt, color, ar, fs)
    findings_2 = service._generate_findings(overview, class_dist, dim, fmt, color, ar, fs)

    ids_1 = {f.id for f in findings_1}
    ids_2 = {f.id for f in findings_2}
    assert ids_1 == ids_2


def test_eda_findings_empty_class_generates_high_severity(tmp_path: Path):
    """An empty class generates a HIGH severity finding."""
    classes = [
        ClassDiscoveryInfo(class_name="Full", relative_path="Full", image_count=100),
        ClassDiscoveryInfo(class_name="Empty", relative_path="Empty", image_count=0),
    ]
    imgs = [_make_img(f"Full/img_{j}.jpg") for j in range(100)]
    disc = _make_discovery(classes=classes)
    val = _make_validation(images=imgs)
    service = EdaService(backend=LocalStorageBackend())

    class_dist = service._compute_class_distribution(disc, val, imgs)
    dim = service._compute_dimension_analysis(imgs)
    fmt = service._compute_format_analysis(val)
    color = service._compute_color_analysis(imgs)
    ar = service._compute_aspect_ratio_analysis(imgs)
    fs = service._compute_file_size_analysis(imgs)

    from app.schemas.eda import DatasetOverview, EdaSeverity
    overview = DatasetOverview(
        dataset_id="test-ds", dataset_name="Test", total_discovered_files=100,
        total_valid_images=100, total_invalid_images=0, class_count=2,
        classes_with_images=1, empty_class_count=1, format_count=1,
        unique_dimension_count=1, total_size_bytes=5_000_000,
        total_size_human="5.0 MB", analysis_id=None,
        quality_assessment_id=None, eda_methodology_version="v1.0",
    )
    findings = service._generate_findings(overview, class_dist, dim, fmt, color, ar, fs)

    empty_finding = next((f for f in findings if f.id == "eda-finding-empty-classes"), None)
    assert empty_finding is not None
    assert empty_finding.severity == EdaSeverity.HIGH
    assert "Empty" in empty_finding.affected_classes


def test_eda_findings_mixed_formats_generates_finding(tmp_path: Path):
    """Mixed formats generate a 'mixed-formats' finding."""
    val = _make_validation(formats={"JPEG": 80, "PNG": 20})
    imgs = [_make_img(f"c/img_{i}.jpg") for i in range(100)]
    classes = [ClassDiscoveryInfo(class_name="c", relative_path="c", image_count=100)]
    disc = _make_discovery(classes=classes)
    service = EdaService(backend=LocalStorageBackend())

    class_dist = service._compute_class_distribution(disc, val, imgs)
    dim = service._compute_dimension_analysis(imgs)
    fmt = service._compute_format_analysis(val)
    color = service._compute_color_analysis(imgs)
    ar = service._compute_aspect_ratio_analysis(imgs)
    fs = service._compute_file_size_analysis(imgs)

    from app.schemas.eda import DatasetOverview
    overview = DatasetOverview(
        dataset_id="test-ds", dataset_name="Test", total_discovered_files=100,
        total_valid_images=100, total_invalid_images=0, class_count=1,
        classes_with_images=1, empty_class_count=0, format_count=2,
        unique_dimension_count=1, total_size_bytes=5_000_000,
        total_size_human="5.0 MB", analysis_id=None,
        quality_assessment_id=None, eda_methodology_version="v1.0",
    )
    findings = service._generate_findings(overview, class_dist, dim, fmt, color, ar, fs)
    assert any(f.id == "eda-finding-mixed-formats" for f in findings)


# ---------------------------------------------------------------------------
# 8. Persistence and Rehydration Tests
# ---------------------------------------------------------------------------

def test_eda_persistence_and_rehydration(tmp_path: Path):
    """EDA report is persisted to disk and correctly rehydrated by a fresh service instance."""
    from app.core.config import Settings

    cfg = Settings(STORAGE_BASE_DIR=tmp_path, ENVIRONMENT="testing")
    backend_a = LocalStorageBackend(cfg)
    backend_a.initialize()

    # Create a minimal EDA report and save it
    service_a = EdaService(backend=backend_a)
    classes = [
        ClassDiscoveryInfo(class_name="X", relative_path="X", image_count=30),
        ClassDiscoveryInfo(class_name="Y", relative_path="Y", image_count=70),
    ]
    imgs = (
        [_make_img(f"X/img_{j}.jpg") for j in range(30)]
        + [_make_img(f"Y/img_{j}.jpg") for j in range(70)]
    )
    disc = _make_discovery("persist-test", classes=classes)
    val = _make_validation("persist-test", images=imgs)
    analysis = _make_analysis("persist-test", discovery=disc, validation=val)

    # Inject analysis into service so run_eda reuses it
    from app.services.analysis_service import AnalysisService
    ana_service = AnalysisService(backend=backend_a)
    ana_service._analyses[analysis.id] = analysis
    # Patch eda_service to use this analysis_service
    import unittest.mock as mock
    with mock.patch("app.services.eda_service.storage_backend", backend_a):
        service_a._storage = backend_a
        # Directly run internal helpers and build a report
        class_dist = service_a._compute_class_distribution(disc, val, imgs)
        dim = service_a._compute_dimension_analysis(imgs)
        ar = service_a._compute_aspect_ratio_analysis(imgs)
        fmt = service_a._compute_format_analysis(val)
        color = service_a._compute_color_analysis(imgs)
        fs = service_a._compute_file_size_analysis(imgs)
        class_meta = service_a._compute_class_metadata(disc, imgs)

        from app.schemas.eda import DatasetOverview, EdaStatus
        import uuid, datetime
        eda_id = f"eda-persist-test-{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        from app.schemas.eda import DatasetOverview
        overview = DatasetOverview(
            dataset_id="persist-test",
            dataset_name="Test Dataset",
            total_discovered_files=100,
            total_valid_images=100,
            total_invalid_images=0,
            class_count=2,
            classes_with_images=2,
            empty_class_count=0,
            format_count=1,
            unique_dimension_count=1,
            total_size_bytes=5_000_000,
            total_size_human="5.0 MB",
            analysis_id="ana-persist-test-test",
            quality_assessment_id=None,
            eda_methodology_version="v1.0",
        )
        findings = service_a._generate_findings(overview, class_dist, dim, fmt, color, ar, fs)
        report = EdaReport(
            id=eda_id,
            dataset_id="persist-test",
            dataset_name="Test Dataset",
            source_analysis_id="ana-persist-test-test",
            source_quality_assessment_id=None,
            status=EdaStatus.COMPLETED,
            created_at=now,
            completed_at=now,
            duration_ms=100.0,
            methodology_version="v1.0",
            overview=overview,
            class_distribution=class_dist,
            dimension_analysis=dim,
            aspect_ratio_analysis=ar,
            format_analysis=fmt,
            color_analysis=color,
            file_size_analysis=fs,
            class_metadata=class_meta,
            findings=findings,
            warnings=[],
        )
        backend_a.save_eda_report(eda_id, report.model_dump(), dataset_id="persist-test")

    # Fresh service from same backend
    service_b = EdaService(backend=backend_a)
    rehydrated = service_b.get_report(eda_id)
    assert rehydrated is not None
    assert rehydrated.id == eda_id
    assert rehydrated.dataset_id == "persist-test"
    assert rehydrated.status == EdaStatus.COMPLETED

    latest = service_b.get_latest_report_for_dataset("persist-test")
    assert latest is not None
    assert latest.id == eda_id

    listing = service_b.list_reports()
    assert any(item.id == eda_id for item in listing.items)


# ---------------------------------------------------------------------------
# 9. FastAPI Endpoint Tests
# ---------------------------------------------------------------------------

def test_eda_api_dataset_not_found_before_eda(client):
    """GET /api/v1/datasets/{id}/eda returns 404 before any EDA has been run."""
    resp = client.get("/api/v1/datasets/chilli-leaf/eda")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error_code"] == "DATASET_EDA_NOT_FOUND"


def test_eda_api_report_not_found_404(client):
    """GET /api/v1/eda-reports/{eda_id} returns 404 for unknown ID."""
    resp = client.get("/api/v1/eda-reports/eda-nonexistent-id-abc")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error_code"] == "EDA_REPORT_NOT_FOUND"


def test_eda_api_list_returns_list_response(client):
    """GET /api/v1/eda-reports returns correct list structure."""
    resp = client.get("/api/v1/eda-reports")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


def test_eda_api_trigger_and_retrieve_e2e(client):
    """
    Full E2E: POST /analyze to run M2, then POST /eda to run EDA,
    then GET /eda to retrieve, then GET /eda/findings.
    """
    # First run analysis (M2)
    resp_analyze = client.post("/api/v1/datasets/icar-rice-maize/analyze")
    assert resp_analyze.status_code == status.HTTP_200_OK

    # Trigger EDA
    resp_eda = client.post("/api/v1/datasets/icar-rice-maize/eda")
    assert resp_eda.status_code == status.HTTP_200_OK
    eda_data = resp_eda.json()
    eda_id = eda_data["id"]
    assert eda_id.startswith("eda-")
    assert eda_data["status"] == "completed"
    assert "overview" in eda_data
    assert "class_distribution" in eda_data
    assert "dimension_analysis" in eda_data
    assert "aspect_ratio_analysis" in eda_data
    assert "format_analysis" in eda_data
    assert "color_analysis" in eda_data
    assert "file_size_analysis" in eda_data
    assert "findings" in eda_data
    assert isinstance(eda_data["findings"], list)

    # GET dataset EDA
    resp_get = client.get("/api/v1/datasets/icar-rice-maize/eda")
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["id"] == eda_id

    # GET EDA status
    resp_status = client.get(f"/api/v1/datasets/icar-rice-maize/eda/status")
    assert resp_status.status_code == status.HTTP_200_OK
    assert resp_status.json()["eda_id"] == eda_id
    assert resp_status.json()["status"] == "completed"

    # GET EDA findings
    resp_findings = client.get(f"/api/v1/datasets/icar-rice-maize/eda/findings")
    assert resp_findings.status_code == status.HTTP_200_OK
    findings_data = resp_findings.json()
    assert isinstance(findings_data, list)

    # GET by EDA ID from global endpoint
    resp_global = client.get(f"/api/v1/eda-reports/{eda_id}")
    assert resp_global.status_code == status.HTTP_200_OK
    assert resp_global.json()["id"] == eda_id

    # GET global findings
    resp_global_findings = client.get(f"/api/v1/eda-reports/{eda_id}/findings")
    assert resp_global_findings.status_code == status.HTTP_200_OK
    assert isinstance(resp_global_findings.json(), list)

    # LIST global EDA reports
    resp_list = client.get("/api/v1/eda-reports")
    assert resp_list.status_code == status.HTTP_200_OK
    list_data = resp_list.json()
    assert list_data["total"] >= 1
    assert any(item["id"] == eda_id for item in list_data["items"])


def test_eda_no_host_paths_in_response(client):
    """EDA API response must not contain absolute host filesystem paths."""
    # Run analyze first
    client.post("/api/v1/datasets/icar-rice-maize/analyze")
    resp = client.post("/api/v1/datasets/icar-rice-maize/eda")
    assert resp.status_code == status.HTTP_200_OK
    text = resp.text
    assert "/Users/" not in text
    assert "/private/var/" not in text
    assert "\\Users\\" not in text


def test_eda_reuses_existing_report_without_force_refresh(client):
    """Calling POST /eda twice without force_refresh=true reuses the cached report."""
    client.post("/api/v1/datasets/icar-rice-maize/analyze")

    resp1 = client.post("/api/v1/datasets/icar-rice-maize/eda")
    assert resp1.status_code == status.HTTP_200_OK
    id1 = resp1.json()["id"]

    resp2 = client.post("/api/v1/datasets/icar-rice-maize/eda")
    assert resp2.status_code == status.HTTP_200_OK
    id2 = resp2.json()["id"]

    # Same report should be returned
    assert id1 == id2


def test_eda_force_refresh_generates_new_report(client):
    """Calling POST /eda?force_refresh=true generates a new report."""
    client.post("/api/v1/datasets/icar-rice-maize/analyze")

    resp1 = client.post("/api/v1/datasets/icar-rice-maize/eda")
    assert resp1.status_code == status.HTTP_200_OK
    id1 = resp1.json()["id"]

    resp2 = client.post("/api/v1/datasets/icar-rice-maize/eda?force_refresh=true")
    assert resp2.status_code == status.HTTP_200_OK
    id2 = resp2.json()["id"]

    # A fresh report with a new ID should be generated
    assert id2 != id1


def test_eda_global_status_endpoint(client):
    """GET /api/v1/eda-reports/{eda_id}/status returns correct status structure."""
    client.post("/api/v1/datasets/icar-rice-maize/analyze")
    resp = client.post("/api/v1/datasets/icar-rice-maize/eda")
    eda_id = resp.json()["id"]

    resp_status = client.get(f"/api/v1/eda-reports/{eda_id}/status")
    assert resp_status.status_code == status.HTTP_200_OK
    s = resp_status.json()
    assert s["eda_id"] == eda_id
    assert s["status"] == "completed"
    assert "methodology_version" in s
    assert "created_at" in s


def test_eda_dataset_overview_counts(client):
    """EDA overview counts match analysis output: total_valid, total_invalid, class_count."""
    resp_analyze = client.post("/api/v1/datasets/icar-rice-maize/analyze")
    analysis_data = resp_analyze.json()

    resp_eda = client.post("/api/v1/datasets/icar-rice-maize/eda?force_refresh=true")
    eda_data = resp_eda.json()

    overview = eda_data["overview"]
    assert overview["total_valid_images"] == analysis_data["metrics"]["total_validated_images"]
    assert overview["class_count"] == analysis_data["metrics"]["total_classes_discovered"]

