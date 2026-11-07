"""
M6 — Asynchronous Processing Job Service.

Manages the background execution of the full analytical pipeline (M2 -> M3 -> M4)
for uploaded datasets. Handles job state persistence, progress tracking, restart
recovery, and failure isolation.
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from app.core.errors import (
    JobAlreadyRunningError,
    JobNotFoundError,
)
from app.events.event_bus import event_bus
from app.events.event_types import DatasetEventType
from app.schemas.dataset import DatasetStatus
from app.schemas.job import JobStage, JobStatus, ProcessingJob
from app.storage.base import StorageBackend
from app.storage.local import get_storage_backend

logger = logging.getLogger(__name__)


class JobService:
    """Service orchestrating background analytical pipeline execution and lifecycle tracking."""

    def __init__(self, backend: Optional[StorageBackend] = None, max_workers: int = 2):
        self.storage: StorageBackend = backend or get_storage_backend()
        self._max_workers = max_workers
        self._jobs: Dict[str, ProcessingJob] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="croplens-worker")
        self._rehydrate_from_storage()

    def _get_executor(self) -> ThreadPoolExecutor:
        """Ensure active executor is available, recreating if previously shut down."""
        with self._lock:
            if self._executor is None or getattr(self._executor, "_shutdown", False):
                self._executor = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="croplens-worker",
                )
            return self._executor

    def _rehydrate_from_storage(self) -> None:
        """Load historical job records from storage into memory cache."""
        try:
            persisted = self.storage.list_persisted_jobs()
            for record in persisted:
                try:
                    job = ProcessingJob.model_validate(record)
                    self._jobs[job.job_id] = job
                except Exception as exc:
                    logger.warning(f"Failed to rehydrate job {record.get('job_id')}: {exc}")
            logger.info(f"Rehydrated {len(self._jobs)} processing jobs from storage.")
        except Exception as exc:
            logger.error(f"Error during job rehydration: {exc}")

    def recover_jobs_on_startup(self) -> None:
        """
        Invoked on application startup:
        - Rehydrates any stored jobs from storage.
        - Interrupted jobs (stuck in 'processing' / 'validating') are marked failed with an explanatory code.
        - Unstarted queued jobs are resumed in the worker pool.
        """
        self._rehydrate_from_storage()
        with self._lock:
            for job in list(self._jobs.values()):
                if job.status in (JobStatus.PROCESSING, JobStatus.VALIDATING):
                    logger.warning(
                        f"Job {job.job_id} was interrupted by server shutdown. Marking as failed."
                    )
                    job.status = JobStatus.FAILED
                    job.current_stage = JobStage.FAILED
                    job.error_code = "JOB_INTERRUPTED_BY_RESTART"
                    job.error_message = "Processing was interrupted by server shutdown. Safe to retry."
                    job.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    self._persist_job(job)

                elif job.status == JobStatus.QUEUED:
                    logger.info(f"Resuming queued job {job.job_id} on startup.")
                    self._get_executor().submit(self._execute_pipeline, job.job_id)

    def create_job(self, dataset_id: str, version_id: str) -> ProcessingJob:
        """Create and persist a new processing job for a dataset version."""
        with self._lock:
            # Prevent duplicate active jobs for the same dataset version
            for active_job in self._jobs.values():
                if (
                    active_job.dataset_id == dataset_id
                    and active_job.dataset_version == version_id
                    and active_job.status in (JobStatus.QUEUED, JobStatus.VALIDATING, JobStatus.PROCESSING)
                ):
                    raise JobAlreadyRunningError(dataset_id, version_id)

            job_id = f"job-{dataset_id}-{uuid.uuid4().hex[:8]}"
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            job = ProcessingJob(
                job_id=job_id,
                dataset_id=dataset_id,
                dataset_version=version_id,
                job_type="analysis_pipeline",
                status=JobStatus.QUEUED,
                current_stage=JobStage.QUEUED,
                progress_pct=0.0,
                created_at=now,
                artifact_refs={},
            )
            self._jobs[job_id] = job
            self._persist_job(job)

        event_bus.emit(
            DatasetEventType.DATASET_ANALYSIS_QUEUED,
            dataset_id=dataset_id,
            version_id=version_id,
            job_id=job_id,
            payload={"created_at": now},
        )
        return job

    def enqueue_job(self, job_id: str) -> None:
        """Submit an existing queued job to the worker pool."""
        job = self.get_job(job_id)
        if not job:
            raise JobNotFoundError(job_id)
        self._get_executor().submit(self._execute_pipeline, job_id)

    def retry_job(self, job_id: str) -> ProcessingJob:
        """Safely re-enqueue a failed or interrupted job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise JobNotFoundError(job_id)
            if job.status in (JobStatus.PROCESSING, JobStatus.QUEUED):
                raise JobAlreadyRunningError(job.dataset_id, job.dataset_version)

            job.status = JobStatus.QUEUED
            job.current_stage = JobStage.QUEUED
            job.progress_pct = 0.0
            job.started_at = None
            job.completed_at = None
            job.duration_ms = None
            job.error_code = None
            job.error_message = None
            job.retry_count += 1
            self._persist_job(job)

        self._get_executor().submit(self._execute_pipeline, job_id)
        return job

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """Retrieve job by ID from memory or disk."""
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]

        data = self.storage.load_job(job_id)
        if data:
            try:
                job = ProcessingJob.model_validate(data)
                with self._lock:
                    self._jobs[job_id] = job
                return job
            except Exception as exc:
                logger.error(f"Failed to parse stored job {job_id}: {exc}")
        return None

    def list_jobs(
        self,
        dataset_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
    ) -> List[ProcessingJob]:
        """List jobs matching optional filters, sorted newest first."""
        with self._lock:
            jobs = list(self._jobs.values())

        if dataset_id:
            jobs = [j for j in jobs if j.dataset_id == dataset_id]
        if status:
            jobs = [j for j in jobs if j.status == status]

        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def _persist_job(self, job: ProcessingJob) -> None:
        """Persist current job state to disk."""
        try:
            self.storage.save_job(job.job_id, job.model_dump())
        except Exception as exc:
            logger.error(f"Failed to persist job {job.job_id}: {exc}")

    # -------------------------------------------------------------------------
    # Core Pipeline Worker Execution
    # -------------------------------------------------------------------------

    def _execute_pipeline(self, job_id: str) -> None:
        """
        Background worker routine running M2 -> M3 -> M4 sequentially.
        Ensures intermediate progress is tracked, exceptions are caught, and events are emitted.
        """
        job = self.get_job(job_id)
        if not job:
            return

        # Local imports to break circular dependencies
        from app.schemas.analysis import AnalysisConfig
        from app.services.dataset_service import dataset_service
        from app.services.analysis_service import analysis_service
        from app.services.data_quality_service import data_quality_service
        from app.services.eda_service import eda_service
        from app.services.comparison_service import comparison_service

        start_time = time.perf_counter()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self._lock:
            job.status = JobStatus.PROCESSING
            job.current_stage = JobStage.DISCOVERY
            job.started_at = now_str
            job.progress_pct = 15.0
            self._persist_job(job)

        event_bus.emit(
            DatasetEventType.DATASET_ANALYSIS_STARTED,
            dataset_id=job.dataset_id,
            version_id=job.dataset_version,
            job_id=job_id,
        )

        try:
            # 1. M2 Discovery
            logger.info(f"[{job_id}] Stage 1/6: Running dataset discovery for {job.dataset_id}")
            discovery_res = dataset_service.discover_dataset(job.dataset_id)
            img_count = discovery_res.discovered_image_files or 0
            if img_count == 0:
                dataset_obj = dataset_service.get_dataset(job.dataset_id)
                dataset_dir = self.storage.resolve_dataset_path(dataset_obj)
                non_img_files = [
                    f for f in dataset_dir.rglob("*")
                    if f.is_file() and f.suffix.lower() in (".csv", ".tsv", ".json", ".parquet", ".txt", ".npy")
                ]
                if not non_img_files:
                    raise ValueError("Dataset discovery found 0 supported image or data files.")

            with self._lock:
                job.current_stage = JobStage.VALIDATION
                job.progress_pct = 35.0
                self._persist_job(job)

            # 2. M2 Validation
            logger.info(f"[{job_id}] Stage 2/6: Running validation for {job.dataset_id}")
            val_res = None
            if img_count > 0:
                val_res = dataset_service.validate_dataset(job.dataset_id)
                if val_res.total_validated_images == 0:
                    raise ValueError("Validation failed: 0 decodable valid images found.")
            else:
                logger.info(f"[{job_id}] Non-image dataset detected; skipping image byte validation.")

            with self._lock:
                job.current_stage = JobStage.EXACT_DUPLICATES
                job.progress_pct = 50.0
                self._persist_job(job)

            # 3. M2 Duplicate Detection (Exact & Near)
            logger.info(f"[{job_id}] Stage 3/6: Running duplicate detection for {job.dataset_id}")
            if img_count > 0:
                dataset_service.detect_duplicates(job.dataset_id)
                dataset_service.detect_near_duplicates(job.dataset_id)
            else:
                logger.info(f"[{job_id}] Non-image dataset detected; skipping perceptual image duplicate detection.")

            with self._lock:
                job.current_stage = JobStage.UNIFIED_ANALYSIS
                job.progress_pct = 65.0
                self._persist_job(job)

            # 4. M2 Unified Analysis persistence
            logger.info(f"[{job_id}] Stage 4/6: Orchestrating unified analysis for {job.dataset_id}")
            analysis_res = analysis_service.run_analysis(job.dataset_id, config=AnalysisConfig(force_refresh=False))
            job.artifact_refs["analysis_id"] = analysis_res.id

            with self._lock:
                job.current_stage = JobStage.QUALITY_LAB
                job.progress_pct = 80.0
                self._persist_job(job)

            # 5. M3 Data Quality Assessment
            logger.info(f"[{job_id}] Stage 5/6: Running Data Quality Lab for {job.dataset_id}")
            quality_res = data_quality_service.assess_dataset(job.dataset_id, analysis=analysis_res, force_refresh=True)
            job.artifact_refs["quality_id"] = quality_res.id
            job.artifact_refs["quality_assessment_id"] = quality_res.id

            with self._lock:
                job.current_stage = JobStage.EDA_ENGINE
                job.progress_pct = 95.0
                self._persist_job(job)

            # 6. M4 EDA Engine
            logger.info(f"[{job_id}] Stage 6/6: Running EDA engine for {job.dataset_id}")
            eda_res = eda_service.run_eda(job.dataset_id, force_refresh=True)
            job.artifact_refs["eda_id"] = eda_res.id
            job.artifact_refs["eda_report_id"] = eda_res.id

            # 7. Visualization Specifications (non-blocking for core analytics)
            logger.info(f"[{job_id}] Stage 7: Generating visualization specifications for {job.dataset_id}")
            with self._lock:
                job.current_stage = JobStage.VISUALIZATIONS
                job.progress_pct = 98.0
                self._persist_job(job)

            try:
                from app.services.visualizations import visualization_service
                vis_col = visualization_service.generate_visualizations(
                    dataset_id=job.dataset_id,
                    version_id=job.dataset_version,
                    force_refresh=True,
                )
                job.artifact_refs["visualization_id"] = vis_col.id
            except Exception as vis_exc:
                logger.error(f"[{job_id}] Visualization generation failed (non-fatal): {vis_exc}", exc_info=True)

            # 8. M7 Insights (non-blocking for core analytics)
            logger.info(f"[{job_id}] Stage 8: Generating dataset insights for {job.dataset_id}")
            with self._lock:
                job.current_stage = JobStage.INSIGHTS
                job.progress_pct = 99.0
                self._persist_job(job)

            try:
                from app.services.insights import insights_service
                ins_col = insights_service.generate_insights(
                    dataset_id=job.dataset_id,
                    version_id=job.dataset_version,
                    force_refresh=True,
                )
                job.artifact_refs["insights_id"] = ins_col.id
            except Exception as ins_exc:
                logger.error(f"[{job_id}] Insights generation failed (non-fatal): {ins_exc}", exc_info=True)

            # Completion & Finalization
            duration = round((time.perf_counter() - start_time) * 1000, 2)
            completion_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

            with self._lock:
                job.status = JobStatus.COMPLETED
                job.current_stage = JobStage.COMPLETED
                job.progress_pct = 100.0
                job.completed_at = completion_time
                job.duration_ms = duration
                self._persist_job(job)

            # Update dataset version status to READY
            dataset_service.mark_version_ready(
                dataset_id=job.dataset_id,
                version_id=job.dataset_version,
                source_analysis_id=analysis_res.id,
                source_quality_id=quality_res.id,
                source_eda_id=eda_res.id,
                image_count=val_res.total_validated_images if val_res else (discovery_res.discovered_image_files or 0),
                class_count=discovery_res.discovered_class_directories or 0,
            )

            # Emit completion event
            event_bus.emit(
                DatasetEventType.DATASET_ANALYSIS_COMPLETED,
                dataset_id=job.dataset_id,
                version_id=job.dataset_version,
                job_id=job_id,
                payload={
                    "analysis_id": analysis_res.id,
                    "quality_id": quality_res.id,
                    "eda_id": eda_res.id,
                    "duration_ms": duration,
                },
            )

            # Invalidate any historical comparisons involving this dataset
            comparison_service.invalidate_stale_comparisons(
                dataset_id=job.dataset_id,
                new_analysis_id=analysis_res.id,
            )

            logger.info(f"[{job_id}] Pipeline completed successfully in {duration}ms.")

        except Exception as exc:
            duration = round((time.perf_counter() - start_time) * 1000, 2)
            completion_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
            error_code = type(exc).__name__
            error_msg = str(exc)

            logger.error(f"[{job_id}] Pipeline failed: {error_code} - {error_msg}", exc_info=True)

            with self._lock:
                job.status = JobStatus.FAILED
                job.current_stage = JobStage.FAILED
                job.completed_at = completion_time
                job.duration_ms = duration
                job.error_code = error_code
                job.error_message = error_msg
                self._persist_job(job)

            # Mark version as failed, preserving any previous successful version
            dataset_service.mark_version_failed(
                dataset_id=job.dataset_id,
                version_id=job.dataset_version,
                error_message=error_msg,
            )

            event_bus.emit(
                DatasetEventType.DATASET_ANALYSIS_FAILED,
                dataset_id=job.dataset_id,
                version_id=job.dataset_version,
                job_id=job_id,
                payload={"error_code": error_code, "error_message": error_msg},
            )

    def shutdown(self) -> None:
        """Clean shutdown of worker threads."""
        with self._lock:
            if self._executor and not getattr(self._executor, "_shutdown", False):
                self._executor.shutdown(wait=False)


# Global job service singleton
job_service = JobService()
