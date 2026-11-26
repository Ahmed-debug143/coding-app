import pytest
from fastapi.testclient import TestClient

from aula import db, storage
from main import app


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "campusia-test-data"
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "DB_PATH", data_dir / "aula.db")
    monkeypatch.setattr(db, "UPLOAD_DIR", data_dir / "uploads")
    monkeypatch.setattr(storage, "UPLOAD_DIR", data_dir / "uploads")
    return data_dir


@pytest.fixture
def client(isolated_data_dir):
    with TestClient(app) as test_client:
        yield test_client
