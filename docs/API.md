# CropLens API Specification (`/api/v1`)

The CropLens backend is built with FastAPI. All endpoints return standard JSON responses and are prefixed by `/api/v1`.

Interactive Swagger UI documentation is available locally at:
`http://127.0.0.1:8000/api/v1/docs`

Interactive ReDoc documentation is available locally at:
`http://127.0.0.1:8000/api/v1/redoc`

---

## 1. Health

### `GET /api/v1/health`
Returns runtime operational status of the service.

#### Response (200 OK)
```json
{
  "status": "ok",
  "app_name": "CropLens API",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2026-11-07T09:30:00.000000+00:00"
}
```

---

## 2. Datasets

### `GET /api/v1/datasets`
Returns registered agricultural datasets (both curated reference sets and evaluator uploads).

#### Response (200 OK)
```json
{
  "total": 7,
  "items": [
    {
      "id": "icar-rice-maize",
      "name": "ICAR Rice and Maize Disease Dataset",
      "slug": "icar-rice-maize",
      "description": "Primary reference dataset from Indian Council of Agricultural Research (ICAR)...",
      "source": "icar_rice_maize",
      "is_curated": true,
      "is_uploaded": false,
      "created_at": "2026-11-07T09:30:00.000000+00:00",
      "updated_at": "2026-11-07T09:30:00.000000+00:00",
      "crops": ["Rice", "Maize"],
      "status": "registered",
      "tags": ["primary", "icar", "field-conditions", "cereal-crops"],
      "total_images": null,
      "total_classes": null,
      "storage_relative_path": "curated/icar-rice-maize"
    }
  ],
  "is_placeholder": true,
  "note": "Development registry. Metric fields are unpopulated until M2 pipeline execution."
}
```

### `GET /api/v1/datasets/{dataset_id}`
Returns metadata definition for a specific registered dataset.

#### Parameters
- `dataset_id` (string, path): Unique identifier or slug (e.g., `icar-rice-maize`).

#### Response (200 OK)
```json
{
  "id": "icar-rice-maize",
  "name": "ICAR Rice and Maize Disease Dataset",
  "slug": "icar-rice-maize",
  "description": "Primary reference dataset from Indian Council of Agricultural Research (ICAR)...",
  "source": "icar_rice_maize",
  "is_curated": true,
  "is_uploaded": false,
  "created_at": "2026-11-07T09:30:00.000000+00:00",
  "updated_at": "2026-11-07T09:30:00.000000+00:00",
  "crops": ["Rice", "Maize"],
  "status": "registered",
  "tags": ["primary", "icar", "field-conditions", "cereal-crops"],
  "total_images": null,
  "total_classes": null,
  "storage_relative_path": "curated/icar-rice-maize"
}
```

#### Response (404 Not Found)
```json
{
  "detail": "Dataset with ID or slug 'non-existent' was not found.",
  "status_code": 404,
  "error_code": "DATASET_NOT_FOUND",
  "timestamp": "2026-11-07T09:30:00.000000+00:00"
}
```

