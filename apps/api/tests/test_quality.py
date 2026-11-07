import random
from pathlib import Path
import pytest
from fastapi import status
from PIL import Image

from app.schemas.analysis import AnalysisStatus, UnifiedAnalysisMetrics, UnifiedAnalysisResult
from app.schemas.dataset import (
    ClassDiscoveryInfo,
    DatasetDiscoveryResult,
    DatasetMetadata,
    DatasetSource,
    DatasetStatus,
    DatasetValidationResult,
    DimensionSummary,
    DuplicateAnalysisResult,
    ExactDuplicateGroup,
    DuplicateImageMember,
    ImageValidationRecord,
    NearDuplicateAnalysisResult,
    NearDuplicateGroup,
    NearDuplicateMember,
    ValidationStatus,
)
from app.schemas.quality import (
    QualityFindingCategory,
    QualitySeverity,
)
from app.services.data_quality_service import DataQualityService, data_quality_service
from app.services.dataset_service import dataset_service
from app.storage.local import LocalStorageBackend


# ---------------------------------------------------------------------------
# Test Helpers: Synthetic Model Generators
# ---------------------------------------------------------------------------

def _make_dummy_analysis(
    dataset_id: str = "test-ds",
    discovered: int = 100,
    valid: int = 100,
    corrupted: int = 0,
    classes: list = None,
    exact_groups: int = 0,
    exact_redundant: int = 0,
    near_groups: int = 0,
    near_redundant: int = 0,
    cross_class: int = 0,
    formats: dict = None,
    min_ar: float = 1.0,
    max_ar: float = 1.33,
    min_w: int = 500,
    min_h: int = 500,
) -> UnifiedAnalysisResult:
    now = "2026-11-07T12:00:00Z"
    if classes is None:
        classes = [
            ClassDiscoveryInfo(class_name="Class_A", relative_path="Class_A", image_count=50),
            ClassDiscoveryInfo(class_name="Class_B", relative_path="Class_B", image_count=50),
        ]

    disc_res = DatasetDiscoveryResult(
        dataset_id=dataset_id,
        dataset_name="Test DS",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        dataset_root_relative_path=f"curated/{dataset_id}",
        discovery_status=DatasetStatus.DISCOVERED,
        discovered_image_files=discovered,
        discovered_class_directories=len(classes),
        classes=classes,
        ingestion_timestamp=now,
    )

    dim_summary = DimensionSummary(
        min_width=min_w,
        max_width=1000,
        mean_width=750.0,
        min_height=min_h,
        max_height=1000,
        mean_height=750.0,
        min_aspect_ratio=min_ar,
        max_aspect_ratio=max_ar,
    )

    val_res = DatasetValidationResult(
        dataset_id=dataset_id,
        dataset_name="Test DS",
        dataset_source=DatasetSource.ICAR_RICE_MAIZE,
        validation_status=DatasetStatus.VALIDATED,
        total_discovered_images=discovered,
        total_validated_images=valid,
        total_corrupted_images=corrupted,
        total_unreadable_images=0,
        total_processing_errors=0,
        total_unsupported_files=0,
        validation_timestamp=now,
        dimension_summary=dim_summary,
        format_distribution=formats or {"JPEG": valid},
        color_mode_distribution={"RGB": valid},
    )

    exact_res = DuplicateAnalysisResult(
        dataset_id=dataset_id,
        dataset_name="Test DS",
        analysis_timestamp=now,
        total_eligible_images=valid,
        successfully_hashed_images=valid,
        unique_content_groups=valid - exact_redundant,
        exact_duplicate_groups=exact_groups,
        duplicate_instances_count=exact_redundant,
        images_in_duplicate_groups=exact_groups * 2,
        duplicate_percentage=round((exact_redundant / valid) * 100.0, 2) if valid > 0 else 0.0,
        cross_class_duplicate_groups=cross_class,
    )

    near_res = NearDuplicateAnalysisResult(
        dataset_id=dataset_id,
        dataset_name="Test DS",
        analysis_timestamp=now,
        algorithm="phash",
        hash_size=8,
        distance_threshold=10,
        similarity_threshold=0.8438,
        total_eligible_images=valid,
        successfully_hashed_images=valid,
        unique_perceptual_hashes=valid - near_redundant,
        exact_duplicates_collapsed_count=exact_redundant,
        unique_content_representatives_compared=valid - exact_redundant,
        pairwise_comparisons_performed=100,
        near_duplicate_groups=near_groups,
        images_in_near_duplicate_groups=near_groups * 2,
        redundant_near_duplicate_instances=near_redundant,
        near_duplicate_percentage=round((near_redundant / valid) * 100.0, 2) if valid > 0 else 0.0,
        cross_class_near_duplicate_groups=cross_class,
        analysis_duration_ms=500.0,
    )

    total_red = exact_redundant + near_redundant
    metrics = UnifiedAnalysisMetrics(
        total_files_discovered=discovered,
        total_classes_discovered=len(classes),
        total_validated_images=valid,
        total_corrupted_images=corrupted,
        exact_duplicate_groups=exact_groups,
        exact_duplicate_redundant_instances=exact_redundant,
        exact_duplicate_percentage=exact_res.duplicate_percentage,
        near_duplicate_groups=near_groups,
        near_duplicate_images_in_groups=near_groups * 2,
        near_duplicate_redundant_instances=near_redundant,
        near_duplicate_percentage=near_res.near_duplicate_percentage,
        total_redundant_images=total_red,
        clean_unique_images=(valid - total_red),
        cross_class_exact_duplicate_groups=cross_class,
        cross_class_near_duplicate_groups=cross_class,
    )

    return UnifiedAnalysisResult(
        id=f"ana-{dataset_id}-001",
        dataset_id=dataset_id,
        dataset_name="Test DS",
        status=AnalysisStatus.COMPLETED,
        created_at=now,
        completed_at=now,
        duration_ms=1000.0,
        stages_completed=["discovery", "validation", "exact_duplicates", "near_duplicates"],
        metrics=metrics,
        discovery=disc_res,
        validation=val_res,
        exact_duplicates=exact_res,
        near_duplicates=near_res,
    )


