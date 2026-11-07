# CropLens

> **Interactive Agricultural Dataset Intelligence Platform for NIErnaya Phase 2**

CropLens is an agricultural dataset intelligence platform engineered for dataset exploration, data cleaning and validation, missing-value analysis, exploratory data analysis (EDA), image quality analysis, and cross-dataset comparison.

The platform establishes a shared Python analysis engine for both curated reference benchmarks (primary anchor: **ICAR Rice and Maize**) and evaluator-uploaded datasets.

---

## Milestone 1: Project Foundation

This repository contains the completed **Milestone 1: Project Foundation**:
- Clean monorepo structure separating frontend, backend, shared types, and documentation.
- Polished Next.js 14 App Router frontend with dark agricultural analytics design.
- Complete 8-route navigable interface structure with reusable dashboard components.
- Modular FastAPI backend application factory with versioned endpoints (`/api/v1`).
- Shared contract definitions with 1:1 parity between TypeScript and Pydantic.
- Secure local storage abstraction with directory isolation and path traversal guards.
- Backend automated test suite with 100% test pass rate.
- Frontend zero-warning ESLint and strict TypeScript type-checking.

---

## Monorepo Layout

```text
croplens/
├── apps/
│   ├── web/                    # Next.js 14 App Router client (TypeScript + Tailwind)
│   └── api/                    # FastAPI backend service (Python 3.11+)
├── packages/
│   └── shared-types/           # Shared TypeScript contracts
├── docs/                       # Architecture and API specifications
├── scripts/                    # Independent runner scripts
├── .gitignore
├── .env.example
├── README.md
└── package.json                # Root workspace configuration
```

---

## Technology Stack

### Frontend (`apps/web`)
- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS with custom dark agricultural palette (`#080e0c` background, emerald/mint accents)
- **Icons**: Lucide React
- **Visualization Foundation**: Prepared for Apache ECharts integration

### Backend (`apps/api`)
- **Framework**: FastAPI
- **Validation**: Pydantic v2 & Pydantic Settings
- **ASGI Server**: Uvicorn
- **Testing**: Pytest & HTTPX TestClient

### Shared Contracts (`packages/shared-types`)
- Standardized interfaces for Dataset Metadata, Dataset Source, Analysis Status, Analysis Summary, and API Error Responses.

---

## Getting Started

### Prerequisites
- **Node.js**: v18.0.0+ (Tested on v26+)
- **Python**: 3.11+ (Tested on Python 3.14)
- **uv** (recommended for ultra-fast Python package resolution) or standard `pip`

---

### Installation

1. **Install Frontend Dependencies:**
   ```bash
   npm install
   ```

2. **Setup Backend Python Environment:**
   ```bash
   cd apps/api
   # Using uv:
   uv venv .venv
   uv pip install --python .venv -r requirements.txt

   # Or using standard venv:
   # python3 -m venv .venv
   # source .venv/bin/activate
   # pip install -r requirements.txt
   cd ../..
   ```

3. **Configure Environment:**
   ```bash
   cp .env.example .env
   cp apps/web/.env.example apps/web/.env.local
   cp apps/api/.env.example apps/api/.env
   ```

---

## Running the Applications

The frontend and backend can be run together or completely independently.

### Option A: Using Convenience Scripts

- **Run Frontend (Web)**:
  ```bash
  ./scripts/dev-frontend.sh
  ```
  Web client will be available at [http://localhost:3000](http://localhost:3000).

- **Run Backend (API)**:
  ```bash
  ./scripts/dev-backend.sh
  ```
  API service will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).
  Interactive Swagger UI: [http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs).

### Option B: Using npm Workspace Commands

```bash
# Start frontend dev server
npm run dev:web

# Run backend tests
npm run test:api
```

---

## Verification & Quality Checks

Run the verification suite locally:

```bash
# 1. Frontend TypeScript Validation
npm run type-check:web

# 2. Frontend ESLint
npm run lint:web

# 3. Frontend Production Build
npm run build:web

# 4. Backend Pytest Suite
./scripts/test-backend.sh
```

---

## API Endpoints Implemented in M1

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health status, version, and environment. |
| `GET` | `/api/v1/datasets` | Registered agricultural benchmarks catalog. |
| `GET` | `/api/v1/datasets/{id}` | Specific dataset metadata inspection. |
| `GET` | `/api/v1/analyses` | Analysis jobs list (initially empty list in M1). |
| `GET` | `/api/v1/analyses/{id}` | Analysis run details (returns 404 in M1). |

---

## Navigable Frontend Routes

| Route | View Name | Purpose |
| :--- | :--- | :--- |
| `/` | System Overview | Architecture cards, live API health, and dataset catalog. |
| `/datasets` | Dataset Explorer | Curated benchmarks (ICAR primary + 6 supplementary). |
| `/quality` | Data Quality Lab | 5 quality pillar architectures (corruption, duplicates, pHash). |
| `/eda` | EDA & Visualizations | Planned ECharts visualizations for class/color/geometry. |
| `/comparison` | Dataset Comparison | Cross-dataset domain shift and taxonomy mapping. |
| `/insights` | Findings & Insights | Field pathology critique and automated findings log. |
| `/reports` | Methodology & Reports | NIErnaya Phase 2 evaluation rubric and audit protocol. |
| `/analyze` | Evaluator Upload | Dropzone wireframe and validation staging for evaluator uploads. |

---

## Milestone 2 Preparation

The foundation is ready for Milestone 2:
- **Shared Analysis Engine**: Architecture is prepared for Pandas, NumPy, OpenCV, and Pillow integration.
- **Storage Subsystem**: Isolated directory paths are configured for uploads, extractions, and cached results.
- **Contract Stability**: Frontend and backend share identical schemas, enabling seamless ingestion of computed statistics without architectural rework.

