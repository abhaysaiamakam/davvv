"""
Comprehensive pytest test suite for M5: Dataset Comparison Engine.

Tests cover:
- MetricComparison calculation and zero-denominator safety
- Class alignment logic (shared, unique, disjoint, overlap %)
- Statistical comparisons (scale, entropy, gini, imbalance)
- Image characteristic comparisons (dimensions, format, color mode)
- Data quality and duplicate impact comparisons
- Optional M3 / M4 handling (graceful degradation, warnings, availability flags)
- Stable finding generation
- Persistence, pair pointers, and service rehydration
- API endpoint integration via TestClient
- Error handling (self-comparison, missing dataset, missing M2 prerequisite, not found)
- Verification of no host path leaks
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional
import pytest
from fastapi import status

from app.core.errors import (
    ComparisonNotFoundError,
    ComparisonPrerequisiteError,
    SelfComparisonError,
)
from app.schemas.analysis import AnalysisStatus, UnifiedAnalysisMetrics, UnifiedAnalysisResult
from app.schemas.comparison import (
    ComparisonFindingCategory,
    ComparisonSeverity,
    ComparisonStatus,
    DatasetComparisonReport,
    MetricComparison,
)
from app.schemas.dataset import (
    ClassDiscoveryInfo,
    DatasetDiscoveryResult,
    DatasetMetadata,
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
    AspectRatioAnalysis,
    ClassDistributionAnalysis,
    ColorAnalysis,
    DimensionStats,
    EdaReport,
    EdaStatus,
    FileSizeStats,
    FormatAnalysis,
)
from app.schemas.quality import (
    DataQualityAssessment,
    ImageIntegrityAssessment,
    QualityFinding,
    QualityFindingCategory,
    QualitySeverity,
    TransparentQualityScore,
)
from app.services.analysis_service import analysis_service
from app.services.comparison_service import ComparisonService, comparison_service
from app.services.data_quality_service import data_quality_service
from app.services.dataset_service import dataset_service
from app.services.eda_service import eda_service
from app.storage.local import LocalStorageBackend


# ---------------------------------------------------------------------------
# Test Helpers: Synthetic Model Generators
# ---------------------------------------------------------------------------


from tests.test_quality import _make_dummy_analysis


def _make_dummy_dataset(dataset_id: str, name: str = "Test DS") -> DatasetMetadata:
    return DatasetMetadata(
        id=dataset_id,
        name=name,
        slug=dataset_id,
        description="Test dataset description",
        source=DatasetSource.ICAR_RICE_MAIZE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        status=DatasetStatus.READY,
    )


def _make_dummy_quality(
    assessment_id: str,
    dataset_id: str,
    overall_score: float = 85.0,
    quality_tier: str = "good",
) -> DataQualityAssessment:
    ana = _make_dummy_analysis(dataset_id)
    qa = data_quality_service.evaluate_dataset_quality(dataset_id, ana)
    data = qa.model_dump()
    data["id"] = assessment_id
    data["quality_score"]["overall_score"] = overall_score
    data["quality_score"]["quality_tier"] = quality_tier
    return DataQualityAssessment.model_validate(data)


from tests.test_eda import _make_img


def _make_dummy_eda(
    eda_id: str,
    dataset_id: str,
    entropy: float = 1.0,
    gini: float = 0.1,
    imbalance_ratio: float = 1.5,
    median_width: int = 800,
    median_height: int = 600,
) -> EdaReport:
    imgs = [
        _make_img(f"Class_A/img_{i}.jpg", width=median_width, height=median_height)
        for i in range(50)
    ] + [
        _make_img(f"Class_B/img_{i}.jpg", width=median_width, height=median_height)
        for i in range(50)
    ]
    ana = _make_dummy_analysis(dataset_id)
    ana.validation.images = imgs
    # Temporarily set analysis so run_eda picks it up
    orig_fn = analysis_service.get_latest_analysis_for_dataset
    analysis_service.get_latest_analysis_for_dataset = lambda did: ana
    try:
        eda = eda_service.run_eda(dataset_id, force_refresh=True)
    finally:
        analysis_service.get_latest_analysis_for_dataset = orig_fn

    data = eda.model_dump()
    data["id"] = eda_id
    data["class_distribution"]["entropy"] = entropy
    data["class_distribution"]["gini_coefficient"] = gini
    data["class_distribution"]["imbalance_ratio"] = imbalance_ratio
    data["dimension_analysis"]["median_width"] = median_width
    data["dimension_analysis"]["median_height"] = median_height
    return EdaReport.model_validate(data)


# ---------------------------------------------------------------------------
# Unit Tests: MetricComparison
# ---------------------------------------------------------------------------


def test_metric_comparison_normal():
    mc = ComparisonService._make_metric_comparison(100.0, 150.0)
    assert mc.dataset_a_value == 100.0
    assert mc.dataset_b_value == 150.0
    assert mc.absolute_diff == 50.0
    assert mc.pct_change == 50.0
    assert mc.is_available is True


def test_metric_comparison_zero_denominator():
    mc = ComparisonService._make_metric_comparison(0.0, 50.0)
    assert mc.dataset_a_value == 0.0
    assert mc.dataset_b_value == 50.0
    assert mc.absolute_diff == 50.0
    assert mc.pct_change is None
    assert mc.is_available is True


def test_metric_comparison_none_handling():
    mc1 = ComparisonService._make_metric_comparison(None, 50.0)
    assert mc1.absolute_diff is None
    assert mc1.pct_change is None
    assert mc1.is_available is True

    mc2 = ComparisonService._make_metric_comparison(None, None)
    assert mc2.absolute_diff is None
    assert mc2.pct_change is None
    assert mc2.is_available is False


# ---------------------------------------------------------------------------
# Unit Tests: Class Alignment
# ---------------------------------------------------------------------------


def test_class_alignment_identical(storage):
    service = ComparisonService(storage)
    cls_a = [
        ClassDiscoveryInfo(class_name="c1", relative_path="c1", image_count=50),
        ClassDiscoveryInfo(class_name="c2", relative_path="c2", image_count=50),
    ]
    ana_a = _make_dummy_analysis("ds-a", valid=100, classes=cls_a)
    ana_b = _make_dummy_analysis("ds-b", valid=100, classes=cls_a)

    res = service._compare_class_distribution(ana_a, ana_b, None, None)
    align = res.alignment
    assert align.shared_classes == ["c1", "c2"]
    assert align.only_in_a == []
    assert align.only_in_b == []
    assert align.class_overlap_pct == 100.0
    assert len(align.shared_class_comparisons) == 2
    assert align.shared_class_comparisons[0].pct_change == 0.0


def test_class_alignment_disjoint(storage):
    service = ComparisonService(storage)
    cls_a = [ClassDiscoveryInfo(class_name="c1", relative_path="c1", image_count=50)]
    cls_b = [ClassDiscoveryInfo(class_name="c2", relative_path="c2", image_count=50)]
    ana_a = _make_dummy_analysis("ds-a", valid=50, classes=cls_a)
    ana_b = _make_dummy_analysis("ds-b", valid=50, classes=cls_b)

    res = service._compare_class_distribution(ana_a, ana_b, None, None)
    align = res.alignment
    assert align.shared_classes == []
    assert align.only_in_a == ["c1"]
    assert align.only_in_b == ["c2"]
    assert align.class_overlap_pct == 0.0


def test_class_alignment_partial(storage):
    service = ComparisonService(storage)
    cls_a = [
        ClassDiscoveryInfo(class_name="shared", relative_path="shared", image_count=40),
        ClassDiscoveryInfo(class_name="only_a", relative_path="only_a", image_count=60),
    ]
    cls_b = [
        ClassDiscoveryInfo(class_name="shared", relative_path="shared", image_count=80),
        ClassDiscoveryInfo(class_name="only_b", relative_path="only_b", image_count=20),
    ]
    ana_a = _make_dummy_analysis("ds-a", valid=100, classes=cls_a)
    ana_b = _make_dummy_analysis("ds-b", valid=100, classes=cls_b)

    res = service._compare_class_distribution(ana_a, ana_b, None, None)
    align = res.alignment
    assert align.shared_classes == ["shared"]
    assert align.only_in_a == ["only_a"]
    assert align.only_in_b == ["only_b"]
    # 1 shared out of 3 total classes in union = 33.33%
    assert align.class_overlap_pct == 33.33
    assert align.shared_class_comparisons[0].count_a == 40
    assert align.shared_class_comparisons[0].count_b == 80
    assert align.shared_class_comparisons[0].pct_change == 100.0


# ---------------------------------------------------------------------------
# Unit Tests: Overview & Findings
# ---------------------------------------------------------------------------


def test_scale_findings_generation(storage):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-a", valid=100)
    ana_b = _make_dummy_analysis("ds-b", valid=1500)  # 15x larger

    overview = service._compare_overview(ana_a, ana_b)
    class_dist = service._compare_class_distribution(ana_a, ana_b, None, None)
    img_chars = service._compare_image_characteristics(ana_a, ana_b, None, None)
    data_quality = service._compare_data_quality(ana_a, ana_b, None, None)

    findings = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=None,
        quality_b=None,
        eda_a=None,
        eda_b=None,
    )

    finding_ids = [f.id for f in findings]
    assert "cmp-finding-size-difference" in finding_ids
    assert "cmp-finding-size-large-gap" in finding_ids
    assert "cmp-finding-m3-unavailable" in finding_ids
    assert "cmp-finding-m4-unavailable" in finding_ids


def test_quality_and_cross_class_findings(storage, monkeypatch):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-a", valid=100, cross_class=0)
    ana_b = _make_dummy_analysis("ds-b", valid=100, cross_class=3)

    monkeypatch.setattr(
        dataset_service,
        "get_dataset",
        lambda did: _make_dummy_dataset(did, f"Dataset {did}"),
    )
    monkeypatch.setattr(
        analysis_service,
        "get_latest_analysis_for_dataset",
        lambda did: (ana_a if did == "ds-a" else ana_b),
    )

    qa_a_base = data_quality_service.assess_dataset("ds-a", analysis=ana_a, force_refresh=True)
    qa_b_base = data_quality_service.assess_dataset("ds-b", analysis=ana_b, force_refresh=True)

    data_a = qa_a_base.model_dump()
    data_a["quality_score"]["overall_score"] = 95.0
    data_a["quality_score"]["quality_tier"] = "excellent"
    qa_a = DataQualityAssessment.model_validate(data_a)

    data_b = qa_b_base.model_dump()
    data_b["quality_score"]["overall_score"] = 75.0
    data_b["quality_score"]["quality_tier"] = "good"
    qa_b = DataQualityAssessment.model_validate(data_b)

    overview = service._compare_overview(ana_a, ana_b)
    class_dist = service._compare_class_distribution(ana_a, ana_b, None, None)
    img_chars = service._compare_image_characteristics(ana_a, ana_b, None, None)
    data_quality = service._compare_data_quality(ana_a, ana_b, qa_a, qa_b)

    findings = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=qa_a,
        quality_b=qa_b,
        eda_a=None,
        eda_b=None,
    )

    finding_ids = [f.id for f in findings]
    assert "cmp-finding-cross-class-dups-b" in finding_ids
    assert "cmp-finding-quality-score-gap" in finding_ids
    assert "cmp-finding-quality-tier-difference" in finding_ids


# ---------------------------------------------------------------------------
# Persistence & Rehydration Tests
# ---------------------------------------------------------------------------


def test_persistence_and_rehydration(storage, monkeypatch):
    # Save a comparison
    service1 = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-1", valid=100)
    ana_b = _make_dummy_analysis("ds-2", valid=100)

    # Mock dataset service get_dataset using monkeypatch
    monkeypatch.setattr(
        dataset_service,
        "get_dataset",
        lambda did: _make_dummy_dataset(did, f"Dataset {did}"),
    )
    monkeypatch.setattr(
        analysis_service,
        "get_latest_analysis_for_dataset",
        lambda did: (ana_a if did == "ds-1" else ana_b),
    )

    report = service1.run_comparison("ds-1", "ds-2")
    assert report.id.startswith("cmp-ds-1-vs-ds-2")

    # Verify files on disk
    cmp_file = storage.comparison_dir / report.id / "comparison.json"
    assert cmp_file.is_file()

    ptr_file = storage.comparison_dir / "pairs" / "ds-1--ds-2" / "latest.json"
    assert ptr_file.is_file()

    # Rehydrate in a new service instance
    service2 = ComparisonService(storage)
    loaded = service2.get_comparison(report.id)
    assert loaded is not None
    assert loaded.id == report.id
    assert loaded.overview.valid_images.dataset_a_value == 100.0

    # Symmetric pair pointer lookup
    pair_id = storage.get_latest_comparison_id_for_pair("ds-2", "ds-1")
    assert pair_id == report.id


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------


def test_api_self_comparison_error(client):
    resp = client.post(
        "/api/v1/comparisons",
        json={"dataset_a_id": "same-ds", "dataset_b_id": "same-ds"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    data = resp.json()
    assert data["error_code"] == "SELF_COMPARISON_NOT_ALLOWED"


def test_api_missing_dataset_error(client):
    resp = client.post(
        "/api/v1/comparisons",
        json={"dataset_a_id": "non-existent-1", "dataset_b_id": "non-existent-2"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error_code"] == "DATASET_NOT_FOUND"


def test_api_prerequisite_missing_error(client, monkeypatch):
    # Register two fake datasets in dataset_service
    ds1 = _make_dummy_dataset("ds-pre-1", "Pre DS 1")
    ds2 = _make_dummy_dataset("ds-pre-2", "Pre DS 2")

    monkeypatch.setattr(
        dataset_service,
        "get_dataset",
        lambda did: ds1 if did == "ds-pre-1" else (ds2 if did == "ds-pre-2" else None),
    )
    monkeypatch.setattr(
        analysis_service,
        "get_latest_analysis_for_dataset",
        lambda did: None,
    )

    resp = client.post(
        "/api/v1/comparisons",
        json={"dataset_a_id": "ds-pre-1", "dataset_b_id": "ds-pre-2"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["error_code"] == "COMPARISON_PREREQUISITE_MISSING"


def test_api_full_comparison_flow(client, monkeypatch):
    # Setup valid datasets and analyses
    ds1 = _make_dummy_dataset("ds-flow-1", "Flow DS 1")
    ds2 = _make_dummy_dataset("ds-flow-2", "Flow DS 2")

    ana1 = _make_dummy_analysis("ds-flow-1", valid=200)
    ana2 = _make_dummy_analysis("ds-flow-2", valid=300)

    monkeypatch.setattr(
        dataset_service,
        "get_dataset",
        lambda did: ds1 if did == "ds-flow-1" else (ds2 if did == "ds-flow-2" else None),
    )
    monkeypatch.setattr(
        analysis_service,
        "get_latest_analysis_for_dataset",
        lambda did: (ana1 if did == "ds-flow-1" else (ana2 if did == "ds-flow-2" else None)),
    )

    # 1. Run comparison
    resp = client.post(
        "/api/v1/comparisons",
        json={"dataset_a_id": "ds-flow-1", "dataset_b_id": "ds-flow-2"},
    )
    assert resp.status_code == status.HTTP_200_OK
    report = resp.json()
    cmp_id = report["id"]
    assert report["dataset_a_id"] == "ds-flow-1"
    assert report["dataset_b_id"] == "ds-flow-2"
    assert report["overview"]["valid_images"]["dataset_a_value"] == 200.0
    assert report["overview"]["valid_images"]["dataset_b_value"] == 300.0
    assert report["overview"]["valid_images"]["pct_change"] == 50.0

    # 2. Get comparison by ID
    resp_get = client.get(f"/api/v1/comparisons/{cmp_id}")
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["id"] == cmp_id

    # 3. Get status
    resp_st = client.get(f"/api/v1/comparisons/{cmp_id}/status")
    assert resp_st.status_code == status.HTTP_200_OK
    assert resp_st.json()["status"] == "completed"

    # 4. Get findings
    resp_f = client.get(f"/api/v1/comparisons/{cmp_id}/findings")
    assert resp_f.status_code == status.HTTP_200_OK
    assert isinstance(resp_f.json(), list)

    # 5. List comparisons
    resp_list = client.get("/api/v1/comparisons")
    assert resp_list.status_code == status.HTTP_200_OK
    assert resp_list.json()["total"] >= 1

    # 6. Cache hit verification (same ID without force_refresh)
    resp_cached = client.post(
        "/api/v1/comparisons",
        json={"dataset_a_id": "ds-flow-1", "dataset_b_id": "ds-flow-2", "force_refresh": False},
    )
    assert resp_cached.status_code == status.HTTP_200_OK
    assert resp_cached.json()["id"] == cmp_id

    # 7. Force refresh verification (different ID)
    resp_forced = client.post(
        "/api/v1/comparisons",
        json={"dataset_a_id": "ds-flow-1", "dataset_b_id": "ds-flow-2", "force_refresh": True},
    )
    assert resp_forced.status_code == status.HTTP_200_OK
    assert resp_forced.json()["id"] != cmp_id


def test_api_comparison_not_found(client):
    resp = client.get("/api/v1/comparisons/cmp-nonexistent-12345")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error_code"] == "COMPARISON_NOT_FOUND"


# ---------------------------------------------------------------------------
# Additional Comprehensive Unit & Property Tests
# ---------------------------------------------------------------------------


def test_eda_metric_comparisons_and_findings(storage):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-a", valid=100)
    ana_b = _make_dummy_analysis("ds-b", valid=100)

    eda_a = _make_dummy_eda("eda-a", "ds-a", entropy=3.0, gini=0.1, imbalance_ratio=1.0)
    eda_b = _make_dummy_eda("eda-b", "ds-b", entropy=1.2, gini=0.45, imbalance_ratio=8.0)

    overview = service._compare_overview(ana_a, ana_b)
    class_dist = service._compare_class_distribution(ana_a, ana_b, eda_a, eda_b)
    img_chars = service._compare_image_characteristics(ana_a, ana_b, eda_a, eda_b)
    data_quality = service._compare_data_quality(ana_a, ana_b, None, None)

    findings = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=None,
        quality_b=None,
        eda_a=eda_a,
        eda_b=eda_b,
    )

    finding_ids = [f.id for f in findings]
    assert "cmp-finding-entropy-difference" in finding_ids
    assert "cmp-finding-gini-difference" in finding_ids
    assert "cmp-finding-imbalance-gap" in finding_ids


def test_image_characteristics_findings(storage):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-a", valid=100)
    ana_b = _make_dummy_analysis("ds-b", valid=100)

    eda_a = _make_dummy_eda("eda-a", "ds-a", median_width=400, median_height=300)
    eda_b = _make_dummy_eda("eda-b", "ds-b", median_width=1200, median_height=900)
    eda_b.format_analysis.most_common_format = "PNG"

    overview = service._compare_overview(ana_a, ana_b)
    class_dist = service._compare_class_distribution(ana_a, ana_b, eda_a, eda_b)
    img_chars = service._compare_image_characteristics(ana_a, ana_b, eda_a, eda_b)
    data_quality = service._compare_data_quality(ana_a, ana_b, None, None)

    findings = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=None,
        quality_b=None,
        eda_a=eda_a,
        eda_b=eda_b,
    )

    finding_ids = [f.id for f in findings]
    assert "cmp-finding-dimension-median-difference" in finding_ids
    assert "cmp-finding-format-difference" in finding_ids


def test_duplicate_rate_gap_finding(storage):
    service = ComparisonService(storage)
    # A has 2% duplicates, B has 12% duplicates -> gap = 10% > 5%
    ana_a = _make_dummy_analysis("ds-a", valid=100, exact_groups=1, exact_redundant=2)
    ana_b = _make_dummy_analysis("ds-b", valid=100, exact_groups=6, exact_redundant=12)

    overview = service._compare_overview(ana_a, ana_b)
    class_dist = service._compare_class_distribution(ana_a, ana_b, None, None)
    img_chars = service._compare_image_characteristics(ana_a, ana_b, None, None)
    data_quality = service._compare_data_quality(ana_a, ana_b, None, None)

    findings = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=None,
        quality_b=None,
        eda_a=None,
        eda_b=None,
    )

    finding_ids = [f.id for f in findings]
    assert "cmp-finding-duplicate-rate-gap" in finding_ids


def test_missing_upstream_graceful_handling(storage, monkeypatch):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-miss-a", valid=100)
    ana_b = _make_dummy_analysis("ds-miss-b", valid=100)

    monkeypatch.setattr(
        dataset_service,
        "get_dataset",
        lambda did: _make_dummy_dataset(did, f"Dataset {did}"),
    )
    monkeypatch.setattr(
        analysis_service,
        "get_latest_analysis_for_dataset",
        lambda did: (ana_a if did == "ds-miss-a" else ana_b),
    )
    monkeypatch.setattr(
        data_quality_service,
        "get_latest_assessment_for_dataset",
        lambda did: None,
    )
    monkeypatch.setattr(
        eda_service,
        "get_latest_report_for_dataset",
        lambda did: None,
    )

    report = service.run_comparison("ds-miss-a", "ds-miss-b", force_refresh=True)

    assert report.status == ComparisonStatus.COMPLETED
    assert len(report.warnings) >= 2
    assert report.class_distribution.is_available is False
    assert report.image_characteristics.is_available is False
    assert report.data_quality.is_quality_available is False
    assert report.data_quality.is_duplicate_available is True

    finding_ids = [f.id for f in report.findings]
    assert "cmp-finding-m3-unavailable" in finding_ids
    assert "cmp-finding-m4-unavailable" in finding_ids


def test_no_host_paths_in_comparison_report(storage, monkeypatch):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-safe-a", valid=100)
    ana_b = _make_dummy_analysis("ds-safe-b", valid=100)

    monkeypatch.setattr(
        dataset_service,
        "get_dataset",
        lambda did: _make_dummy_dataset(did, f"Dataset {did}"),
    )
    monkeypatch.setattr(
        analysis_service,
        "get_latest_analysis_for_dataset",
        lambda did: (ana_a if did == "ds-safe-a" else ana_b),
    )

    report = service.run_comparison("ds-safe-a", "ds-safe-b", force_refresh=True)
    report_json_str = json.dumps(report.model_dump())

    # Verify no absolute host paths
    assert "/Users/" not in report_json_str
    assert "\\Users\\" not in report_json_str
    assert "/home/" not in report_json_str


def test_empty_classes_detection(storage):
    service = ComparisonService(storage)
    cls_a = [
        ClassDiscoveryInfo(class_name="c1", relative_path="c1", image_count=0),
        ClassDiscoveryInfo(class_name="c2", relative_path="c2", image_count=50),
    ]
    cls_b = [
        ClassDiscoveryInfo(class_name="c2", relative_path="c2", image_count=50),
        ClassDiscoveryInfo(class_name="c3", relative_path="c3", image_count=0),
    ]
    ana_a = _make_dummy_analysis("ds-a", valid=50, classes=cls_a)
    ana_b = _make_dummy_analysis("ds-b", valid=50, classes=cls_b)

    res = service._compare_class_distribution(ana_a, ana_b, None, None)
    assert res.alignment.empty_classes_a == 1
    assert res.alignment.empty_classes_b == 1
    assert res.alignment.shared_classes == ["c2"]


def test_deterministic_findings_and_stable_ids(storage):
    service = ComparisonService(storage)
    ana_a = _make_dummy_analysis("ds-a", valid=100, exact_groups=5, exact_redundant=10)
    ana_b = _make_dummy_analysis("ds-b", valid=1000, exact_groups=0, exact_redundant=0)

    overview = service._compare_overview(ana_a, ana_b)
    class_dist = service._compare_class_distribution(ana_a, ana_b, None, None)
    img_chars = service._compare_image_characteristics(ana_a, ana_b, None, None)
    data_quality = service._compare_data_quality(ana_a, ana_b, None, None)

    findings_run1 = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=None,
        quality_b=None,
        eda_a=None,
        eda_b=None,
    )
    findings_run2 = service._generate_findings(
        overview=overview,
        class_dist=class_dist,
        img_chars=img_chars,
        data_quality=data_quality,
        analysis_a=ana_a,
        analysis_b=ana_b,
        quality_a=None,
        quality_b=None,
        eda_a=None,
        eda_b=None,
    )

    ids1 = [f.id for f in findings_run1]
    ids2 = [f.id for f in findings_run2]
    assert ids1 == ids2
    # Ensure all finding IDs are stable literals, none contains uuid
    for fid in ids1:
        assert fid.startswith("cmp-finding-")
        assert len(fid) < 50