# ---------------------------------------------------------------------------
# 1. Image Integrity Tests
# ---------------------------------------------------------------------------

def test_integrity_flawless_dataset(tmp_path: Path):
    """When all files are valid and 0 corrupted, integrity rate is 100% and status is flawless."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(discovered=100, valid=100, corrupted=0)
    findings = []
    eval_res = service._evaluate_integrity(analysis, findings)

    assert eval_res.status == "flawless"
    assert eval_res.integrity_rate == 100.0
    assert eval_res.total_corrupted_images == 0
    assert any(f.id == "qa-finding-integrity-clean" for f in findings)


def test_integrity_with_corrupted_images(tmp_path: Path):
    """Corrupted images generate a high-severity finding and reduce integrity rate."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(discovered=100, valid=96, corrupted=4)
    findings = []
    eval_res = service._evaluate_integrity(analysis, findings)

    assert eval_res.status == "minor_corruption"
    assert eval_res.integrity_rate == 96.0
    assert eval_res.total_corrupted_images == 4
    corrupt_finding = next(f for f in findings if f.id == "qa-finding-integrity-corrupted")
    assert corrupt_finding.severity == QualitySeverity.HIGH
    assert corrupt_finding.observed_value == 4


def test_integrity_uncomputed_when_validation_missing():
    """Missing validation results must report uncomputed/unavailable without fabricating 0."""
    service = DataQualityService(backend=LocalStorageBackend())
    now = "2026-11-07T12:00:00Z"
    analysis = UnifiedAnalysisResult(
        id="ana-noval-001",
        dataset_id="noval",
        dataset_name="No Validation DS",
        status=AnalysisStatus.COMPLETED,
        created_at=now,
        stages_completed=["discovery"],
        metrics=UnifiedAnalysisMetrics(total_files_discovered=50),
    )
    findings = []
    eval_res = service._evaluate_integrity(analysis, findings)

    assert eval_res.status == "uncomputed"
    assert eval_res.is_available is False
    assert eval_res.integrity_rate is None
    assert eval_res.total_validated_images is None


# ---------------------------------------------------------------------------
# 2. Class Imbalance Tests
# ---------------------------------------------------------------------------

def test_imbalance_perfectly_balanced():
    """Equal distribution across classes results in balanced status and low CV."""
    service = DataQualityService(backend=LocalStorageBackend())
    classes = [
        ClassDiscoveryInfo(class_name="Rice_Blight", relative_path="Rice/Blight", image_count=50),
        ClassDiscoveryInfo(class_name="Rice_BrownSpot", relative_path="Rice/BrownSpot", image_count=50),
        ClassDiscoveryInfo(class_name="Rice_Healthy", relative_path="Rice/Healthy", image_count=50),
    ]
    analysis = _make_dummy_analysis(classes=classes)
    findings = []
    imbalance = service._evaluate_imbalance(analysis, findings)

    assert imbalance.imbalance_severity == "balanced"
    assert imbalance.imbalance_ratio == 1.0
    assert imbalance.coefficient_of_variation == 0.0
    assert len(imbalance.empty_classes) == 0
    assert any(f.id == "qa-finding-imbalance-balanced" for f in findings)


