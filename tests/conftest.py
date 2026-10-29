import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from service.main import app

FIXTURES = Path(__file__).parent / "fixtures"

# The invented boards in tests/fixtures/. Any other token is a 404.
GREENHOUSE_TOKEN = "acmerobotics"
LEVER_TOKEN = "quillworks"
TEST_USER_AGENT = "shortlist-extractor tests (test@example.com)"


@pytest.fixture
def api(monkeypatch):
    """The service running in-process, in stub mode. No server, no network."""
    monkeypatch.setenv("EXTRACTOR_BACKEND", "stub")
    monkeypatch.setenv("CONNECTOR_MODE", "stub")
    with TestClient(app) as client:  # `with` runs the startup code that loads the backend
        yield client


@pytest.fixture
def greenhouse_jobs():
    return json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))


@pytest.fixture
def lever_postings():
    return json.loads((FIXTURES / "lever_postings.json").read_text(encoding="utf-8"))


class FakeBoards:
    """Stands in for the Greenhouse and Lever APIs, serving the fixture files.

    Records every request. `queue(...)` makes the next requests return the given
    responses (or raise the given exceptions) before normal routing resumes.
    """

    def __init__(self, greenhouse: dict, lever: list):
        self.greenhouse = greenhouse
        self.lever = lever
        self.requests: list[httpx.Request] = []
        self.client_kwargs: list[dict] = []  # filled by the `network` fixture
        self.sleeps: list[float] = []  # filled by the `network` fixture
        self._queued: list = []

    def queue(self, *outcomes):
        self._queued.extend(outcomes)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._queued:
            outcome = self._queued.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return self._route(request)

    def _route(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        host = request.url.host

        # /v1/boards/{token}/jobs and /v1/boards/{token}/jobs/{id}
        if host == "boards-api.greenhouse.io" and parts[:3] == ["v1", "boards", GREENHOUSE_TOKEN]:
            if parts[3:] == ["jobs"]:
                return httpx.Response(200, json=self.greenhouse)
            if len(parts) == 5 and parts[3] == "jobs":
                for job in self.greenhouse["jobs"]:
                    if str(job["id"]) == parts[4]:
                        return httpx.Response(200, json=job)
            return httpx.Response(404, json={"status": 404, "error": "Job not found"})

        # /v0/postings/{token} and /v0/postings/{token}/{id}
        if host == "api.lever.co" and parts[:3] == ["v0", "postings", LEVER_TOKEN]:
            if len(parts) == 3:
                return httpx.Response(200, json=self.lever)
            for posting in self.lever:
                if len(parts) == 4 and posting["id"] == parts[3]:
                    return httpx.Response(200, json=posting)

        return httpx.Response(404, json={"ok": False, "error": "Document not found"})


@pytest.fixture
def boards(greenhouse_jobs, lever_postings):
    return FakeBoards(greenhouse_jobs, lever_postings)


@pytest.fixture
def http(boards):
    """An httpx.Client wired to the fake boards, for calling an adapter directly."""
    with httpx.Client(transport=httpx.MockTransport(boards)) as client:
        yield client


@pytest.fixture
def network(monkeypatch, boards):
    """Every httpx.Client created during the test talks to the fake boards, and
    time.sleep returns at once. The code under test must call `httpx.Client(...)`
    and `time.sleep(...)` through their modules for this to reach it."""
    real_client = httpx.Client

    def client_with_fake_transport(*args, **kwargs):
        boards.client_kwargs.append(kwargs)
        return real_client(*args, **{**kwargs, "transport": httpx.MockTransport(boards)})

    monkeypatch.setattr(httpx, "Client", client_with_fake_transport)
    monkeypatch.setattr(time, "sleep", boards.sleeps.append)
    return boards


@pytest.fixture
def live_api(monkeypatch, network):
    """The service in CONNECTOR_MODE=live, with the fake boards as the internet."""
    monkeypatch.setenv("EXTRACTOR_BACKEND", "stub")
    monkeypatch.setenv("CONNECTOR_MODE", "live")
    monkeypatch.setenv("CONNECTOR_USER_AGENT", TEST_USER_AGENT)
    with TestClient(app) as client:
        yield client
