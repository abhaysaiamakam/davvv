import logging
import math
import statistics
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.errors import DatasetNotFoundError
from app.schemas.analysis import AnalysisStatus, UnifiedAnalysisResult
from app.schemas.quality import (
    ClassImbalanceAssessment,
    DataQualityAssessment,
    DuplicateImpactAssessment,
    ImageIntegrityAssessment,
    MetadataConsistencyAssessment,
    QualityAssessmentListResponse,
    QualityAssessmentStatusResponse,
    QualityAssessmentSummary,
    QualityFinding,
    QualityFindingCategory,
    QualityScoreComponent,
    QualitySeverity,
    TransparentQualityScore,
)
from app.storage.base import StorageBackend
from app.storage.local import storage_backend

logger = logging.getLogger(__name__)


class DataQualityService:
    """
    Core intelligence service for M3 Data Quality Lab.
    Consumes unified M2 pipeline outputs and produces:
      1. Image Integrity assessment
      2. Class Imbalance assessment
      3. Image Metadata Consistency assessment
      4. Duplicate Impact assessment
      5. Transparent, explainable, versioned Quality Scoring
      6. Evidence-backed actionable Quality Findings
      7. Persistence and retrieval
    """

    METHODOLOGY_VERSION = "v1.0"

    def __init__(self, backend: Optional[StorageBackend] = None):
        self.storage: StorageBackend = backend or storage_backend
        self._assessments: Dict[str, DataQualityAssessment] = {}
        self._rehydrate_from_storage()

    def _rehydrate_from_storage(self) -> None:
        """Load persisted quality assessments from storage into in-memory cache."""
        try:
            persisted = self.storage.list_persisted_quality_assessments()
            for record in persisted:
                try:
                    assessment = DataQualityAssessment.model_validate(record)
                    self._assessments[assessment.id] = assessment
                except Exception as parse_err:
                    logger.warning(
                        f"Failed to parse persisted quality assessment {record.get('id')}: {parse_err}"
                    )
        except Exception as exc:
            logger.warning(f"Error rehydrating quality assessments from storage: {exc}")

    def list_assessments(self) -> QualityAssessmentListResponse:
        """Return list of all quality assessment summaries, newest first."""
        items: List[QualityAssessmentSummary] = []
        for assessment in self._assessments.values():
            crit_count = sum(1 for f in assessment.findings if f.severity == QualitySeverity.CRITICAL)
            high_count = sum(1 for f in assessment.findings if f.severity == QualitySeverity.HIGH)
            items.append(
                QualityAssessmentSummary(
                    id=assessment.id,
                    dataset_id=assessment.dataset_id,
                    status=assessment.status,
                    created_at=assessment.created_at,
                    completed_at=assessment.completed_at,
                    overall_score=assessment.quality_score.overall_score,
                    quality_tier=assessment.quality_score.quality_tier,
                    findings_count=len(assessment.findings),
                    critical_findings_count=crit_count,
                    high_findings_count=high_count,
                )
            )

        items.sort(key=lambda s: str(s.created_at), reverse=True)
        return QualityAssessmentListResponse(
            total=len(items),
            items=items,
            note="Data Quality Lab assessments." if items else "No assessments executed yet.",
        )

    def get_assessment(self, assessment_id: str) -> Optional[DataQualityAssessment]:
        """Retrieve a specific quality assessment by ID from cache or storage."""
        if assessment_id in self._assessments:
            return self._assessments[assessment_id]

        data = self.storage.load_quality_assessment(assessment_id)
        if data:
            try:
                assessment = DataQualityAssessment.model_validate(data)
                self._assessments[assessment.id] = assessment
                return assessment
            except Exception as parse_err:
                logger.error(f"Failed to validate loaded quality assessment {assessment_id}: {parse_err}")
                return None
        return None

    def get_latest_assessment_for_dataset(self, dataset_id: str) -> Optional[DataQualityAssessment]:
        """Retrieve latest quality assessment for a dataset."""
        latest_id = self.storage.get_latest_quality_assessment_id_for_dataset(dataset_id)
        if latest_id:
            res = self.get_assessment(latest_id)
            if res:
                return res

        # Fallback: scan in-memory cache
        matching = [
            a for a in self._assessments.values()
            if a.dataset_id == dataset_id or getattr(a, "dataset_id", "") == dataset_id
        ]
        if matching:
            matching.sort(key=lambda r: str(r.created_at), reverse=True)
            return matching[0]

        return None

    def get_assessment_status(self, assessment_id: str) -> Optional[QualityAssessmentStatusResponse]:
        """Retrieve status details for an assessment."""
        assessment = self.get_assessment(assessment_id)
        if not assessment:
            return None

        return QualityAssessmentStatusResponse(
            assessment_id=assessment.id,
            dataset_id=assessment.dataset_id,
            status=assessment.status,
            created_at=assessment.created_at,
            completed_at=assessment.completed_at,
            duration_ms=assessment.duration_ms,
            methodology_version=assessment.methodology_version,
            error_message=None if assessment.status == AnalysisStatus.COMPLETED else "Assessment incomplete or failed",
        )

    # -----------------------------------------------------------------------
    # Assessment Generation Workflow
    # -----------------------------------------------------------------------

    def assess_dataset(
        self,
        dataset_id: str,
        analysis: Optional[UnifiedAnalysisResult] = None,
        force_refresh: bool = False,
    ) -> DataQualityAssessment:
        """
        Execute comprehensive data quality assessment on a dataset.
        Consumes existing M2 analysis results or executes unified analysis if missing.
        """
        from app.services.analysis_service import analysis_service
        from app.services.dataset_service import dataset_service

        dataset = dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise DatasetNotFoundError(dataset_id)

        t_start = time.perf_counter()
        now = datetime.now(timezone.utc).isoformat()
        assessment_id = f"qa-{dataset.slug}-{uuid.uuid4().hex[:10]}"

        # Obtain base analysis outputs (reuse or trigger)
        if analysis is None:
            if not force_refresh:
                analysis = analysis_service.get_latest_analysis_for_dataset(dataset.id)
            if analysis is None:
                logger.info(f"Triggering unified analysis for dataset {dataset.id} before quality assessment")
                analysis = analysis_service.run_analysis(dataset.id)

        findings: List[QualityFinding] = []
        warnings: List[str] = list(analysis.warnings)

        # 1. Image Integrity Assessment
        integrity_eval = self._evaluate_integrity(analysis, findings)

        # 2. Class Imbalance Assessment
        imbalance_eval = self._evaluate_imbalance(analysis, findings)

        # 3. Metadata Consistency Assessment
        consistency_eval = self._evaluate_consistency(analysis, findings)

        # 4. Duplicate Impact Assessment
        duplicate_eval = self._evaluate_duplicates(analysis, findings)

        # 5. Transparent Quality Scoring
        quality_score = self._calculate_quality_score(
            integrity=integrity_eval,
            imbalance=imbalance_eval,
            consistency=consistency_eval,
            duplicates=duplicate_eval,
        )

        # 6. Executive Summary Narrative
        summary = self._generate_executive_summary(
            dataset_name=dataset.name,
            score=quality_score,
            integrity=integrity_eval,
            imbalance=imbalance_eval,
            duplicates=duplicate_eval,
            consistency=consistency_eval,
            findings=findings,
        )

        duration_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

        assessment = DataQualityAssessment(
            id=assessment_id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            source_analysis_id=analysis.id if analysis else None,
            status=AnalysisStatus.COMPLETED,
            created_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            methodology_version=self.METHODOLOGY_VERSION,
            integrity=integrity_eval,
            imbalance=imbalance_eval,
            metadata_consistency=consistency_eval,
            duplicate_impact=duplicate_eval,
            quality_score=quality_score,
            findings=findings,
            summary=summary,
            warnings=warnings,
        )

        # Persist assessment to storage
        try:
            self.storage.save_quality_assessment(
                assessment_id=assessment.id,
                data=assessment.model_dump(),
                dataset_id=dataset.id,
            )
        except Exception as persist_err:
            logger.error(f"Failed to persist quality assessment {assessment.id}: {persist_err}")
            assessment.warnings.append(f"Persistence error: {persist_err}")

        self._assessments[assessment.id] = assessment
        return assessment

    # -----------------------------------------------------------------------
    # Dimension 1: Image Integrity Evaluation
    # -----------------------------------------------------------------------

    def _evaluate_integrity(
        self,
        analysis: UnifiedAnalysisResult,
        findings: List[QualityFinding],
    ) -> ImageIntegrityAssessment:
        m = analysis.metrics
        val = analysis.validation

        disc_count = m.total_files_discovered
        valid_count = m.total_validated_images
        corrupt_count = m.total_corrupted_images
        unreadable_count = m.total_unreadable_images
        proc_errors = m.total_processing_errors
        unsupported_count = m.total_unsupported_files

        notes = []

        if valid_count is None:
            notes.append("Validation stage was not executed or produced no results.")
            return ImageIntegrityAssessment(
                total_discovered_images=disc_count,
                total_validated_images=None,
                total_corrupted_images=None,
                total_unreadable_images=None,
                total_processing_errors=None,
                total_unsupported_files=None,
                integrity_rate=None,
                status="uncomputed",
                is_available=False,
                evaluation_notes=notes,
            )

        total_tested = valid_count + (corrupt_count or 0) + (unreadable_count or 0) + (proc_errors or 0)
        if total_tested > 0:
            rate = round((valid_count / total_tested) * 100.0, 2)
        elif valid_count == 0:
            rate = 0.0
        else:
            rate = 100.0

        if (corrupt_count or 0) == 0 and (unreadable_count or 0) == 0 and (proc_errors or 0) == 0:
            status_desc = "flawless"
            notes.append("All discovered image files successfully passed byte-level integrity verification.")
            findings.append(
                QualityFinding(
                    id="qa-finding-integrity-clean",
                    category=QualityFindingCategory.INTEGRITY,
                    severity=QualitySeverity.INFO,
                    title="100% Image Integrity Confirmed",
                    explanation=f"All {valid_count} discovered images were decoded and verified without corruption or truncation.",
                    metric_name="integrity_rate",
                    observed_value=100.0,
                    expected_value=100.0,
                    threshold_used="rate == 100.0",
                    recommended_action="No image repair or file purging required.",
                    evidence_references=[f"validation.total_validated_images={valid_count}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )
        elif rate >= 95.0:
            status_desc = "minor_corruption"
            notes.append(f"{corrupt_count or 0} corrupted files detected ({round(100.0 - rate, 2)}% of dataset).")
            corrupted_samples = []
            if val and val.corrupted_files:
                corrupted_samples = [f.relative_path for f in val.corrupted_files[:5]]

            findings.append(
                QualityFinding(
                    id="qa-finding-integrity-corrupted",
                    category=QualityFindingCategory.INTEGRITY,
                    severity=QualitySeverity.HIGH,
                    title=f"Detected {corrupt_count} Corrupted or Unreadable Image Files",
                    explanation=f"Found {corrupt_count} images that failed decoding, have broken headers, or contain zero bytes.",
                    metric_name="corrupted_image_count",
                    observed_value=corrupt_count,
                    expected_value=0,
                    threshold_used="corrupt_count > 0",
                    affected_image_samples=corrupted_samples,
                    recommended_action="Quarantine or remove corrupted files to prevent data pipeline or DataLoader crashes during training.",
                    evidence_references=[f"validation.corrupted_image_count={corrupt_count}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )
        else:
            status_desc = "severe_corruption"
            notes.append(f"Severe corruption detected: integrity rate is {rate}%.")
            findings.append(
                QualityFinding(
                    id="qa-finding-integrity-severe",
                    category=QualityFindingCategory.INTEGRITY,
                    severity=QualitySeverity.CRITICAL,
                    title=f"Severe Image Corruption: {round(100.0 - rate, 2)}% Failure Rate",
                    explanation=f"Only {rate}% of files ({valid_count}/{total_tested}) can be decoded.",
                    metric_name="integrity_rate",
                    observed_value=rate,
                    expected_value=100.0,
                    threshold_used="rate < 95.0",
                    recommended_action="Immediate source dataset re-ingestion required. Check storage extraction or transfer corruption.",
                    evidence_references=[f"validation.total_corrupted_images={corrupt_count}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        return ImageIntegrityAssessment(
            total_discovered_images=disc_count,
            total_validated_images=valid_count,
            total_corrupted_images=corrupt_count,
            total_unreadable_images=unreadable_count,
            total_processing_errors=proc_errors,
            total_unsupported_files=unsupported_count,
            integrity_rate=rate,
            status=status_desc,
            is_available=True,
            evaluation_notes=notes,
        )

    # -----------------------------------------------------------------------
    # Dimension 2: Class Imbalance Evaluation
    # -----------------------------------------------------------------------

    def _evaluate_imbalance(
        self,
        analysis: UnifiedAnalysisResult,
        findings: List[QualityFinding],
    ) -> ClassImbalanceAssessment:
        disc = analysis.discovery
        notes = []

        if not disc or not disc.classes:
            notes.append("No class discovery data available for imbalance evaluation.")
            return ClassImbalanceAssessment(
                total_classes=0,
                classes_with_images=0,
                empty_classes=[],
                min_class_count=None,
                max_class_count=None,
                mean_class_count=None,
                median_class_count=None,
                std_class_count=None,
                imbalance_ratio=None,
                coefficient_of_variation=None,
                imbalance_severity="undefined",
                underrepresented_classes=[],
                overrepresented_classes=[],
                class_distribution={},
                evaluation_notes=notes,
            )

        # Distinguish non-class root artifacts (like `.` or `_root_`) as notes
        class_dist: Dict[str, int] = {}
        for c in disc.classes:
            class_dist[c.class_name] = c.image_count

        total_classes = len(class_dist)
        empty_classes = [name for name, count in class_dist.items() if count == 0]
        non_empty_counts = [count for count in class_dist.values() if count > 0]
        classes_with_images = len(non_empty_counts)

        if not non_empty_counts:
            notes.append("Dataset has zero images across all discovered directories.")
            return ClassImbalanceAssessment(
                total_classes=total_classes,
                classes_with_images=0,
                empty_classes=empty_classes,
                min_class_count=0,
                max_class_count=0,
                mean_class_count=0.0,
                median_class_count=0.0,
                std_class_count=0.0,
                imbalance_ratio=None,
                coefficient_of_variation=None,
                imbalance_severity="undefined",
                underrepresented_classes=[],
                overrepresented_classes=[],
                class_distribution=class_dist,
                evaluation_notes=notes,
            )

        min_cnt = min(non_empty_counts)
        max_cnt = max(non_empty_counts)
        mean_cnt = round(float(statistics.mean(non_empty_counts)), 2)
        median_cnt = round(float(statistics.median(non_empty_counts)), 2)
        std_cnt = round(float(statistics.stdev(non_empty_counts)), 2) if len(non_empty_counts) > 1 else 0.0

        cv = round(std_cnt / mean_cnt, 4) if mean_cnt > 0 else 0.0

        # Mathematical definition of ratio: undefined if min_cnt is 0
        if min_cnt > 0:
            imbalance_ratio = round(float(max_cnt / min_cnt), 2)
        else:
            imbalance_ratio = None
            notes.append("Imbalance ratio mathematically undefined because minimum class count is 0.")

        # Outlier detection:
        # Underrepresented: count < median * 0.5 or (count < mean - 1.5 * std and std > 5)
        # Overrepresented: count > median * 2.0 or (count > mean + 1.5 * std and std > 5)
        underrepresented = []
        overrepresented = []

        for name, count in class_dist.items():
            if count == 0:
                continue
            if count < median_cnt * 0.5 or (count < mean_cnt - 1.5 * std_cnt and std_cnt > 3):
                underrepresented.append({
                    "class_name": name,
                    "image_count": count,
                    "deficit_from_median": round(median_cnt - count, 1),
                })
            elif count > median_cnt * 2.0 or (count > mean_cnt + 1.5 * std_cnt and std_cnt > 3):
                overrepresented.append({
                    "class_name": name,
                    "image_count": count,
                    "excess_over_median": round(count - median_cnt, 1),
                })

        # Categorical Severity Classification Rule:
        if len(class_dist) <= 1:
            severity = "balanced"
            notes.append("Single-class dataset is classified as balanced by definition.")
        elif empty_classes:
            severity = "severely_imbalanced"
            notes.append(f"{len(empty_classes)} class directories contain 0 images.")
        elif imbalance_ratio is not None and (imbalance_ratio > 4.0 or cv > 0.6):
            severity = "severely_imbalanced"
            notes.append(f"Imbalance ratio {imbalance_ratio}x exceeds high threshold (4.0x) or CV ({cv}) > 0.6.")
        elif imbalance_ratio is not None and (imbalance_ratio > 1.8 or cv > 0.25):
            severity = "moderately_imbalanced"
            notes.append(f"Imbalance ratio {imbalance_ratio}x exceeds moderate threshold (1.8x).")
        else:
            severity = "balanced"
            notes.append(f"Class distribution is well-balanced across {total_classes} classes (ratio: {imbalance_ratio}x, CV: {cv}).")

        # Generate Evidence-Backed Findings
        if empty_classes:
            findings.append(
                QualityFinding(
                    id="qa-finding-imbalance-empty-classes",
                    category=QualityFindingCategory.IMBALANCE,
                    severity=QualitySeverity.CRITICAL,
                    title=f"{len(empty_classes)} Empty Class Directories Found",
                    explanation=f"Directories {', '.join(empty_classes[:3])} contain zero valid images, which can crash multi-class loss functions.",
                    metric_name="empty_classes_count",
                    observed_value=len(empty_classes),
                    expected_value=0,
                    threshold_used="empty_classes > 0",
                    affected_classes=empty_classes,
                    recommended_action="Remove empty class folders or populate them with labeled samples prior to training split generation.",
                    evidence_references=[f"discovery.empty_classes={empty_classes}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        if severity == "severely_imbalanced":
            affected = [c["class_name"] for c in underrepresented + overrepresented]
            findings.append(
                QualityFinding(
                    id="qa-finding-imbalance-severe",
                    category=QualityFindingCategory.IMBALANCE,
                    severity=QualitySeverity.HIGH,
                    title=f"Severe Class Imbalance Detected (Ratio {imbalance_ratio}x)",
                    explanation=f"Largest class ({max_cnt} images) is {imbalance_ratio}x larger than smallest ({min_cnt} images). CV={cv}.",
                    metric_name="imbalance_ratio",
                    observed_value=imbalance_ratio,
                    expected_value=1.0,
                    threshold_used="imbalance_ratio > 4.0 or cv > 0.6",
                    affected_classes=affected,
                    recommended_action="Apply stratified sampling, class-weighted cross-entropy loss, or focal loss to mitigate majority class bias.",
                    evidence_references=[
                        f"min_count={min_cnt}",
                        f"max_count={max_cnt}",
                        f"median={median_cnt}",
                    ],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )
        elif severity == "moderately_imbalanced":
            affected = [c["class_name"] for c in underrepresented]
            findings.append(
                QualityFinding(
                    id="qa-finding-imbalance-moderate",
                    category=QualityFindingCategory.IMBALANCE,
                    severity=QualitySeverity.MEDIUM,
                    title=f"Moderate Class Imbalance Detected ({imbalance_ratio}x Ratio)",
                    explanation=f"Class distribution varies from {min_cnt} to {max_cnt} images around a median of {median_cnt}.",
                    metric_name="imbalance_ratio",
                    observed_value=imbalance_ratio,
                    expected_value=1.0,
                    threshold_used="1.8 < imbalance_ratio <= 4.0",
                    affected_classes=affected,
                    recommended_action="Monitor per-class recall metrics during model validation to ensure minority classes are recognized.",
                    evidence_references=[f"imbalance_ratio={imbalance_ratio}", f"cv={cv}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )
        elif severity == "balanced" and total_classes > 1:
            findings.append(
                QualityFinding(
                    id="qa-finding-imbalance-balanced",
                    category=QualityFindingCategory.IMBALANCE,
                    severity=QualitySeverity.INFO,
                    title="Equally Balanced Class Representation",
                    explanation=f"Dataset exhibits uniform class distribution across {total_classes} classes (CV: {cv}).",
                    metric_name="coefficient_of_variation",
                    observed_value=cv,
                    expected_value=0.0,
                    threshold_used="cv <= 0.25 and ratio <= 1.8",
                    recommended_action="Standard cross-validation and unweighted loss functions are suitable.",
                    evidence_references=[f"imbalance_ratio={imbalance_ratio}", f"cv={cv}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        return ClassImbalanceAssessment(
            total_classes=total_classes,
            classes_with_images=classes_with_images,
            empty_classes=empty_classes,
            min_class_count=min_cnt,
            max_class_count=max_cnt,
            mean_class_count=mean_cnt,
            median_class_count=median_cnt,
            std_class_count=std_cnt,
            imbalance_ratio=imbalance_ratio,
            coefficient_of_variation=cv,
            imbalance_severity=severity,
            underrepresented_classes=underrepresented,
            overrepresented_classes=overrepresented,
            class_distribution=class_dist,
            evaluation_notes=notes,
        )

    # -----------------------------------------------------------------------
    # Dimension 3: Image Metadata Consistency Evaluation
    # -----------------------------------------------------------------------

    def _evaluate_consistency(
        self,
        analysis: UnifiedAnalysisResult,
        findings: List[QualityFinding],
    ) -> MetadataConsistencyAssessment:
        val = analysis.validation
        notes = []

        if not val or not val.dimension_summary:
            notes.append("No dimensional metadata available from validation pipeline.")
            return MetadataConsistencyAssessment(
                min_width=None,
                max_width=None,
                mean_width=None,
                std_width=None,
                min_height=None,
                max_height=None,
                mean_height=None,
                std_height=None,
                min_aspect_ratio=None,
                max_aspect_ratio=None,
                mean_aspect_ratio=None,
                format_distribution={},
                color_mode_distribution={},
                aspect_ratio_outliers_count=0,
                small_dimension_images_count=0,
                consistency_rate=None,
                is_available=False,
                evaluation_notes=notes,
            )

        ds = val.dimension_summary
        formats = val.format_distribution or {}
        color_modes = val.color_mode_distribution or {}
        total_valid = val.total_validated_images

        # Check aspect ratio boundaries (standard agricultural photography is typically 0.6 to 1.8)
        min_ar = ds.min_aspect_ratio
        max_ar = ds.max_aspect_ratio
        mean_ar = round((min_ar + max_ar) / 2.0, 4) if (min_ar and max_ar) else None

        ar_outliers = 0
        small_dims = 0

        # Scan detailed image records if available in validation result
        if val.images:
            for img in val.images:
                if img.width and img.height:
                    if img.width < 224 or img.height < 224:
                        small_dims += 1
                if img.aspect_ratio is not None:
                    if img.aspect_ratio < 0.5 or img.aspect_ratio > 2.2:
                        ar_outliers += 1
        else:
            # Estimate from dimension summary if per-image records omitted
            if min_ar is not None and min_ar < 0.5:
                ar_outliers += 1
            if max_ar is not None and max_ar > 2.2:
                ar_outliers += 1
            if ds.min_width is not None and ds.min_width < 224:
                small_dims += 1

        total_inconsistencies = ar_outliers + small_dims
        if total_valid > 0:
            consistency_rate = round(max(0.0, 100.0 - (total_inconsistencies / total_valid) * 100.0), 2)
        else:
            consistency_rate = 100.0

        # Format consistency check
        if len(formats) > 1:
            notes.append(f"Multiple image formats detected: {', '.join(formats.keys())}.")
            findings.append(
                QualityFinding(
                    id="qa-finding-consistency-mixed-formats",
                    category=QualityFindingCategory.METADATA,
                    severity=QualitySeverity.LOW,
                    title="Heterogeneous Image File Formats Detected",
                    explanation=f"Dataset contains mixed formats: {dict(formats)}. Standardizing formats avoids decoding discrepancies.",
                    metric_name="format_distribution_count",
                    observed_value=len(formats),
                    expected_value=1,
                    threshold_used="len(formats) > 1",
                    recommended_action="Normalize all images to JPEG/RGB or WebP during preprocessing pipeline.",
                    evidence_references=[f"formats={dict(formats)}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        # Aspect ratio outlier check
        if ar_outliers > 0:
            notes.append(f"{ar_outliers} images exhibit unusual aspect ratios (< 0.5 or > 2.2).")
            findings.append(
                QualityFinding(
                    id="qa-finding-consistency-aspect-outliers",
                    category=QualityFindingCategory.CONSISTENCY,
                    severity=QualitySeverity.MEDIUM,
                    title=f"{ar_outliers} Images with Extreme Aspect Ratios Detected",
                    explanation=f"Observed aspect ratios range from {min_ar} to {max_ar}. Extreme ratios risk distortion when resized to square CNN inputs.",
                    metric_name="aspect_ratio_outliers_count",
                    observed_value=ar_outliers,
                    expected_value=0,
                    threshold_used="aspect_ratio < 0.5 or aspect_ratio > 2.2",
                    recommended_action="Use aspect-ratio-preserving padding (letterboxing) rather than direct scaling during training transforms.",
                    evidence_references=[f"min_ar={min_ar}", f"max_ar={max_ar}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        # Small dimension check
        if small_dims > 0:
            notes.append(f"{small_dims} images have dimensions smaller than 224px.")
            findings.append(
                QualityFinding(
                    id="qa-finding-consistency-small-dimensions",
                    category=QualityFindingCategory.CONSISTENCY,
                    severity=QualitySeverity.HIGH,
                    title=f"{small_dims} Low-Resolution Images Under 224px",
                    explanation="Images with dimensions below standard CNN inputs (224x224) may lose fine foliar disease features upon upscaling.",
                    metric_name="small_dimension_images_count",
                    observed_value=small_dims,
                    expected_value=0,
                    threshold_used="width < 224 or height < 224",
                    recommended_action="Inspect low-resolution images for sufficient diagnostic visual features or filter them out.",
                    evidence_references=[f"min_width={ds.min_width}", f"min_height={ds.min_height}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        if not findings or all(f.category != QualityFindingCategory.CONSISTENCY for f in findings):
            findings.append(
                QualityFinding(
                    id="qa-finding-consistency-high",
                    category=QualityFindingCategory.CONSISTENCY,
                    severity=QualitySeverity.INFO,
                    title="High Dimensional Consistency",
                    explanation=f"Over {consistency_rate}% of images exhibit consistent aspect ratios and resolution.",
                    metric_name="consistency_rate",
                    observed_value=consistency_rate,
                    expected_value=100.0,
                    threshold_used="consistency_rate >= 95.0",
                    recommended_action="Direct batch resizing with standard transforms is safe.",
                    evidence_references=[f"mean_width={ds.mean_width}", f"mean_height={ds.mean_height}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        return MetadataConsistencyAssessment(
            min_width=ds.min_width,
            max_width=ds.max_width,
            mean_width=ds.mean_width,
            std_width=None,
            min_height=ds.min_height,
            max_height=ds.max_height,
            mean_height=ds.mean_height,
            std_height=None,
            min_aspect_ratio=min_ar,
            max_aspect_ratio=max_ar,
            mean_aspect_ratio=mean_ar,
            format_distribution=formats,
            color_mode_distribution=color_modes,
            aspect_ratio_outliers_count=ar_outliers,
            small_dimension_images_count=small_dims,
            consistency_rate=consistency_rate,
            is_available=True,
            evaluation_notes=notes,
        )

    # -----------------------------------------------------------------------
    # Dimension 4: Duplicate Impact Evaluation
    # -----------------------------------------------------------------------

    def _evaluate_duplicates(
        self,
        analysis: UnifiedAnalysisResult,
        findings: List[QualityFinding],
    ) -> DuplicateImpactAssessment:
        m = analysis.metrics
        notes = []

        exact_groups = m.exact_duplicate_groups
        exact_redundant = m.exact_duplicate_redundant_instances
        exact_pct = m.exact_duplicate_percentage
        cross_class_exact = m.cross_class_exact_duplicate_groups or 0

        near_groups = m.near_duplicate_groups
        near_images = m.near_duplicate_images_in_groups
        near_redundant = m.near_duplicate_redundant_instances
        near_pct = m.near_duplicate_percentage
        cross_class_near = m.cross_class_near_duplicate_groups or 0

        total_redundant = m.total_redundant_images
        clean_unique = m.clean_unique_images
        total_valid = m.total_validated_images or 0

        if exact_groups is None and near_groups is None:
            notes.append("Duplicate detection was not performed.")
            return DuplicateImpactAssessment(
                exact_duplicate_groups=None,
                exact_duplicate_redundant_instances=None,
                exact_duplicate_percentage=None,
                near_duplicate_groups=None,
                near_duplicate_images_in_groups=None,
                near_duplicate_redundant_instances=None,
                near_duplicate_percentage=None,
                cross_class_duplicate_groups=None,
                total_redundant_images=None,
                clean_unique_images=None,
                duplicate_impact_severity="uncomputed",
                classes_affected_count=0,
                class_duplicate_breakdown={},
                is_available=False,
                evaluation_notes=notes,
            )

        # Cross-class duplicates across both exact and near
        total_cross_class = cross_class_exact + cross_class_near

        # Combined redundancy severity classification
        red_count = total_redundant or 0
        if total_valid > 0:
            red_pct = round((red_count / total_valid) * 100.0, 2)
        else:
            red_pct = 0.0

        if red_count == 0:
            severity = "none"
            notes.append("Zero exact or perceptual near-duplicates detected.")
            findings.append(
                QualityFinding(
                    id="qa-finding-duplicates-none",
                    category=QualityFindingCategory.DUPLICATES,
                    severity=QualitySeverity.INFO,
                    title="Zero Duplicate Redundancy Detected",
                    explanation="No exact byte-identical copies or near-duplicate perceptual clusters were identified.",
                    metric_name="total_redundant_images",
                    observed_value=0,
                    expected_value=0,
                    threshold_used="total_redundant_images == 0",
                    recommended_action="Dataset has optimal sample uniqueness; no deduplication purging required.",
                    evidence_references=["exact_duplicate_groups=0", "near_duplicate_groups=0"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )
        elif red_pct < 5.0:
            severity = "low"
            notes.append(f"Low duplicate impact: {red_count} redundant images ({red_pct}% of valid images).")
        elif red_pct < 15.0:
            severity = "moderate"
            notes.append(f"Moderate duplicate impact: {red_count} redundant images ({red_pct}% of valid images).")
        else:
            severity = "severe"
            notes.append(f"High duplicate impact: {red_count} redundant images ({red_pct}% of valid images).")

        # Compile per-class duplicate impact
        class_dups: Dict[str, int] = {}
        if analysis.exact_duplicates and analysis.exact_duplicates.class_metrics:
            for cname, cmetric in analysis.exact_duplicates.class_metrics.items():
                class_dups[cname] = class_dups.get(cname, 0) + cmetric.duplicate_instances
        if analysis.near_duplicates and analysis.near_duplicates.class_metrics:
            for cname, cmetric in analysis.near_duplicates.class_metrics.items():
                class_dups[cname] = class_dups.get(cname, 0) + cmetric.near_duplicate_instances

        classes_affected = len([k for k, v in class_dups.items() if v > 0])

        # Generate Evidence-Backed Findings for duplicates
        if total_cross_class > 0:
            findings.append(
                QualityFinding(
                    id="qa-finding-duplicates-cross-class",
                    category=QualityFindingCategory.DUPLICATES,
                    severity=QualitySeverity.CRITICAL,
                    title=f"{total_cross_class} Cross-Class Duplicate Group(s) Detected",
                    explanation=(
                        f"Identical or near-identical images reside under multiple distinct disease/class folders "
                        f"({cross_class_exact} exact, {cross_class_near} near). This introduces direct label contamination."
                    ),
                    metric_name="cross_class_duplicate_groups",
                    observed_value=total_cross_class,
                    expected_value=0,
                    threshold_used="cross_class_duplicate_groups > 0",
                    recommended_action="Purge or re-label cross-class duplicate images immediately to prevent false training supervision.",
                    evidence_references=[
                        f"cross_class_exact={cross_class_exact}",
                        f"cross_class_near={cross_class_near}",
                    ],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        if exact_groups and exact_groups > 0:
            findings.append(
                QualityFinding(
                    id="qa-finding-duplicates-exact",
                    category=QualityFindingCategory.DUPLICATES,
                    severity=QualitySeverity.MEDIUM,
                    title=f"{exact_groups} Exact Duplicate Groups ({exact_redundant} Redundant Copies)",
                    explanation=(
                        f"Found {exact_groups} exact SHA-256 duplicate clusters representing {exact_redundant} "
                        f"redundant file copies ({exact_pct}% of valid images)."
                    ),
                    metric_name="exact_duplicate_redundant_instances",
                    observed_value=exact_redundant,
                    expected_value=0,
                    threshold_used="exact_duplicate_redundant_instances > 0",
                    recommended_action="Deduplicate exact copies retaining only canonical representatives to save disk and compute.",
                    evidence_references=[f"exact_groups={exact_groups}", f"exact_redundant={exact_redundant}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        if near_groups and near_groups > 0:
            findings.append(
                QualityFinding(
                    id="qa-finding-duplicates-near",
                    category=QualityFindingCategory.DUPLICATES,
                    severity=QualitySeverity.LOW if red_pct < 5.0 else QualitySeverity.MEDIUM,
                    title=f"{near_groups} Perceptual Near-Duplicate Groups Detected",
                    explanation=(
                        f"Found {near_groups} perceptual clusters containing {near_images} images with {near_redundant} "
                        f"visually redundant copies ({near_pct}% of valid images)."
                    ),
                    metric_name="near_duplicate_redundant_instances",
                    observed_value=near_redundant,
                    expected_value=0,
                    threshold_used="near_duplicate_redundant_instances > 0",
                    recommended_action="Review near-duplicate clusters before train/validation splitting to avoid data leakage.",
                    evidence_references=[f"near_groups={near_groups}", f"near_redundant={near_redundant}"],
                    methodology_version=self.METHODOLOGY_VERSION,
                )
            )

        return DuplicateImpactAssessment(
            exact_duplicate_groups=exact_groups,
            exact_duplicate_redundant_instances=exact_redundant,
            exact_duplicate_percentage=exact_pct,
            near_duplicate_groups=near_groups,
            near_duplicate_images_in_groups=near_images,
            near_duplicate_redundant_instances=near_redundant,
            near_duplicate_percentage=near_pct,
            cross_class_duplicate_groups=total_cross_class,
            total_redundant_images=total_redundant,
            clean_unique_images=clean_unique,
            duplicate_impact_severity=severity,
            classes_affected_count=classes_affected,
            class_duplicate_breakdown=class_dups,
            is_available=True,
            evaluation_notes=notes,
        )

    # -----------------------------------------------------------------------
    # Dimension 5: Transparent Quality Score Calculation
    # -----------------------------------------------------------------------

    def _calculate_quality_score(
        self,
        integrity: ImageIntegrityAssessment,
        imbalance: ClassImbalanceAssessment,
        consistency: MetadataConsistencyAssessment,
        duplicates: DuplicateImpactAssessment,
    ) -> TransparentQualityScore:
        """
        Calculate reproducible, fully transparent quality score on a 0.0 - 100.0 scale.
        
        Components:
          1. Image Integrity (25% weight): Ratio of decodable valid images to evaluated.
          2. Image Uniqueness (30% weight): Ratio of clean unique images to valid images.
          3. Class Balance    (25% weight): Uniformity of class distribution penalized by dispersion and empty classes.
          4. Consistency      (20% weight): Ratio of images within standard resolution and aspect ratio bounds.
        """
        weights = {
            "integrity": 0.25,
            "uniqueness": 0.30,
            "balance": 0.25,
            "consistency": 0.20,
        }

        # 1. Integrity Component (0-100)
        if integrity.is_available and integrity.integrity_rate is not None:
            integrity_val = min(100.0, max(0.0, integrity.integrity_rate))
            integrity_exp = f"{integrity_val}% of files passed byte-level decodability and corruption checks."
            integrity_metrics = {"integrity_rate": integrity.integrity_rate, "corrupted": integrity.total_corrupted_images}
        else:
            integrity_val = 50.0  # conservative baseline when uncomputed
            integrity_exp = "Integrity uncomputed; conservative baseline applied."
            integrity_metrics = {"status": "uncomputed"}

        # 2. Uniqueness Component (0-100)
        if duplicates.is_available and duplicates.clean_unique_images is not None and duplicates.total_redundant_images is not None:
            total_valid = (duplicates.clean_unique_images + duplicates.total_redundant_images)
            if total_valid > 0:
                uniqueness_val = round((duplicates.clean_unique_images / total_valid) * 100.0, 2)
            else:
                uniqueness_val = 100.0
            uniqueness_exp = f"{uniqueness_val}% of valid images are clean and non-redundant (deduplication yield: {100.0 - uniqueness_val}%)."
            uniqueness_metrics = {
                "clean_unique_images": duplicates.clean_unique_images,
                "total_redundant_images": duplicates.total_redundant_images,
                "uniqueness_rate": uniqueness_val,
            }
        else:
            uniqueness_val = 50.0
            uniqueness_exp = "Duplicate detection uncomputed; conservative baseline applied."
            uniqueness_metrics = {"status": "uncomputed"}

        # 3. Class Balance Component (0-100)
        if imbalance.classes_with_images > 0:
            if imbalance.total_classes <= 1:
                balance_val = 100.0
                balance_exp = "Single-class dataset has no multi-class imbalance."
            else:
                # Dispersion penalty: cv of 0.0 -> 100, cv of 1.0 -> 0
                cv = imbalance.coefficient_of_variation or 0.0
                base_balance = max(0.0, 1.0 - cv) * 100.0
                # Penalty for empty classes
                empty_penalty = (len(imbalance.empty_classes) / imbalance.total_classes) * 50.0
                balance_val = round(max(0.0, min(100.0, base_balance - empty_penalty)), 2)
                balance_exp = f"Dispersion factor: {round(max(0.0, 1.0 - cv), 2)} based on CV {cv}; empty class penalty: {empty_penalty}."
            balance_metrics = {
                "coefficient_of_variation": imbalance.coefficient_of_variation,
                "imbalance_ratio": imbalance.imbalance_ratio,
                "empty_classes_count": len(imbalance.empty_classes),
            }
        else:
            balance_val = 0.0
            balance_exp = "No class samples discovered."
            balance_metrics = {"total_classes": imbalance.total_classes}

        # 4. Consistency Component (0-100)
        if consistency.is_available and consistency.consistency_rate is not None:
            consistency_val = min(100.0, max(0.0, consistency.consistency_rate))
            consistency_exp = f"{consistency_val}% of images adhere to resolution (>=224px) and aspect ratio (0.5 - 2.2) standards."
            consistency_metrics = {
                "consistency_rate": consistency.consistency_rate,
                "aspect_ratio_outliers": consistency.aspect_ratio_outliers_count,
                "small_dimensions": consistency.small_dimension_images_count,
            }
        else:
            consistency_val = 50.0
            consistency_exp = "Consistency uncomputed; baseline applied."
            consistency_metrics = {"status": "uncomputed"}

        components = {
            "integrity": QualityScoreComponent(
                name="Image Integrity",
                score=integrity_val,
                weight=weights["integrity"],
                weighted_score=round(integrity_val * weights["integrity"], 2),
                explanation=integrity_exp,
                metrics_used=integrity_metrics,
            ),
            "uniqueness": QualityScoreComponent(
                name="Sample Uniqueness",
                score=uniqueness_val,
                weight=weights["uniqueness"],
                weighted_score=round(uniqueness_val * weights["uniqueness"], 2),
                explanation=uniqueness_exp,
                metrics_used=uniqueness_metrics,
            ),
            "balance": QualityScoreComponent(
                name="Class Distribution Balance",
                score=balance_val,
                weight=weights["balance"],
                weighted_score=round(balance_val * weights["balance"], 2),
                explanation=balance_exp,
                metrics_used=balance_metrics,
            ),
            "consistency": QualityScoreComponent(
                name="Metadata & Dimension Consistency",
                score=consistency_val,
                weight=weights["consistency"],
                weighted_score=round(consistency_val * weights["consistency"], 2),
                explanation=consistency_exp,
                metrics_used=consistency_metrics,
            ),
        }

        overall_score = round(
            sum(c.weighted_score for c in components.values()), 2
        )
        overall_score = min(100.0, max(0.0, overall_score))

        if overall_score >= 90.0:
            tier = "excellent"
        elif overall_score >= 75.0:
            tier = "good"
        elif overall_score >= 60.0:
            tier = "fair"
        elif overall_score >= 40.0:
            tier = "poor"
        else:
            tier = "critical"

        explanation = (
            f"Dataset scored {overall_score}/100.0 ({tier.upper()} tier). "
            f"Integrity ({integrity_val}/100), Uniqueness ({uniqueness_val}/100), "
            f"Balance ({balance_val}/100), Consistency ({consistency_val}/100)."
        )

        is_complete = (
            integrity.is_available
            and duplicates.is_available
            and consistency.is_available
            and imbalance.classes_with_images > 0
        )

        return TransparentQualityScore(
            overall_score=overall_score,
            quality_tier=tier,
            methodology_version=self.METHODOLOGY_VERSION,
            components=components,
            weight_configuration=weights,
            explanation=explanation,
            is_complete=is_complete,
        )

    # -----------------------------------------------------------------------
    # Executive Narrative Summary
    # -----------------------------------------------------------------------

    def _generate_executive_summary(
        self,
        dataset_name: str,
        score: TransparentQualityScore,
        integrity: ImageIntegrityAssessment,
        imbalance: ClassImbalanceAssessment,
        duplicates: DuplicateImpactAssessment,
        consistency: MetadataConsistencyAssessment,
        findings: List[QualityFinding],
    ) -> str:
        crit_count = sum(1 for f in findings if f.severity == QualitySeverity.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == QualitySeverity.HIGH)

        sentences = [
            f"{dataset_name} evaluated with overall quality score of {score.overall_score}/100.0 ({score.quality_tier.capitalize()} tier)."
        ]

        if integrity.status == "flawless":
            sentences.append("All discovered image files passed byte-level decodability verification with zero corruption.")
        elif integrity.total_corrupted_images:
            sentences.append(f"Image integrity flagged {integrity.total_corrupted_images} corrupted files.")

        if imbalance.imbalance_severity == "balanced":
            sentences.append(f"Class representation is balanced across {imbalance.total_classes} classes.")
        else:
            sentences.append(f"Class distribution exhibits {imbalance.imbalance_severity.replace('_', ' ')} (ratio: {imbalance.imbalance_ratio}x).")

        if duplicates.total_redundant_images:
            sentences.append(
                f"Identified {duplicates.total_redundant_images} redundant images across exact and near duplicates ({duplicates.clean_unique_images} clean unique images remain)."
            )
        else:
            sentences.append("Zero redundant duplicate images identified.")

        if crit_count > 0 or high_count > 0:
            sentences.append(f"Found {crit_count} critical and {high_count} high-priority curation findings requiring attention.")
        else:
            sentences.append("No critical curation defects detected; dataset is well-suited for benchmark evaluation.")

        return " ".join(sentences)


# Global service singleton
data_quality_service = DataQualityService()