def test_imbalance_severely_imbalanced():
    """Severe disparity (e.g. 100 vs 10 images) triggers severely_imbalanced classification."""
    service = DataQualityService(backend=LocalStorageBackend())
    classes = [
        ClassDiscoveryInfo(class_name="Majority_Class", relative_path="Maj", image_count=100),
        ClassDiscoveryInfo(class_name="Minority_Class", relative_path="Min", image_count=10),
    ]
    analysis = _make_dummy_analysis(classes=classes)
    findings = []
    imbalance = service._evaluate_imbalance(analysis, findings)

    assert imbalance.imbalance_severity == "severely_imbalanced"
    assert imbalance.imbalance_ratio == 10.0
    assert imbalance.min_class_count == 10
    assert imbalance.max_class_count == 100
    assert len(imbalance.underrepresented_classes) >= 1
    finding = next(f for f in findings if f.id == "qa-finding-imbalance-severe")
    assert finding.severity == QualitySeverity.HIGH


def test_imbalance_with_empty_class():
    """Empty classes (0 images) are detected, recorded, and flagged with critical severity."""
    service = DataQualityService(backend=LocalStorageBackend())
    classes = [
        ClassDiscoveryInfo(class_name="Populated_A", relative_path="A", image_count=40),
        ClassDiscoveryInfo(class_name="Empty_B", relative_path="B", image_count=0),
    ]
    analysis = _make_dummy_analysis(classes=classes)
    findings = []
    imbalance = service._evaluate_imbalance(analysis, findings)

    assert imbalance.imbalance_severity == "severely_imbalanced"
    assert "Empty_B" in imbalance.empty_classes
    assert imbalance.classes_with_images == 1
    empty_finding = next(f for f in findings if f.id == "qa-finding-imbalance-empty-classes")
    assert empty_finding.severity == QualitySeverity.CRITICAL


def test_imbalance_single_class_dataset():
    """A dataset with only 1 class is defined as balanced without division-by-zero crashes."""
    service = DataQualityService(backend=LocalStorageBackend())
    classes = [
        ClassDiscoveryInfo(class_name="Sole_Class", relative_path="Sole", image_count=80),
    ]
    analysis = _make_dummy_analysis(classes=classes)
    findings = []
    imbalance = service._evaluate_imbalance(analysis, findings)

    assert imbalance.total_classes == 1
    assert imbalance.imbalance_severity == "balanced"
    assert imbalance.coefficient_of_variation == 0.0


# ---------------------------------------------------------------------------
# 3. Metadata Consistency Tests
# ---------------------------------------------------------------------------

def test_consistency_homogeneous_dimensions():
    """Uniform dimensions and single format yield high consistency score."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(min_ar=1.0, max_ar=1.33, min_w=640, min_h=480, formats={"JPEG": 100})
    findings = []
    consistency = service._evaluate_consistency(analysis, findings)

    assert consistency.is_available is True
    assert consistency.consistency_rate == 100.0
    assert consistency.aspect_ratio_outliers_count == 0
    assert consistency.small_dimension_images_count == 0
    assert any(f.id == "qa-finding-consistency-high" for f in findings)


def test_consistency_mixed_formats_and_extreme_aspect_ratios():
    """Mixed formats and aspect ratio outliers generate findings."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(
        min_ar=0.35,  # extreme portrait outlier < 0.5
        max_ar=2.5,   # extreme banner outlier > 2.2
        min_w=150,    # small dimension < 224
        formats={"JPEG": 70, "PNG": 30},
    )
    findings = []
    consistency = service._evaluate_consistency(analysis, findings)

    assert len(consistency.format_distribution) == 2
    assert consistency.aspect_ratio_outliers_count > 0
    assert consistency.small_dimension_images_count > 0
    assert any(f.id == "qa-finding-consistency-mixed-formats" for f in findings)
    assert any(f.id == "qa-finding-consistency-aspect-outliers" for f in findings)
    assert any(f.id == "qa-finding-consistency-small-dimensions" for f in findings)


# ---------------------------------------------------------------------------
# 4. Duplicate Impact Tests
# ---------------------------------------------------------------------------

