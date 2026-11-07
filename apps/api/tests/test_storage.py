import pytest
from app.core.errors import PathTraversalError


def test_storage_initialization(storage):
    assert storage.base_dir.exists()
    assert storage.uploads_dir.exists()
    assert storage.extract_dir.exists()
    assert storage.results_dir.exists()
    assert storage.curated_dir.exists()


def test_safe_upload_path(storage):
    path = storage.get_upload_path("dataset-123", "archive.zip")
    assert path.name == "archive.zip"
    assert "dataset-123" in str(path)
    assert storage.is_safe_path(path)


def test_path_sanitization_does_not_leak_absolute_path(storage):
    path = storage.get_upload_path("icar-ds", "samples.zip")
    sanitized = storage.sanitize_relative_path(path)
    # The sanitized path should not contain the machine's absolute root path
    assert str(storage.base_dir) not in sanitized
    assert sanitized.startswith("uploads/icar-ds")


def test_path_traversal_detection(storage):
    # Attempt directory traversal via malicious dataset identifier
    with pytest.raises(PathTraversalError):
        storage.get_upload_path("../../etc", "malicious.zip")


def test_storage_status_structure(storage):
    status = storage.get_storage_status()
    assert status["initialized"] is True
    assert status["storage_type"] == "local_filesystem"
    assert "disk_free_gb" in status
    assert "directories_ready" in status

