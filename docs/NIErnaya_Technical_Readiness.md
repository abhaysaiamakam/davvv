# CropLens — Technical Readiness & NIErnaya Demonstration Guide

**Platform Version**: v0.1.0  
**Milestone**: M11 — Final Integration, Validation & NIErnaya Readiness  
**Target Modalities**: Tabular (CSV/TSV), Image Classification, Time-Series, COCO/YOLO Annotations  

---

## 1. System Architecture Overview

CropLens is a dynamic, extensible Dataset Analytics, EDA, Preprocessing, Feature Engineering, and Intelligence Platform designed for reproducible dataset evaluation and machine learning readiness assessment.

```text
       ┌─────────────────────────────────────────────────────────┐
       │                 CropLens Frontend (Web)                 │
       └────────────────────────────┬────────────────────────────┘
                                    │ REST API
       ┌────────────────────────────▼────────────────────────────┐
       │                   FastAPI Backend Service               │
       ├─────────────────────────────────────────────────────────┤
       │ • Dataset Lifecycle & Versioning (M6)                   │
       │ • Unified Analysis Pipeline (M2) & Job Queue            │
       │ • Data Quality Lab (M3)                                 │
       │ • EDA & Visualization Engine (M4)                      │
       │ • Dataset Comparison Engine (M5)                        │
       │ • Findings & Insights Intelligence (M7)                 │
       │ • Preprocessing & Cleaning Engine (M8)                  │
       │ • Feature Engineering & Feature Selection Engine (M9)   │
       │ • Dataset Readiness & Analytical Reports Engine (M10)   │
       └────────────────────────────┬────────────────────────────┘
                                    │ Storage Layer
       ┌────────────────────────────▼────────────────────────────┐
       │             Isolated Local Storage Backend               │
       │ • Immutability Protection & Streaming SHA-256 Fingerprint │
       │ • Version Extraction & Persisted Artifact Indices       │
       └─────────────────────────────────────────────────────────┘
```

---

## 2. NIErnaya Phase 2 Live Demonstration Workflow

The NIErnaya technical demonstration follows a 12-stage end-to-end evaluation flow:

1. **Dataset Upload & Registration (`POST /api/v1/datasets/upload`)**:
   - Ingests archive (`.zip`, `.tar.gz`) containing dataset files.
   - Computes streaming SHA-256 content fingerprint. If duplicate content is detected, reuses existing version without redundant re-analysis.
2. **Automated Discovery & Modality Detection (`GET /api/v1/datasets/{id}`)**:
   - Scans file tree and detects dataset modality (Tabular, Image, Time-Series, COCO/YOLO).
3. **Data Quality Audit (`GET /api/v1/datasets/{id}/quality-assessments`)**:
   - Evaluates integrity (corrupt images/unreadable files), class imbalance, duplicate impact (exact SHA-256 and perceptual pHash/dHash near-duplicates), and metadata consistency.
4. **Exploratory Data Analysis (`GET /api/v1/datasets/{id}/eda-reports`)**:
   - Generates summary statistics, distribution metrics, class proportions, and relationship matrices.
5. **Visualization Specification (`GET /api/v1/datasets/{id}/visualizations`)**:
   - Generates declarative chart specifications (bar charts, boxplots, histograms, scatter plots, correlation heatmaps).
6. **Findings & Insights (`GET /api/v1/datasets/{id}/insights`)**:
   - Generates evidence-backed recommendations categorized by severity (`critical`, `high`, `medium`, `low`, `info`).
7. **Preprocessing Preview (`POST /api/v1/datasets/{id}/preprocessing/preview`)**:
   - Previews cleaning operations (imputing missing values, deduplication, excluding corrupt images) without modifying dataset state.
8. **Applying Preprocessing & Version Derivation (`POST /api/v1/datasets/{id}/preprocessing/apply`)**:
   - Executes selected operations, creating an immutable derived version (e.g. `ver-{id}-2-{hash}`).
9. **Feature Engineering & Selection (`POST /api/v1/datasets/{id}/feature-engineering/apply`)**:
   - Evaluates polynomial features, lag/rolling time-series features, variance threshold selection, and correlation selection.
10. **PCA Transformation**:
    - Applies Principal Component Analysis for dimensionality reduction and records explained variance ratio.
11. **Dataset Readiness Assessment (`GET /api/v1/datasets/{id}/versions/{version}/readiness`)**:
    - Evaluates 5 readiness dimensions: Dataset Integrity, Data Quality, Analytical Suitability, Preprocessing Status, Feature Readiness.
12. **Analytical Report & PDF Export (`GET /api/v1/datasets/{id}/reports/{report_id}/download?format=pdf`)**:
    - Compiles evidence-backed analytical dossier and exports PDF document with table layouts and methodology provenance.

---

## 3. Dataset Versioning & Immutability Rules

1. **Immutable Source Archives**: Source uploaded datasets are stored in read-only version directories (`extract/{dataset_id}/v1`).
2. **Derived Version Provenance**: Preprocessing (M8) and Feature Engineering (M9) produce new derived dataset versions (`v2`, `v3`, etc.) while leaving parent versions untouched.
3. **Artifact Version Scoping**: All analysis results, quality assessments, EDA reports, visualizations, insights, readiness assessments, and analytical reports are version-scoped and stored independently in `results/{dataset_id}/{version_id}`.
4. **Content Fingerprint Deduplication**: Re-uploading an identical dataset archive yields the active version without duplicate job execution.

---

## 4. Test Commands & Verification Strategy

### Running Full Backend Test Suite
```bash
# Execute pytest suite across all 19 test modules
bash scripts/test-backend.sh
```

### Running E2E M11 Integration & NIErnaya Tests Only
```bash
cd apps/api
.venv/bin/pytest tests/test_m11_integration_and_niernaya.py -v
```

### Running Frontend Compilation & Lint Checks
```bash
# Verify TypeScript compilation and ESLint across workspaces
bun run build
bun run lint
```

---

## 5. Performance & Resource Characteristics

- **Ingestion & Discovery**: ~50ms for 1,000 files via streaming scanner.
- **Quality & Deduplication**: <200ms using streaming SHA-256 and perceptual 64-bit image hashes.
- **PDF Export Compilation**: <150ms using ReportLab document flowable layout.
- **Path Sanitization & Security**: All absolute paths are stripped; zero host paths (`/Users/`, `/home/`, `/var/`) are exposed in API payloads or PDF exports.
