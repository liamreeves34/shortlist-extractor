import pytest
from fastapi.testclient import TestClient

from service.main import app


@pytest.fixture
def api(monkeypatch):
    """The service running in-process, in stub mode. No server, no network."""
    monkeypatch.setenv("EXTRACTOR_BACKEND", "stub")
    monkeypatch.setenv("CONNECTOR_MODE", "stub")
    with TestClient(app) as client:  # `with` runs the startup code that loads the backend
        yield client
