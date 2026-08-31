from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="phantomfish-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["STORAGE_DIR"] = str(Path(_tmp) / "uploads")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SEED_PASSWORD"] = "test1234"
os.environ["DEFAULT_RATE_TYPE"] = "oficial"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    resp = client.post(
        "/login", data={"username": "jairo", "password": "test1234"}, follow_redirects=False
    )
    assert resp.status_code == 303
    return client
