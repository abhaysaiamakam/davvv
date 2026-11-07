# CropLens Architecture Document

## Overview

CropLens is an interactive agricultural dataset intelligence platform engineered for NIErnaya Phase 2. The platform performs dataset exploration, rigorous data quality assessment (corruption checks, SHA-256 duplicate detection, perceptual hash near-duplicate clustering), exploratory data analysis (EDA), and cross-dataset comparative analysis.

The platform is designed around a single, shared Python analysis engine serving both curated reference datasets (e.g., ICAR Rice and Maize) and evaluator-provided datasets uploaded during testing.

## Monorepo Layout

```
croplens/
├── apps/
│   ├── web/                     # Next.js 14 App Router frontend
│   │   ├── src/
│   │   │   ├── app/             # Navigable route pages (8 workflows)
│   │   │   ├── components/      # Reusable sidebar, header, cards, states
│   │   │   ├── hooks/           # Typed React hooks (useApiHealth, etc.)
│   │   │   ├── lib/             # API client, utility functions
│   │   │   └── types/           # Type re-exports
│   │   └── public/
│   │
│   └── api/                     # FastAPI backend application
│       ├── app/
│       │   ├── api/             # Versioned API routes (/api/v1)
│       │   ├── core/            # Config, exceptions, logging
│       │   ├── schemas/         # Pydantic validation contracts
│       │   ├── services/        # Business logic & dataset registry
│       │   └── storage/         # Storage abstraction & path guard
│       ├── tests/               # Pytest suite
│       └── requirements.txt
│
├── packages/
│   └── shared-types/            # Canonical TypeScript contracts
│
├── docs/                        # Architecture & API specifications
├── scripts/                     # Independent runner scripts
├── .gitignore
├── README.md
└── package.json                 # Monorepo workspace configuration
```

## Core Subsystems

### 1. Presentation Layer (`apps/web`)
- **Framework**: Next.js 14 (App Router), TypeScript, Tailwind CSS.
- **Design Language**: Professional dark agricultural analytics theme (green-black `#080e0c`, emerald `#10b981`, mint `#34d399`).
- **Core Components**:
  - `Sidebar`: Persistent left navigation with active path indicator and status badges.
  - `Header`: Dynamic breadcrumbs, live API health status polling, and API docs link.
  - `PageContainer`: Standard layout envelope for all feature routes.
  - `DashboardCard`: Structured analytics card with header badges, icons, and action slots.
  - `DatasetSelector`: Select control for switching between registered and uploaded datasets.
  - `LoadingState`, `ErrorState`, `EmptyState`: Resilient feedback components.

### 2. Service Layer (`apps/api`)
- **Framework**: FastAPI with application factory pattern (`create_app()`).
- **Configuration**: Pydantic `BaseSettings` reading environment variables with default fallbacks.
- **Error Handling**: Centralized exception handlers converting exceptions to standard `ApiErrorResponse` envelopes.
- **Endpoints (`/api/v1`)**:
  - `GET /api/v1/health`: API status, app name, version, and environment.
  - `GET /api/v1/datasets`: Curated and uploaded dataset registry.
  - `GET /api/v1/datasets/{id}`: Detailed dataset metadata.
  - `GET /api/v1/analyses`: Job queue and cached analysis runs.

### 3. Storage Abstraction (`app.storage`)
- **Interface**: `StorageBackend` abstract class.
- **Implementation**: `LocalStorageBackend` operating with isolated paths for:
  - `uploads/`: Ingested archives and blind test batches.
  - `extracted/`: Isolated extraction directories for dataset images.
  - `results/`: Cached JSON metrics, perceptual hashes, and reports.
  - `curated/`: Reference benchmarks (e.g. ICAR Rice and Maize).
- **Security & Masking**: Strictly enforces parent directory containment to reject directory traversal attempts (`PathTraversalError`). All relative paths returned to the client are sanitized to prevent exposing internal host operating system paths.

### 4. Shared Contract Parity (`packages/shared-types` ↔ `app.schemas`)
Both layers share 1:1 parity across:
- `DatasetMetadata`: Dataset identity, crop lists, status, and analytical counts.
- `DatasetSource`: Enumeration of recognized reference origins.
- `AnalysisStatus` & `AnalysisSummary`: Job execution state and computed metrics.
- `HealthResponse`: System health status payload.
- `ApiErrorResponse`: Centralized HTTP error envelope.

## Analytical Integrity Principles
1. **Zero Fabricated Metrics**: Uncalculated statistics (image counts, class totals, duplicate counts) are represented as `null` until the Milestone 2 Python pipeline executes on real files.
2. **Deterministic Processing**: Hashing and deduplication routines produce reproducible outputs across runs.
3. **Shared Pipeline Architecture**: Curated reference datasets and user/evaluator uploaded datasets execute the same Python analysis routines.