### `POST /api/v1/datasets/{dataset_id}/discover`
Triggers deterministic filesystem discovery on a registered dataset root. Scans supported image formats (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`, `.tif`, `.tiff`), indexes nested class directories, enforces symlink containment, and returns structured ingestion metadata.

#### Parameters
- `dataset_id` (string, path): Unique identifier or slug (e.g., `icar-rice-maize`).

#### Response (200 OK)
```json
{
  "dataset_id": "icar-rice-maize",
  "dataset_name": "ICAR Rice and Maize Disease Dataset",
  "dataset_source": "icar_rice_maize",
  "dataset_root_relative_path": "curated/icar-rice-maize",
  "discovery_status": "discovered",
  "discovered_image_files": 863,
  "discovered_class_directories": 19,
  "supported_extensions_encountered": [".jpg"],
  "classes": [
    {
      "class_name": "Maize/Disease/01_maydis_leaf_blight",
      "relative_path": "Maize/Disease/01_maydis_leaf_blight",
      "image_count": 50
    },
    {
      "class_name": "Rice/Disease/01_Bacterial_leaf_blight",
      "relative_path": "Rice/Disease/01_Bacterial_leaf_blight",
      "image_count": 50
    }
  ],
  "unreadable_or_inaccessible_count": 0,
  "ingestion_timestamp": "2026-11-07T10:05:50.862354+00:00",
  "warnings": [],
  "validated_image_files": null
}
```

#### Response (404 Not Found - Directory Missing)
```json
{
  "detail": "Dataset directory for 'paddy-doctor' does not exist on filesystem at 'curated/paddy-doctor'.",
  "status_code": 404,
  "error_code": "DATASET_DIRECTORY_NOT_FOUND",
  "timestamp": "2026-11-07T10:06:02.528855+00:00"
}
```

### `GET /api/v1/datasets/{dataset_id}/discovery`
Retrieves cached filesystem discovery metadata previously computed for the dataset.

#### Response (200 OK)
Returns the `DatasetDiscoveryResult` object.

### `POST /api/v1/datasets/{dataset_id}/duplicates/detect`
Executes chunked streaming SHA-256 content hashing across all images validated in M2.2. Identifies exact byte duplicates, assigns canonical representatives, detects cross-class leakage, and computes dataset and per-class redundancy statistics.

#### Parameters
- `dataset_id` (string, path): Unique identifier or slug (e.g., `icar-rice-maize`).

#### Response (200 OK)
Returns `DuplicateAnalysisResult`:
```json
{
  "dataset_id": "icar-rice-maize",
  "dataset_name": "ICAR Rice and Maize Disease Dataset",
  "analysis_timestamp": "2026-11-07T12:00:00Z",
  "total_eligible_images": 863,
  "successfully_hashed_images": 863,
  "hashing_failures": 0,
  "unique_content_groups": 846,
  "exact_duplicate_groups": 17,
  "duplicate_instances_count": 17,
  "images_in_duplicate_groups": 34,
  "duplicate_percentage": 1.97,
  "cross_class_duplicate_groups": 0,
  "groups": [
    {
      "group_id": "dup-04f7306e88042bb0",
      "sha256_hash": "04f7306e88042bb0...",
      "file_size_bytes": 128504,
      "image_count": 2,
      "representative": {
        "relative_path": "Rice/Insect-pests/06_Rice_skipper/7aaf2921-b68d-44fa-832d-067c2dd51e52.Jpg",
        "class_name": "Rice/Insect-pests/06_Rice_skipper",
        "file_size_bytes": 128504,
        "is_representative": true
      },
      "duplicates": [
        {
          "relative_path": "Rice/Insect-pests/06_Rice_skipper/8b598f45-1f7d-4998-894f-ae1302411840.Jpg",
          "class_name": "Rice/Insect-pests/06_Rice_skipper",
          "file_size_bytes": 128504,
          "is_representative": false
        }
      ],
      "classes_involved": ["Rice/Insect-pests/06_Rice_skipper"],
      "is_cross_class": false
    }
  ],
  "class_metrics": {
    "Rice/Insect-pests/06_Rice_skipper": {
      "class_name": "Rice/Insect-pests/06_Rice_skipper",
      "total_images": 73,
      "duplicate_instances": 4,
      "duplicate_percentage": 5.48
    }
  },
  "warnings": []
}
```

### `GET /api/v1/datasets/{dataset_id}/duplicates`
Retrieves previously computed duplicate analysis metadata for a dataset. Returns `404 DUPLICATE_ANALYSIS_NOT_FOUND` if analysis has not been executed yet.

---

## 3. Analyses

### `GET /api/v1/analyses`
Returns analysis runs. Initially returns an empty list in Milestone 1.

#### Response (200 OK)
```json
{
  "total": 0,
  "items": [],
  "is_placeholder": false,
  "note": "No active or historical analyses registered. Analysis engine will be connected in M2."
}
```

### `GET /api/v1/analyses/{analysis_id}`
Returns details for a specific analysis run.

#### Response (404 Not Found)
```json
{
  "detail": "Analysis job 'analysis-123' was not found.",
  "status_code": 404,
  "error_code": "ANALYSIS_NOT_FOUND",
  "timestamp": "2026-11-07T09:30:00.000000+00:00"
}
```

---

## 4. Standard Error Envelope

All unhandled exceptions and validation errors conform to `ApiErrorResponse`:

```json
{
  "detail": "Human-readable explanation of error.",
  "status_code": 400,
  "error_code": "MACHINE_READABLE_CODE",
  "timestamp": "2026-11-07T09:30:00.000000+00:00"
}
```

