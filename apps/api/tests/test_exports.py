import io
import json
import time
import uuid
import zipfile

from PIL import Image


def _uploaded_image_dataset(client):
    dataset_id = f"export-test-{uuid.uuid4().hex[:8]}"
    image_bytes = io.BytesIO()
    Image.new("RGB", (31, 19), (22, 144, 65)).save(image_bytes, format="PNG")
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("train/actual-class/leaf.png", image_bytes.getvalue())
        archive.writestr("labels/classes.txt", "actual-class\n")
    archive_bytes.seek(0)
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("images.zip", archive_bytes, "application/zip")}, data={"dataset_id": dataset_id, "name": "Export fixture"})
    assert uploaded.status_code == 202, uploaded.text
    response = uploaded.json()
    for _ in range(200):
        job = client.get(f"/api/v1/jobs/{response['job_id']}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.025)
    assert job["status"] == "completed", job
    return dataset_id, response["version_id"]


def _wait_export(client, export_id):
    for _ in range(200):
        result = client.get(f"/api/v1/exports/{export_id}")
        assert result.status_code == 200, result.text
        job = result.json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.025)
    raise AssertionError("Export job did not finish")


def test_versioned_readiness_json_export_contains_real_version_and_download_headers(client):
    dataset_id, version_id = _uploaded_image_dataset(client)
    started = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/exports", json={"export_type": "readiness", "format": "json"})
    assert started.status_code == 202, started.text
    job = _wait_export(client, started.json()["export_id"])
    assert job["status"] == "completed", job
    downloaded = client.get(job["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/json")
    assert downloaded.headers["content-disposition"].endswith(f'{job["filename"]}"')
    document = downloaded.json()
    assert document["version_id"] == version_id
    assert document["readiness_section"]["dataset_id"] == dataset_id
    cross_dataset = client.get(f"/api/v1/datasets/another-dataset/reports/{document['report_id']}")
    assert cross_dataset.status_code == 404
    cross_download = client.get(f"/api/v1/datasets/another-dataset/reports/{document['report_id']}/download")
    assert cross_download.status_code == 404


def test_dataset_zip_preserves_version_files_and_exports_actual_image_metadata(client):
    dataset_id, version_id = _uploaded_image_dataset(client)
    started = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/exports", json={"export_type": "dataset", "format": "zip"})
    assert started.status_code == 202, started.text
    job = _wait_export(client, started.json()["export_id"])
    assert job["status"] == "completed", job
    downloaded = client.get(job["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert "train/actual-class/leaf.png" in archive.namelist()
        assert "labels/classes.txt" in archive.namelist()
        assert "croplens-export-manifest.json" in archive.namelist()
        assert "image-metadata.csv" in archive.namelist()
        manifest = json.loads(archive.read("croplens-export-manifest.json"))
        assert manifest["dataset_id"] == dataset_id and manifest["version_id"] == version_id
        metadata = archive.read("image-metadata.csv").decode("utf-8-sig")
        assert "actual-class" in metadata and "31" in metadata and "19" in metadata


def test_csv_and_pdf_analysis_exports_have_matching_content_types_and_version_data(client):
    dataset_id, version_id = _uploaded_image_dataset(client)
    for export_format, expected_type in (("csv", "text/csv"), ("pdf", "application/pdf")):
        started = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/exports", json={"export_type": "eda", "format": export_format})
        assert started.status_code == 202, started.text
        job = _wait_export(client, started.json()["export_id"])
        assert job["status"] == "completed", job
        downloaded = client.get(job["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith(expected_type)
        assert job["filename"].endswith(f".{export_format}")
        if export_format == "csv":
            content = downloaded.content.decode("utf-8-sig")
            assert "version_id" in content and version_id in content
        else:
            assert downloaded.content.startswith(b"%PDF-")


def test_export_rejects_dataset_pdf_and_unknown_versions(client):
    dataset_id, version_id = _uploaded_image_dataset(client)
    unsupported = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/exports", json={"export_type": "dataset", "format": "pdf"})
    assert unsupported.status_code == 422
    missing = client.post(f"/api/v1/datasets/{dataset_id}/versions/missing/exports", json={"export_type": "comprehensive", "format": "json"})
    assert missing.status_code == 404


def test_image_dataset_csv_exports_metadata_not_pixel_data(client):
    dataset_id, version_id = _uploaded_image_dataset(client)
    started = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/exports", json={"export_type": "dataset", "format": "csv"})
    assert started.status_code == 202
    job = _wait_export(client, started.json()["export_id"])
    assert job["status"] == "completed", job
    downloaded = client.get(job["download_url"])
    assert downloaded.headers["content-type"].startswith("text/csv")
    content = downloaded.content.decode("utf-8-sig")
    assert "image_id,filename,class_name" in content
    assert "actual-class" in content and "31" in content and "19" in content


def test_single_tabular_csv_export_contains_original_records(client):
    dataset_id = f"tabular-export-{uuid.uuid4().hex[:8]}"
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("records.csv", "sample_id,measurement\nleaf-01,12.5\nleaf-02,8.0\n")
    archive_bytes.seek(0)
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("table.zip", archive_bytes, "application/zip")}, data={"dataset_id": dataset_id})
    assert uploaded.status_code == 202, uploaded.text
    upload = uploaded.json()
    for _ in range(200):
        job = client.get(f"/api/v1/jobs/{upload['job_id']}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.025)
    assert job["status"] == "completed", job
    version_id = upload["version_id"]
    started = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/exports", json={"export_type": "dataset", "format": "csv"})
    assert started.status_code == 202, started.text
    exported = _wait_export(client, started.json()["export_id"])
    assert exported["status"] == "completed", exported
    downloaded = client.get(exported["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content.decode("utf-8-sig") == "sample_id,measurement\nleaf-01,12.5\nleaf-02,8.0\n"