def test_duplicate_impact_zero_duplicates():
    """Zero duplicates yields 'none' severity and 100% clean uniqueness."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(exact_groups=0, exact_redundant=0, near_groups=0, near_redundant=0)
    findings = []
    dup_eval = service._evaluate_duplicates(analysis, findings)

    assert dup_eval.duplicate_impact_severity == "none"
    assert dup_eval.total_redundant_images == 0
    assert dup_eval.clean_unique_images == 100
    assert any(f.id == "qa-finding-duplicates-none" for f in findings)


def test_duplicate_impact_exact_and_near_combined():
    """Verifies exact + near duplicates are consolidated without double-counting."""
    service = DataQualityService(backend=LocalStorageBackend())
    # 5 exact redundant + 5 near redundant in a 100-image dataset
    analysis = _make_dummy_analysis(
        valid=100,
        exact_groups=5,
        exact_redundant=5,
        near_groups=5,
        near_redundant=5,
    )
    findings = []
    dup_eval = service._evaluate_duplicates(analysis, findings)

    assert dup_eval.exact_duplicate_redundant_instances == 5
    assert dup_eval.near_duplicate_redundant_instances == 5
    assert dup_eval.total_redundant_images == 10  # 5 + 5
    assert dup_eval.clean_unique_images == 90     # 100 - 10
    assert dup_eval.duplicate_impact_severity == "moderate"  # 10% falls in [5%, 15%)


def test_duplicate_impact_cross_class_hazard():
    """Cross-class duplicates trigger CRITICAL severity finding."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(exact_groups=2, exact_redundant=2, near_groups=2, near_redundant=2, cross_class=1)
    findings = []
    dup_eval = service._evaluate_duplicates(analysis, findings)

    assert dup_eval.cross_class_duplicate_groups == 2  # 1 exact + 1 near
    cross_finding = next(f for f in findings if f.id == "qa-finding-duplicates-cross-class")
    assert cross_finding.severity == QualitySeverity.CRITICAL


# ---------------------------------------------------------------------------
# 5. Transparent Quality Score & Reproducibility Tests
# ---------------------------------------------------------------------------

