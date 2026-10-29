"""Step 2.8: the live paths in service/main.py, with CONNECTOR_MODE=live.

`live_api` (conftest.py) runs the service with the fake boards standing in for
the internet, so these go through main.py -> connectors -> adapter -> HTTP.
"""

import httpx
import jsonschema
import pytest

from scripts.export_schema import build_schemas

UA = "shortlist-extractor tests (test@example.com)"
GREENHOUSE_INTERN = "4000001"
LEVER_INTERN = "3f2b6c1e-8a4d-4c7e-9b1a-0d5e6f7a8b91"


class RecordingBackend:
    """Remembers the text it was given, so tests can see what a URL resolved to."""

    name = "recording"
    model_version = "test"

    def __init__(self):
        self.texts: list[str] = []

    def extract(self, text, fields):
        self.texts.append(text)
        return {}


@pytest.fixture
def backend(live_api):
    recording = RecordingBackend()
    live_api.app.state.backend = recording
    return recording


# ---------- /v1/sources/fetch ----------


def test_fetch_returns_real_internships(live_api):
    response = live_api.post(
        "/v1/sources/fetch", json={"provider": "greenhouse", "token": "acmerobotics"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "greenhouse"
    assert body["token"] == "acmerobotics"
    assert [p["external_id"] for p in body["postings"]] == [GREENHOUSE_INTERN]


def test_fetch_lever(live_api):
    response = live_api.post("/v1/sources/fetch", json={"provider": "lever", "token": "quillworks"})
    assert response.status_code == 200
    assert len(response.json()["postings"]) == 2


@pytest.mark.parametrize(
    ("provider", "token"), [("greenhouse", "acmerobotics"), ("lever", "quillworks")]
)
def test_live_fetch_satisfies_the_contract(live_api, provider, token):
    body = live_api.post("/v1/sources/fetch", json={"provider": provider, "token": token}).json()
    jsonschema.validate(body, build_schemas()["fetch_response.schema.json"])


def test_fetch_sends_the_configured_user_agent(live_api, network):
    live_api.post("/v1/sources/fetch", json={"provider": "greenhouse", "token": "acmerobotics"})
    assert network.requests[0].headers["user-agent"] == UA


@pytest.mark.parametrize("provider", ["greenhouse", "lever"])
def test_unknown_board_is_404(live_api, provider):
    response = live_api.post("/v1/sources/fetch", json={"provider": provider, "token": "nosuch"})
    assert response.status_code == 404


def test_upstream_down_is_502(live_api, network):
    network.queue(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    response = live_api.post(
        "/v1/sources/fetch", json={"provider": "greenhouse", "token": "acmerobotics"}
    )
    assert response.status_code == 502


def test_upstream_unreachable_is_502(live_api, network):
    network.queue(*(httpx.ConnectError("connection refused") for _ in range(3)))
    response = live_api.post("/v1/sources/fetch", json={"provider": "lever", "token": "quillworks"})
    assert response.status_code == 502


# ---------- /v1/extract with a URL ----------


@pytest.mark.parametrize(
    "url",
    [
        f"https://job-boards.greenhouse.io/acmerobotics/jobs/{GREENHOUSE_INTERN}",
        f"https://boards.greenhouse.io/acmerobotics/jobs/{GREENHOUSE_INTERN}",
    ],
)
def test_extract_from_a_greenhouse_url(live_api, backend, url):
    response = live_api.post("/v1/extract", json={"url": url, "fields": ["deadline"]})
    assert response.status_code == 200
    (text,) = backend.texts
    assert "Acme Robotics builds warehouse robots" in text
    assert "<" not in text


@pytest.mark.parametrize(
    "url",
    [
        f"https://jobs.lever.co/quillworks/{LEVER_INTERN}",
        f"https://jobs.lever.co/quillworks/{LEVER_INTERN}/apply",
    ],
)
def test_extract_from_a_lever_url(live_api, backend, url):
    response = live_api.post("/v1/extract", json={"url": url, "fields": ["pay"]})
    assert response.status_code == 200
    (text,) = backend.texts
    assert "Build data pipelines in Python" in text
    assert "<" not in text


def test_extract_url_response_names_the_backend(live_api, backend):
    url = f"https://jobs.lever.co/quillworks/{LEVER_INTERN}"
    body = live_api.post("/v1/extract", json={"url": url}).json()
    assert body["backend"] == "recording"


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co/",
        "https://jobs.lever.co/quillworks",
        "https://job-boards.greenhouse.io/acmerobotics",
        "https://job-boards.greenhouse.io/acmerobotics/departments/5",
    ],
)
def test_unknown_url_shape_is_422(live_api, network, url):
    response = live_api.post("/v1/extract", json={"url": url})
    assert response.status_code == 422
    assert network.requests == []  # rejected before any fetch


def test_url_off_the_allowlist_is_still_422(live_api, network):
    response = live_api.post("/v1/extract", json={"url": "https://evil.example.com/acme/jobs/1"})
    assert response.status_code == 422
    assert network.requests == []


def test_extract_url_on_unknown_board_is_404(live_api, backend):
    response = live_api.post(
        "/v1/extract",
        json={"url": "https://jobs.lever.co/nosuch/00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
    assert backend.texts == []
