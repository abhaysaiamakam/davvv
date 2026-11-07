import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.storage.local import LocalStorageBackend


@pytest.fixture(scope="session")
def temp_storage_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def test_settings(temp_storage_dir):
    return Settings(
        STORAGE_BASE_DIR=temp_storage_dir,
        ENVIRONMENT="testing",
        DEBUG=True,
    )


@pytest.fixture
def storage(test_settings):
    backend = LocalStorageBackend(test_settings)
    backend.initialize()
    return backend


@pytest.fixture
def client(temp_storage_dir):
    os.environ["CROPLENS_STORAGE_BASE_DIR"] = str(temp_storage_dir)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

