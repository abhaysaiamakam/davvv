"""EDA (Exploratory Data Analysis) service for CropLens dataset intelligence."""
from __future__ import annotations

import logging
import math
import random
import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.eda import (
    AspectRatioBin,
    AspectRatioAnalysis,
    ClassDistributionAnalysis,
    ClassDistributionEntry,
    ClassMetadataSummary,
    ColorAnalysis,
    DatasetOverview,
    DimensionFrequencyEntry,
    DimensionStats,
    EdaFinding,
    EdaFindingCategory,
    EdaReport,
    EdaReportListResponse,
    EdaReportSummary,
    EdaSeverity,
    EdaStatus,
    EdaStatusResponse,
    FileSizeBin,
    FileSizeStats,
    FormatAnalysis,
)
from app.storage.local import storage_backend

logger = logging.getLogger(__name__)

_METHODOLOGY_VERSION = "v1.0"


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _human_readable_bytes(n: int) -> str:
    """Convert byte count to human-readable string."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / (1024 ** 2):.1f} MB"
    return f"{n / (1024 ** 3):.2f} GB"


def _safe_mean(values: List[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def _safe_median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _safe_stdev(values: List[float]) -> Optional[float]:
    if len(values) >= 2:
        return statistics.stdev(values)
    return 0.0 if len(values) == 1 else None


def _compute_gini(counts: List[int]) -> float:
    """Compute Gini coefficient using the standard Lorenz-curve formula."""
    if not counts or sum(counts) == 0:
        return 0.0
    n = len(counts)
    sorted_counts = sorted(counts)
    total = sum(sorted_counts)
    cumsum = 0.0
    for i, v in enumerate(sorted_counts):
        cumsum += (2 * (i + 1) - n - 1) * v
    return cumsum / (n * total)


def _compute_entropy(counts: List[int]) -> Tuple[float, Optional[float]]:
    """Compute Shannon entropy and normalized entropy (base-2)."""
    total = sum(counts)
    if total == 0:
        return 0.0, None
    entropy = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    n_classes = len([c for c in counts if c > 0])
    normalized: Optional[float]
    if n_classes > 1:
        normalized = entropy / math.log2(n_classes)
    elif n_classes == 1:
        normalized = 0.0
    else:
        normalized = None
    return entropy, normalized


# ---------------------------------------------------------------------------
# EdaService
# ---------------------------------------------------------------------------

class EdaService:
    """Exploratory Data Analysis service for CropLens dataset intelligence."""

    def __init__(self, backend=None):
        self._storage = backend or storage_backend
        self._reports: Dict[str, EdaReport] = {}
        self._rehydrate_from_storage()

    def _rehydrate_from_storage(self) -> None:
        """Load all persisted EDA reports from disk into memory cache."""
        try:
            for raw in self._storage.list_persisted_eda_reports():
                try:
                    report = EdaReport.model_validate(raw)
                    self._reports[report.id] = report
                except Exception as exc:
                    logger.warning(f"Failed to rehydrate EDA report: {exc}")
        except Exception as exc:
            logger.warning(f"Failed to load EDA reports from storage: {exc}")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def run_eda(self, dataset_id: str, force_refresh: bool = False) -> EdaReport:
        """Execute the full EDA pipeline for a dataset."""
        # Local imports to avoid circular dependencies
        from app.services.dataset_service import dataset_service
        from app.services.analysis_service import analysis_service
        from app.services.data_quality_service import data_quality_service

        dataset = dataset_service.get_dataset(dataset_id)

        # Return cached report unless forced
        if not force_refresh:
            existing = self.get_latest_report_for_dataset(dataset_id)
            if existing and existing.status == EdaStatus.COMPLETED:
                return existing

        # Retrieve or compute unified analysis (M2)
        analysis = analysis_service.get_latest_analysis_for_dataset(dataset_id)
        if analysis is None:
            analysis = analysis_service.run_analysis(dataset_id)

        # Quality assessment (optional — do not fail if absent)
        quality_assessment = None
        try:
            quality_assessment = data_quality_service.get_latest_assessment_for_dataset(dataset_id)
        except Exception:
            pass

        eda_id = f"eda-{dataset_id}-{uuid.uuid4().hex[:10]}"
        created_at = datetime.now(timezone.utc).isoformat()

        # Extract images
        discovery = analysis.discovery
        validation = analysis.validation
        valid_images = [
            img for img in (validation.images or [])
            if img.status == "valid"
        ]

        # Run all analysis dimensions
        class_dist = self._compute_class_distribution(discovery, validation, valid_images)
        dim_analysis = self._compute_dimension_analysis(valid_images)
        ar_analysis = self._compute_aspect_ratio_analysis(valid_images)
        fmt_analysis = self._compute_format_analysis(validation)
        color_analysis = self._compute_color_analysis(valid_images, dataset=dataset)
        file_size_analysis = self._compute_file_size_analysis(valid_images)
        class_metadata = self._compute_class_metadata(discovery, valid_images)

        # Build overview
        total_size = sum(img.file_size_bytes or 0 for img in valid_images)
        overview = DatasetOverview(
            dataset_id=dataset_id,
            dataset_name=analysis.dataset_name,
            total_discovered_files=discovery.total_images if hasattr(discovery, "total_images") else discovery.discovered_image_files or 0,
            total_valid_images=validation.total_validated_images,
            total_invalid_images=validation.total_corrupted_images,
            class_count=class_dist.total_classes,
            classes_with_images=class_dist.classes_with_images,
            empty_class_count=len(class_dist.empty_classes),
            format_count=fmt_analysis.unique_format_count,
            unique_dimension_count=dim_analysis.unique_dimensions,
            total_size_bytes=total_size,
            total_size_human=_human_readable_bytes(total_size),
            analysis_id=analysis.id,
            quality_assessment_id=quality_assessment.id if quality_assessment else None,
            eda_methodology_version=_METHODOLOGY_VERSION,
        )

        findings = self._generate_findings(
            overview, class_dist, dim_analysis, fmt_analysis, color_analysis, ar_analysis, file_size_analysis
        )

        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            started = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            duration_ms: Optional[float] = (finished - started).total_seconds() * 1000
        except Exception:
            duration_ms = None

        report = EdaReport(
            id=eda_id,
            dataset_id=dataset_id,
            dataset_name=analysis.dataset_name,
            source_analysis_id=analysis.id,
            source_quality_assessment_id=quality_assessment.id if quality_assessment else None,
            status=EdaStatus.COMPLETED,
            created_at=created_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            methodology_version=_METHODOLOGY_VERSION,
            overview=overview,
            class_distribution=class_dist,
            dimension_analysis=dim_analysis,
            aspect_ratio_analysis=ar_analysis,
            format_analysis=fmt_analysis,
            color_analysis=color_analysis,
            file_size_analysis=file_size_analysis,
            class_metadata=class_metadata,
            findings=findings,
            warnings=[],
        )

        self._reports[eda_id] = report
        try:
            self._storage.save_eda_report(eda_id, report.model_dump(), dataset_id=dataset_id)
        except Exception as exc:
            logger.warning(f"Failed to persist EDA report {eda_id}: {exc}")

        return report

    def get_report(self, eda_id: str) -> Optional[EdaReport]:
        """Retrieve an EDA report by ID (memory cache first, then disk)."""
        if eda_id in self._reports:
            return self._reports[eda_id]
        raw = self._storage.load_eda_report(eda_id)
        if raw:
            try:
                report = EdaReport.model_validate(raw)
                self._reports[report.id] = report
                return report
            except Exception as exc:
                logger.warning(f"Failed to parse persisted EDA report {eda_id}: {exc}")
        return None

    def get_latest_report_for_dataset(self, dataset_id: str) -> Optional[EdaReport]:
        """Retrieve the latest EDA report for a dataset."""
        candidates = [r for r in self._reports.values() if r.dataset_id == dataset_id]
        if candidates:
            candidates.sort(key=lambda r: r.created_at, reverse=True)
            return candidates[0]
        eda_id = self._storage.get_latest_eda_report_id_for_dataset(dataset_id)
        if eda_id:
            return self.get_report(eda_id)
        return None

    def get_report_status(self, eda_id: str) -> Optional[EdaStatusResponse]:
        """Return status info for an EDA report."""
        report = self.get_report(eda_id)
        if not report:
            return None
        return EdaStatusResponse(
            eda_id=report.id,
            dataset_id=report.dataset_id,
            status=report.status,
            created_at=report.created_at,
            completed_at=report.completed_at,
            duration_ms=report.duration_ms,
            methodology_version=report.methodology_version,
            error_message=None,
        )

    def list_reports(self) -> EdaReportListResponse:
        """List all EDA reports, newest first."""
        all_reports = sorted(self._reports.values(), key=lambda r: r.created_at, reverse=True)
        summaries = [
            EdaReportSummary(
                id=r.id,
                dataset_id=r.dataset_id,
                status=r.status,
                created_at=r.created_at,
                completed_at=r.completed_at,
                total_valid_images=r.overview.total_valid_images,
                class_count=r.overview.class_count,
                findings_count=len(r.findings),
            )
            for r in all_reports
        ]
        return EdaReportListResponse(total=len(summaries), items=summaries)

    # -------------------------------------------------------------------------
    # Statistical helper methods
    # -------------------------------------------------------------------------

    def _compute_class_distribution(self, discovery, validation, valid_images) -> ClassDistributionAnalysis:
        """Compute class distribution statistics."""
        # Map class relative_path -> invalid count using validation records
        invalid_by_class: Dict[str, int] = defaultdict(int)
        for img in (validation.images or []):
            if img.status != "valid":
                for cls in discovery.classes:
                    if cls.relative_path in img.relative_path:
                        invalid_by_class[cls.class_name] += 1
                        break

        all_counts = [cls.image_count for cls in discovery.classes]
        mean_count = _safe_mean([float(c) for c in all_counts]) or 0.0
        median_count = _safe_median([float(c) for c in all_counts]) or 0.0
        std_count = _safe_stdev([float(c) for c in all_counts]) or 0.0
        variance = std_count ** 2

        min_count = min(all_counts) if all_counts else 0
        max_count = max(all_counts) if all_counts else 0
        cv = (std_count / mean_count) if mean_count > 0 else None
        imbalance_ratio = (max_count / min_count) if min_count > 0 else None

        entropy, normalized_entropy = _compute_entropy(all_counts)
        gini = _compute_gini(all_counts)

        empty_classes = [cls.class_name for cls in discovery.classes if cls.image_count == 0]
        classes_with_images = len([cls for cls in discovery.classes if cls.image_count > 0])
        total_valid = sum(all_counts)

        sorted_classes = sorted(discovery.classes, key=lambda c: c.image_count, reverse=True)
        distribution = []
        for rank, cls in enumerate(sorted_classes, start=1):
            valid_count = cls.image_count
            invalid_count = invalid_by_class.get(cls.class_name, 0)
            pct_valid = (valid_count / total_valid * 100) if total_valid > 0 else 0.0
            pct_total = pct_valid  # same since total_valid is the sum
            distribution.append(
                ClassDistributionEntry(
                    class_name=cls.class_name,
                    relative_path=cls.relative_path,
                    valid_image_count=valid_count,
                    invalid_image_count=invalid_count,
                    percentage_of_valid=round(pct_valid, 4),
                    percentage_of_total=round(pct_total, 4),
                    rank=rank,
                    deviation_from_mean=round(valid_count - mean_count, 4),
                    deviation_from_median=round(valid_count - median_count, 4),
                )
            )

        notes = []
        if cv is not None and cv > 0.5:
            notes.append(f"High class imbalance detected (CV={cv:.2f}). Consider augmentation or resampling.")
        if imbalance_ratio is not None and imbalance_ratio > 10:
            notes.append(f"Extreme imbalance ratio of {imbalance_ratio:.1f}x. Minority classes may be under-represented.")
        if empty_classes:
            names = ", ".join(empty_classes[:3])
            suffix = "..." if len(empty_classes) > 3 else ""
            notes.append(f"{len(empty_classes)} empty class(es) detected: {names}{suffix}.")
        if normalized_entropy is not None and normalized_entropy > 0.95:
            notes.append("Dataset is near-perfectly balanced (normalized entropy > 0.95).")
        elif normalized_entropy is not None and normalized_entropy < 0.5:
            notes.append("Dataset is significantly imbalanced (normalized entropy < 0.5).")

        return ClassDistributionAnalysis(
            total_classes=len(discovery.classes),
            classes_with_images=classes_with_images,
            empty_classes=empty_classes,
            distribution=distribution,
            min_count=min_count,
            max_count=max_count,
            mean_count=round(mean_count, 4),
            median_count=round(median_count, 4),
            std_count=round(std_count, 4),
            variance=round(variance, 4),
            coefficient_of_variation=round(cv, 4) if cv is not None else None,
            imbalance_ratio=round(imbalance_ratio, 4) if imbalance_ratio is not None else None,
            entropy=round(entropy, 6),
            normalized_entropy=round(normalized_entropy, 6) if normalized_entropy is not None else None,
            gini_coefficient=round(gini, 6),
            evaluation_notes=notes,
        )

    def _compute_dimension_analysis(self, valid_images) -> DimensionStats:
        """Compute image dimension statistics."""
        widths = [img.width for img in valid_images if img.width is not None]
        heights = [img.height for img in valid_images if img.height is not None]
        total = len(valid_images)

        portrait_count = 0
        landscape_count = 0
        square_count = 0
        dim_freq: Dict[str, int] = defaultdict(int)

        for img in valid_images:
            if img.width is not None and img.height is not None and img.height > 0:
                ar = img.width / img.height
                if ar < 0.95:
                    portrait_count += 1
                elif ar > 1.05:
                    landscape_count += 1
                else:
                    square_count += 1
                key = f"{img.width}x{img.height}"
                dim_freq[key] += 1

        unique_dims = len(dim_freq)
        sorted_dims = sorted(dim_freq.items(), key=lambda x: x[1], reverse=True)
        most_common = []
        for dim_key, cnt in sorted_dims[:10]:
            w_str, h_str = dim_key.split("x")
            most_common.append(
                DimensionFrequencyEntry(
                    width=int(w_str),
                    height=int(h_str),
                    count=cnt,
                    percentage=round(cnt / total * 100, 2) if total > 0 else 0.0,
                )
            )

        pct = lambda n: round(n / total * 100, 2) if total > 0 else 0.0

        return DimensionStats(
            min_width=min(widths) if widths else None,
            max_width=max(widths) if widths else None,
            mean_width=round(_safe_mean([float(w) for w in widths]), 2) if widths else None,
            median_width=round(_safe_median([float(w) for w in widths]), 2) if widths else None,
            std_width=round(_safe_stdev([float(w) for w in widths]) or 0.0, 4) if widths else None,
            min_height=min(heights) if heights else None,
            max_height=max(heights) if heights else None,
            mean_height=round(_safe_mean([float(h) for h in heights]), 2) if heights else None,
            median_height=round(_safe_median([float(h) for h in heights]), 2) if heights else None,
            std_height=round(_safe_stdev([float(h) for h in heights]) or 0.0, 4) if heights else None,
            portrait_count=portrait_count,
            landscape_count=landscape_count,
            square_count=square_count,
            portrait_pct=pct(portrait_count),
            landscape_pct=pct(landscape_count),
            square_pct=pct(square_count),
            unique_dimensions=unique_dims,
            most_common_dimensions=most_common,
            dimension_frequency=dict(dim_freq),
        )

    def _compute_aspect_ratio_analysis(self, valid_images) -> AspectRatioAnalysis:
        """Compute aspect ratio distribution."""
        ars: List[float] = []
        for img in valid_images:
            if img.width is not None and img.height is not None and img.height > 0:
                ars.append(img.width / img.height)

        portrait_count = sum(1 for ar in ars if ar < 0.95)
        landscape_count = sum(1 for ar in ars if ar > 1.05)
        square_count = sum(1 for ar in ars if 0.95 <= ar <= 1.05)
        extreme_low_count = sum(1 for ar in ars if ar < 0.5)
        extreme_high_count = sum(1 for ar in ars if ar > 2.0)

        bin_defs = [
            ("Very Narrow (<0.5)", 0.0, 0.5),
            ("Portrait (0.5–0.95)", 0.5, 0.95),
            ("Square (0.95–1.05)", 0.95, 1.05),
            ("Landscape (1.05–2.0)", 1.05, 2.0),
            ("Very Wide (>2.0)", 2.0, float("inf")),
        ]
        total = len(ars)
        bins = []
        for label, lo, hi in bin_defs:
            if hi == float("inf"):
                cnt = sum(1 for ar in ars if ar >= lo)
                hi_val = 999.0
            else:
                cnt = sum(1 for ar in ars if lo <= ar < hi)
                hi_val = hi
            bins.append(AspectRatioBin(
                label=label,
                min_ar=lo,
                max_ar=hi_val,
                count=cnt,
                percentage=round(cnt / total * 100, 2) if total > 0 else 0.0,
            ))

        return AspectRatioAnalysis(
            min_ar=round(min(ars), 4) if ars else None,
            max_ar=round(max(ars), 4) if ars else None,
            mean_ar=round(_safe_mean(ars), 4) if ars else None,
            median_ar=round(_safe_median(ars), 4) if ars else None,
            std_ar=round(_safe_stdev(ars) or 0.0, 4) if ars else None,
            portrait_count=portrait_count,
            landscape_count=landscape_count,
            square_count=square_count,
            extreme_low_count=extreme_low_count,
            extreme_high_count=extreme_high_count,
            distribution_bins=bins,
        )

    def _compute_format_analysis(self, validation) -> FormatAnalysis:
        """Compute image format distribution."""
        fmt_dist = dict(validation.format_distribution)
        total = sum(fmt_dist.values())
        fmt_pcts = {
            fmt: round(cnt / total * 100, 4) if total > 0 else 0.0
            for fmt, cnt in fmt_dist.items()
        }
        sorted_fmts = sorted(fmt_dist.items(), key=lambda x: x[1], reverse=True)
        most_common = sorted_fmts[0][0] if sorted_fmts else None
        least_common = sorted_fmts[-1][0] if len(sorted_fmts) > 1 else None

        return FormatAnalysis(
            format_distribution=fmt_dist,
            format_percentages=fmt_pcts,
            unique_format_count=len(fmt_dist),
            most_common_format=most_common,
            least_common_format=least_common,
        )

    def _compute_color_analysis(self, valid_images, seed: int = 42, dataset=None) -> ColorAnalysis:
        """Compute color mode distribution and per-channel RGB statistics."""
        cm_dist: Dict[str, int] = defaultdict(int)
        for img in valid_images:
            mode = (img.color_mode or "UNKNOWN").upper()
            cm_dist[mode] += 1

        total = len(valid_images)
        cm_pcts = {
            m: round(cnt / total * 100, 4) if total > 0 else 0.0
            for m, cnt in cm_dist.items()
        }
        grayscale_count = sum(v for k, v in cm_dist.items() if k in ("L", "GRAY", "GRAYSCALE"))
        rgb_count = cm_dist.get("RGB", 0)
        rgba_count = cm_dist.get("RGBA", 0)

        rgb_mean: Optional[List[float]] = None
        rgb_std: Optional[List[float]] = None
        sampling_methodology = (
            "Per-channel mean and std computed from pixel samples of valid RGB images "
            "resized to 64x64 (LANCZOS resampling). Up to 1000 images sampled. seed=42."
        )

        try:
            from PIL import Image as PILImage
            from app.storage.local import storage_backend as _sb

            rgb_imgs = [img for img in valid_images if (img.color_mode or "").upper() == "RGB"]
            rng = random.Random(seed)
            sample_size = min(1000, len(rgb_imgs))
            sampled = rng.sample(rgb_imgs, sample_size) if sample_size > 0 else []

            r_vals: List[float] = []
            g_vals: List[float] = []
            b_vals: List[float] = []

            ds_root = None
            if dataset:
                try:
                    ds_root = _sb.resolve_dataset_path(dataset)
                except Exception:
                    ds_root = None

            for img_record in sampled:
                try:
                    abs_path = _sb.base_dir / img_record.relative_path
                    if ds_root and (ds_root / img_record.relative_path).is_file():
                        abs_path = ds_root / img_record.relative_path
                    elif not abs_path.is_file() and _sb.external_curated_dir:
                        rp = img_record.relative_path
                        if rp.startswith("curated/"):
                            rp = rp[len("curated/"):]
                        # Strip dataset slug (first path component)
                        parts = rp.split("/", 1)
                        if len(parts) > 1:
                            candidate = _sb.external_curated_dir / parts[1]
                            if candidate.is_file():
                                abs_path = candidate
                        if not abs_path.is_file():
                            abs_path = _sb.external_curated_dir / rp
                    if not abs_path.is_file():
                        continue

                    with PILImage.open(abs_path) as pil_img:
                        pil_img = pil_img.convert("RGB")
                        small = pil_img.resize((64, 64), PILImage.LANCZOS)
                        pixels = list(small.getdata())
                        r_vals.extend(float(p[0]) for p in pixels)
                        g_vals.extend(float(p[1]) for p in pixels)
                        b_vals.extend(float(p[2]) for p in pixels)
                except Exception:
                    continue

            if r_vals and g_vals and b_vals:
                rgb_mean = [
                    round(statistics.mean(r_vals), 4),
                    round(statistics.mean(g_vals), 4),
                    round(statistics.mean(b_vals), 4),
                ]
                rgb_std = [
                    round(statistics.stdev(r_vals) if len(r_vals) >= 2 else 0.0, 4),
                    round(statistics.stdev(g_vals) if len(g_vals) >= 2 else 0.0, 4),
                    round(statistics.stdev(b_vals) if len(b_vals) >= 2 else 0.0, 4),
                ]
        except ImportError:
            sampling_methodology += " (PIL not available; channel stats skipped)"
        except Exception as exc:
            logger.warning(f"Color pixel sampling failed: {exc}")
            sampling_methodology += f" (sampling encountered error: {type(exc).__name__})"

        return ColorAnalysis(
            color_mode_distribution=dict(cm_dist),
            color_mode_percentages=cm_pcts,
            grayscale_count=grayscale_count,
            rgb_count=rgb_count,
            rgba_count=rgba_count,
            rgb_mean=rgb_mean,
            rgb_std=rgb_std,
            sampling_methodology=sampling_methodology,
            sampling_seed=seed,
        )

    def _compute_file_size_analysis(self, valid_images) -> FileSizeStats:
        """Compute file size distribution statistics."""
        sizes = [img.file_size_bytes for img in valid_images if img.file_size_bytes is not None]
        total_bytes = sum(sizes)
        total_imgs = len(sizes)

        bin_defs = [
            ("< 10 KB", 0, 10 * 1024),
            ("10–50 KB", 10 * 1024, 50 * 1024),
            ("50–100 KB", 50 * 1024, 100 * 1024),
            ("100–500 KB", 100 * 1024, 500 * 1024),
            ("500 KB – 1 MB", 500 * 1024, 1024 * 1024),
            ("> 1 MB", 1024 * 1024, None),
        ]
        size_bins = []
        for label, lo, hi in bin_defs:
            if hi is None:
                cnt = sum(1 for s in sizes if s >= lo)
                hi_val = 2 ** 31
            else:
                cnt = sum(1 for s in sizes if lo <= s < hi)
                hi_val = hi
            size_bins.append(FileSizeBin(
                label=label,
                min_bytes=lo,
                max_bytes=hi_val,
                count=cnt,
                percentage=round(cnt / total_imgs * 100, 2) if total_imgs > 0 else 0.0,
            ))

        min_sz = min(sizes) if sizes else None
        max_sz = max(sizes) if sizes else None
        mean_sz = _safe_mean([float(s) for s in sizes])
        median_sz = _safe_median([float(s) for s in sizes])
        std_sz = _safe_stdev([float(s) for s in sizes])

        return FileSizeStats(
            min_bytes=min_sz,
            max_bytes=max_sz,
            mean_bytes=round(mean_sz, 2) if mean_sz is not None else None,
            median_bytes=round(median_sz, 2) if median_sz is not None else None,
            std_bytes=round(std_sz, 4) if std_sz is not None else None,
            total_bytes=total_bytes,
            min_human=_human_readable_bytes(min_sz) if min_sz is not None else None,
            max_human=_human_readable_bytes(max_sz) if max_sz is not None else None,
            mean_human=_human_readable_bytes(int(mean_sz)) if mean_sz is not None else None,
            total_human=_human_readable_bytes(total_bytes),
            size_distribution_bins=size_bins,
        )

    def _compute_class_metadata(self, discovery, valid_images) -> List[ClassMetadataSummary]:
        """Compute per-class metadata summary."""
        # Group images by class using class relative_path match
        class_images: Dict[str, List] = defaultdict(list)
        for img in valid_images:
            matched = False
            for cls in discovery.classes:
                if cls.relative_path in img.relative_path:
                    class_images[cls.class_name].append(img)
                    matched = True
                    break
            if not matched:
                class_images["__root__"].append(img)

        summaries = []
        for cls in sorted(discovery.classes, key=lambda c: c.class_name):
            imgs = class_images.get(cls.class_name, [])
            dim_stats = self._compute_dimension_analysis(imgs) if imgs else None

            fmt_dist: Dict[str, int] = defaultdict(int)
            cm_dist: Dict[str, int] = defaultdict(int)
            for img in imgs:
                if img.format:
                    fmt_dist[img.format.upper()] += 1
                if img.color_mode:
                    cm_dist[img.color_mode.upper()] += 1

            fs_stats = self._compute_file_size_analysis(imgs) if imgs else None

            ars = [
                img.width / img.height
                for img in imgs
                if img.width is not None and img.height is not None and img.height > 0
            ]
            mean_ar = round(statistics.mean(ars), 4) if ars else None

            summaries.append(ClassMetadataSummary(
                class_name=cls.class_name,
                valid_count=len(imgs),
                dimension_stats=dim_stats,
                format_distribution=dict(fmt_dist),
                color_mode_distribution=dict(cm_dist),
                file_size_stats=fs_stats,
                mean_aspect_ratio=mean_ar,
            ))

        return summaries

    def _generate_findings(
        self,
        overview: DatasetOverview,
        class_dist: ClassDistributionAnalysis,
        dim_analysis: DimensionStats,
        format_analysis: FormatAnalysis,
        color_analysis: ColorAnalysis,
        ar_analysis: AspectRatioAnalysis,
        file_size_analysis: FileSizeStats,
    ) -> List[EdaFinding]:
        """Generate structured, evidence-backed EDA findings."""
        findings: List[EdaFinding] = []

        # 1. Dominant class
        if class_dist.distribution:
            top = class_dist.distribution[0]
            findings.append(EdaFinding(
                id="eda-finding-dominant-class",
                category=EdaFindingCategory.CLASS_DISTRIBUTION,
                severity=EdaSeverity.INFO,
                title=f"Dominant class: {top.class_name}",
                explanation=(
                    f"Class '{top.class_name}' has the most images ({top.valid_image_count}), "
                    f"representing {top.percentage_of_valid:.1f}% of all valid images."
                ),
                metric_name="max_class_count",
                observed_value=top.valid_image_count,
                expected_value=None,
                threshold_used=None,
                affected_classes=[top.class_name],
                affected_image_samples=[],
                recommended_action="Monitor this class during training to prevent bias toward the dominant class.",
                evidence_references=[f"class_distribution.distribution[0].class_name={top.class_name}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 2. Class imbalance
        if class_dist.coefficient_of_variation is not None and class_dist.coefficient_of_variation > 0.5:
            minority = [e for e in class_dist.distribution if e.valid_image_count < class_dist.mean_count * 0.5]
            findings.append(EdaFinding(
                id="eda-finding-class-imbalance",
                category=EdaFindingCategory.CLASS_DISTRIBUTION,
                severity=EdaSeverity.MEDIUM if class_dist.coefficient_of_variation > 1.0 else EdaSeverity.LOW,
                title="Significant class imbalance detected",
                explanation=(
                    f"The coefficient of variation (CV={class_dist.coefficient_of_variation:.2f}) "
                    f"indicates high class imbalance. {len(minority)} classes are below 50% of the mean count."
                ),
                metric_name="coefficient_of_variation",
                observed_value=class_dist.coefficient_of_variation,
                expected_value=None,
                threshold_used=0.5,
                affected_classes=[e.class_name for e in minority[:5]],
                affected_image_samples=[],
                recommended_action="Apply oversampling, weighted loss functions, or augmentation to under-represented classes.",
                evidence_references=[f"class_distribution.coefficient_of_variation={class_dist.coefficient_of_variation}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 3. Empty classes
        if class_dist.empty_classes:
            findings.append(EdaFinding(
                id="eda-finding-empty-classes",
                category=EdaFindingCategory.CLASS_DISTRIBUTION,
                severity=EdaSeverity.HIGH,
                title=f"{len(class_dist.empty_classes)} empty class(es) detected",
                explanation=(
                    f"Classes {class_dist.empty_classes[:3]} contain no valid images. "
                    "These classes cannot be used for training."
                ),
                metric_name="empty_class_count",
                observed_value=len(class_dist.empty_classes),
                expected_value=0,
                threshold_used=0,
                affected_classes=class_dist.empty_classes,
                affected_image_samples=[],
                recommended_action="Remove empty class directories or populate them with representative images.",
                evidence_references=[f"class_distribution.empty_classes={class_dist.empty_classes}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 4. Dimension high variability
        if (
            dim_analysis.std_width is not None
            and dim_analysis.mean_width is not None
            and dim_analysis.mean_width > 0
            and dim_analysis.std_width / dim_analysis.mean_width > 0.3
        ):
            cv_dim = dim_analysis.std_width / dim_analysis.mean_width
            findings.append(EdaFinding(
                id="eda-finding-dimension-variability",
                category=EdaFindingCategory.DIMENSION_CONSISTENCY,
                severity=EdaSeverity.MEDIUM if cv_dim > 0.5 else EdaSeverity.LOW,
                title="High variation in image dimensions detected",
                explanation=(
                    f"Width CV={cv_dim:.2f}. Images range from "
                    f"{dim_analysis.min_width}x{dim_analysis.min_height} to "
                    f"{dim_analysis.max_width}x{dim_analysis.max_height} px. "
                    f"{dim_analysis.unique_dimensions} unique dimension combinations found."
                ),
                metric_name="dimension_cv_width",
                observed_value=round(cv_dim, 4),
                expected_value=None,
                threshold_used=0.3,
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="Standardize image dimensions using a consistent resize pipeline before training.",
                evidence_references=[
                    f"dimension_analysis.std_width={dim_analysis.std_width}",
                    f"dimension_analysis.mean_width={dim_analysis.mean_width}",
                ],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 5. Mixed formats
        if format_analysis.unique_format_count > 1:
            findings.append(EdaFinding(
                id="eda-finding-mixed-formats",
                category=EdaFindingCategory.FORMAT_DIVERSITY,
                severity=EdaSeverity.LOW,
                title=f"Multiple image formats detected ({format_analysis.unique_format_count} formats)",
                explanation=(
                    f"Dataset contains {format_analysis.unique_format_count} different image formats: "
                    f"{list(format_analysis.format_distribution.keys())}."
                ),
                metric_name="unique_format_count",
                observed_value=format_analysis.unique_format_count,
                expected_value=1,
                threshold_used=1,
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="Convert all images to a single format (e.g., JPEG or PNG) for consistent preprocessing.",
                evidence_references=[f"format_analysis.format_distribution={format_analysis.format_distribution}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 6. Uniform format (info)
        if format_analysis.unique_format_count == 1 and format_analysis.most_common_format:
            findings.append(EdaFinding(
                id="eda-finding-uniform-format",
                category=EdaFindingCategory.FORMAT_DIVERSITY,
                severity=EdaSeverity.INFO,
                title=f"All images share a single format: {format_analysis.most_common_format}",
                explanation=(
                    f"The dataset is format-consistent: all {overview.total_valid_images} "
                    f"valid images use {format_analysis.most_common_format} format."
                ),
                metric_name="unique_format_count",
                observed_value=1,
                expected_value=None,
                threshold_used=None,
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="No action required. Format consistency benefits preprocessing pipelines.",
                evidence_references=[f"format_analysis.most_common_format={format_analysis.most_common_format}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 7. Grayscale images
        if color_analysis.grayscale_count > 0:
            findings.append(EdaFinding(
                id="eda-finding-grayscale-images",
                category=EdaFindingCategory.COLOR_SPACE,
                severity=EdaSeverity.INFO,
                title=f"{color_analysis.grayscale_count} grayscale image(s) detected",
                explanation=(
                    f"{color_analysis.grayscale_count} images are in grayscale mode. "
                    "If RGB models are used, these will need conversion."
                ),
                metric_name="grayscale_count",
                observed_value=color_analysis.grayscale_count,
                expected_value=0,
                threshold_used=None,
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="Convert grayscale images to RGB (3-channel) if the model requires RGB input.",
                evidence_references=[f"color_analysis.grayscale_count={color_analysis.grayscale_count}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 8. RGBA images
        if color_analysis.rgba_count > 0:
            findings.append(EdaFinding(
                id="eda-finding-rgba-images",
                category=EdaFindingCategory.COLOR_SPACE,
                severity=EdaSeverity.LOW,
                title=f"{color_analysis.rgba_count} RGBA image(s) with alpha channel",
                explanation=(
                    f"{color_analysis.rgba_count} images have an alpha (transparency) channel. "
                    "Many models do not support 4-channel input."
                ),
                metric_name="rgba_count",
                observed_value=color_analysis.rgba_count,
                expected_value=0,
                threshold_used=None,
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="Convert RGBA images to RGB, compositing over a white or black background.",
                evidence_references=[f"color_analysis.rgba_count={color_analysis.rgba_count}"],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 9. Extreme aspect ratios
        extreme_total = ar_analysis.extreme_low_count + ar_analysis.extreme_high_count
        if extreme_total > 0:
            findings.append(EdaFinding(
                id="eda-finding-extreme-aspect-ratios",
                category=EdaFindingCategory.ASPECT_RATIO,
                severity=EdaSeverity.LOW,
                title=f"{extreme_total} image(s) with extreme aspect ratios",
                explanation=(
                    f"{ar_analysis.extreme_low_count} images have AR < 0.5 (very narrow), "
                    f"{ar_analysis.extreme_high_count} have AR > 2.0 (very wide). "
                    "These may lose significant content under standard cropping."
                ),
                metric_name="extreme_aspect_ratio_count",
                observed_value=extreme_total,
                expected_value=0,
                threshold_used="AR < 0.5 or AR > 2.0",
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="Apply aspect-preserving resizing with padding rather than center-crop.",
                evidence_references=[
                    f"aspect_ratio_analysis.extreme_low_count={ar_analysis.extreme_low_count}",
                    f"aspect_ratio_analysis.extreme_high_count={ar_analysis.extreme_high_count}",
                ],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        # 10. File size outliers
        if (
            file_size_analysis.std_bytes is not None
            and file_size_analysis.mean_bytes is not None
            and file_size_analysis.mean_bytes > 0
            and file_size_analysis.std_bytes / file_size_analysis.mean_bytes > 1.0
        ):
            findings.append(EdaFinding(
                id="eda-finding-file-size-variance",
                category=EdaFindingCategory.FILE_SIZE,
                severity=EdaSeverity.INFO,
                title="High file size variance detected",
                explanation=(
                    f"File size CV = {file_size_analysis.std_bytes / file_size_analysis.mean_bytes:.2f}. "
                    f"Sizes range from {file_size_analysis.min_human} to {file_size_analysis.max_human}."
                ),
                metric_name="file_size_cv",
                observed_value=round(file_size_analysis.std_bytes / file_size_analysis.mean_bytes, 4),
                expected_value=None,
                threshold_used=1.0,
                affected_classes=[],
                affected_image_samples=[],
                recommended_action="Inspect very large and very small files for quality issues or accidental duplicates.",
                evidence_references=[
                    f"file_size_analysis.min_bytes={file_size_analysis.min_bytes}",
                    f"file_size_analysis.max_bytes={file_size_analysis.max_bytes}",
                ],
                methodology_version=_METHODOLOGY_VERSION,
            ))

        return findings


# Singleton
eda_service = EdaService()

