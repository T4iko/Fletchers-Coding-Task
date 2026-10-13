from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def api(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)

    with TestClient(main.app) as client:
        def upload(path, filename=None, content_type=None):
            data = path.read_bytes() if hasattr(path, "read_bytes") else path
            name = filename or getattr(path, "name", "upload.bin")
            return client.post("/documents", files={"file": (name, data, content_type or "application/octet-stream")})

        yield SimpleNamespace(client=client, upload=upload, db_path=str(db_path), upload_dir=upload_dir)