def test_quality_score_bounds_and_weights():
    """Score must strictly reside in [0.0, 100.0] and weights must sum to 1.0."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(valid=100, corrupted=0, exact_redundant=10, near_redundant=5)
    findings = []
    integ = service._evaluate_integrity(analysis, findings)
    imb = service._evaluate_imbalance(analysis, findings)
    cons = service._evaluate_consistency(analysis, findings)
    dups = service._evaluate_duplicates(analysis, findings)

    score = service._calculate_quality_score(integ, imb, cons, dups)

    assert 0.0 <= score.overall_score <= 100.0
    assert sum(score.weight_configuration.values()) == pytest.approx(1.0, 0.001)
    assert "integrity" in score.components
    assert "uniqueness" in score.components
    assert "balance" in score.components
    assert "consistency" in score.components
    assert score.methodology_version == "v1.0"


def test_quality_score_deterministic_reproducibility():
    """Identical input analysis must produce the exact same score across repeated calls."""
    service = DataQualityService(backend=LocalStorageBackend())
    analysis = _make_dummy_analysis(valid=100, corrupted=2, exact_redundant=4, near_redundant=3)

    score_1 = service._calculate_quality_score(
        service._evaluate_integrity(analysis, []),
        service._evaluate_imbalance(analysis, []),
        service._evaluate_consistency(analysis, []),
        service._evaluate_duplicates(analysis, []),
    )
    score_2 = service._calculate_quality_score(
        service._evaluate_integrity(analysis, []),
        service._evaluate_imbalance(analysis, []),
        service._evaluate_consistency(analysis, []),
        service._evaluate_duplicates(analysis, []),
    )

    assert score_1.overall_score == score_2.overall_score
    assert score_1.quality_tier == score_2.quality_tier
    for k in score_1.components:
        assert score_1.components[k].score == score_2.components[k].score


# ---------------------------------------------------------------------------
# 6. Persistence & Server Restart Rehydration Tests
# ---------------------------------------------------------------------------

def test_quality_assessment_persistence_and_rehydration(tmp_path: Path):
    """
    Test that quality assessment results are persisted to disk and survive
    service reinitialization (simulating server restart).
    """
    backend = LocalStorageBackend()
    backend.base_path = tmp_path
    backend.initialize()

    # Create dummy dataset directory and register
    curated_dir = backend.curated_dir / "m3-persist-ds"
    c_dir = curated_dir / "Rice" / "healthy"
    c_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (300, 300), color=(0, 128, 0))
    img.save(c_dir / "leaf.jpg", "JPEG")

    test_ds = DatasetMetadata(
        id="m3-persist-ds",
        name="M3 Persist Dataset",
        slug="m3-persist-ds",
        description="Dataset for testing quality persistence",
        source=DatasetSource.ICAR_RICE_MAIZE,
        is_curated=True,
        is_uploaded=False,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        crops=["Rice"],
        status=DatasetStatus.REGISTERED,
        storage_relative_path="curated/m3-persist-ds",
    )
    dataset_service._curated_registry.append(test_ds)

    service_a = DataQualityService(backend=backend)
    assessment = service_a.assess_dataset("m3-persist-ds")

    assert assessment.status == AnalysisStatus.COMPLETED
    assessment_id = assessment.id

    # Verify result file exists on disk
    persisted_file = backend.quality_dir / assessment_id / "assessment.json"
    assert persisted_file.exists()
    assert persisted_file.stat().st_size > 0

    # Simulate server restart with fresh service instance B
    service_b = DataQualityService(backend=backend)
    rehydrated = service_b.get_assessment(assessment_id)

    assert rehydrated is not None
    assert rehydrated.id == assessment_id
    assert rehydrated.dataset_id == "m3-persist-ds"
    assert rehydrated.quality_score.overall_score == assessment.quality_score.overall_score

    # Check latest lookup
    latest = service_b.get_latest_assessment_for_dataset("m3-persist-ds")
    assert latest is not None
    assert latest.id == assessment_id

    # Check list endpoint reflects it
    listing = service_b.list_assessments()
    assert any(item.id == assessment_id for item in listing.items)


# ---------------------------------------------------------------------------
# 7. FastAPI Quality Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_quality_endpoints_e2e(client):
    """
    Test full API workflow:
    1. POST /api/v1/datasets/m3-persist-ds/quality-assessments
    2. GET /api/v1/datasets/m3-persist-ds/quality-assessment
    3. GET /api/v1/datasets/m3-persist-ds/quality-assessment/status
    4. GET /api/v1/datasets/m3-persist-ds/quality-assessment/findings
    5. GET /api/v1/quality-assessments/{assessment_id}
    6. GET /api/v1/quality-assessments
    """
    # 1. Trigger quality assessment
    resp_trigger = client.post("/api/v1/datasets/m3-persist-ds/quality-assessments")
    assert resp_trigger.status_code == status.HTTP_200_OK
    data = resp_trigger.json()
    assessment_id = data["id"]
    assert assessment_id.startswith("qa-")
    assert "quality_score" in data
    assert "findings" in data
    assert "integrity" in data
    assert "imbalance" in data
    assert "duplicate_impact" in data

    # 2. Get latest assessment for dataset
    resp_latest = client.get("/api/v1/datasets/m3-persist-ds/quality-assessment")
    assert resp_latest.status_code == status.HTTP_200_OK
    assert resp_latest.json()["id"] == assessment_id

    # 3. Get latest status for dataset
    resp_status = client.get("/api/v1/datasets/m3-persist-ds/quality-assessment/status")
    assert resp_status.status_code == status.HTTP_200_OK
    status_data = resp_status.json()
    assert status_data["assessment_id"] == assessment_id
    assert status_data["status"] == "completed"

    # 4. Get findings for dataset
    resp_findings = client.get("/api/v1/datasets/m3-persist-ds/quality-assessment/findings")
    assert resp_findings.status_code == status.HTTP_200_OK
    findings_list = resp_findings.json()
    assert isinstance(findings_list, list)

    # 5. Get by ID
    resp_get = client.get(f"/api/v1/quality-assessments/{assessment_id}")
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["id"] == assessment_id

    # 6. List all assessments
    resp_list = client.get("/api/v1/quality-assessments")
    assert resp_list.status_code == status.HTTP_200_OK
    list_data = resp_list.json()
    assert list_data["total"] >= 1
    assert any(item["id"] == assessment_id for item in list_data["items"])


def test_api_quality_assessment_not_found(client):
    """Querying an unknown assessment ID returns 404."""
    resp = client.get("/api/v1/quality-assessments/qa-nonexistent-id")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error_code"] == "QUALITY_ASSESSMENT_NOT_FOUND"


def test_api_dataset_quality_not_found_before_assessment(client):
    """Querying quality assessment for an unassessed dataset returns 404."""
    resp = client.get("/api/v1/datasets/chilli-leaf/quality-assessment")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error_code"] == "DATASET_QUALITY_ASSESSMENT_NOT_FOUND"


def test_no_host_paths_in_quality_response(client):
    """Verify that no absolute host filesystem paths leak in quality API response."""
    resp = client.get("/api/v1/datasets/m3-persist-ds/quality-assessment")
    assert resp.status_code == status.HTTP_200_OK
    text_content = resp.text
    assert "/Users/" not in text_content
    assert "/private/var/" not in text_content
    assert "\\Users\\" not in text_content
