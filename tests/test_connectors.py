"""Steps 2.7 and 2.11: service/connectors/__init__.py, the dispatcher.

The `network` fixture (conftest.py) points every httpx.Client at the fake boards
and records time.sleep calls instead of sleeping.
"""

import httpx
import pytest

from service import connectors
from service.connectors.greenhouse import UnknownBoard

UA = "shortlist-extractor tests (test@example.com)"


def test_dispatches_to_greenhouse(network):
    postings = connectors.fetch("greenhouse", "acmerobotics", user_agent=UA)
    assert [p.external_id for p in postings] == ["4000001"]
    assert network.requests[0].url.host == "boards-api.greenhouse.io"


def test_dispatches_to_lever(network):
    postings = connectors.fetch("lever", "quillworks", user_agent=UA)
    assert len(postings) == 2
    assert network.requests[0].url.host == "api.lever.co"


def test_dispatches_to_ashby(network):
    postings = connectors.fetch("ashby", "ferncliff", user_agent=UA)
    assert len(postings) == 2
    assert network.requests[0].url.host == "api.ashbyhq.com"


def test_unknown_provider_raises_value_error(network):
    with pytest.raises(ValueError):
        connectors.fetch("workday", "acme", user_agent=UA)
    assert network.requests == []


# ---------- 2.11 politeness ----------


@pytest.mark.parametrize(
    ("provider", "token"),
    [("greenhouse", "acmerobotics"), ("lever", "quillworks"), ("ashby", "ferncliff")],
)
def test_every_request_sends_the_user_agent(network, provider, token):
    network.queue(httpx.Response(503))  # force a retry, so there are two requests to check
    connectors.fetch(provider, token, user_agent=UA)
    assert len(network.requests) == 2
    assert all(r.headers["user-agent"] == UA for r in network.requests)


def test_client_has_a_timeout(network):
    connectors.fetch("greenhouse", "acmerobotics", user_agent=UA)
    assert network.client_kwargs, "connectors.fetch should create its own httpx.Client"
    assert network.client_kwargs[0].get("timeout") is not None


# ---------- 2.7 retries ----------


def test_retries_server_errors_then_succeeds(network):
    network.queue(httpx.Response(503), httpx.Response(500))
    postings = connectors.fetch("greenhouse", "acmerobotics", user_agent=UA)
    assert len(postings) == 1
    assert len(network.requests) == 3
    assert network.sleeps == [1, 2]


def test_retries_connection_errors(network):
    network.queue(httpx.ConnectError("connection refused"))
    postings = connectors.fetch("lever", "quillworks", user_agent=UA)
    assert len(postings) == 2
    assert len(network.requests) == 2
    assert network.sleeps == [1]


def test_gives_up_after_three_tries(network):
    network.queue(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    with pytest.raises(httpx.HTTPError):
        connectors.fetch("greenhouse", "acmerobotics", user_agent=UA)
    assert len(network.requests) == 3
    assert network.sleeps == [1, 2]  # no pointless wait after the last try


def test_gives_up_after_three_connection_errors(network):
    network.queue(*(httpx.ConnectError("connection refused") for _ in range(3)))
    with pytest.raises(httpx.HTTPError):
        connectors.fetch("lever", "quillworks", user_agent=UA)
    assert len(network.requests) == 3


def test_never_retries_a_404(network):
    with pytest.raises(UnknownBoard):
        connectors.fetch("greenhouse", "nosuchboard", user_agent=UA)
    assert len(network.requests) == 1
    assert network.sleeps == []


def test_does_not_retry_other_client_errors(network):
    network.queue(httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        connectors.fetch("greenhouse", "acmerobotics", user_agent=UA)
    assert len(network.requests) == 1
    assert network.sleeps == []


# ---------- parse_job_url ----------

ASHBY_JOB = "0b8f6a2e-1c3d-4e5f-9a7b-2c4d6e8f0a1b"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://job-boards.greenhouse.io/AcmeRobotics/jobs/4000001?utm_source=Simplify",
            ("greenhouse", "acmerobotics", "4000001"),
        ),
        (
            "https://boards.greenhouse.io/acmerobotics/jobs/4000001",
            ("greenhouse", "acmerobotics", "4000001"),
        ),
        ("https://jobs.lever.co/quillworks/abc-123", ("lever", "quillworks", "abc-123")),
        ("https://jobs.lever.co/quillworks/abc-123/apply", ("lever", "quillworks", "abc-123")),
        (f"https://jobs.ashbyhq.com/ferncliff/{ASHBY_JOB}", ("ashby", "ferncliff", ASHBY_JOB)),
        (
            f"https://jobs.ashbyhq.com/Ferncliff/{ASHBY_JOB}/application?utm_source=Simplify",
            ("ashby", "ferncliff", ASHBY_JOB),
        ),
        (
            f"https://jobs.ashbyhq.com/Hippocratic%20AI/{ASHBY_JOB}",
            ("ashby", "hippocratic ai", ASHBY_JOB),
        ),
        ("https://jobs.lever.co/arcteryx.com/abc-123", ("lever", "arcteryx.com", "abc-123")),
    ],
)
def test_parse_job_url(url, expected):
    assert connectors.parse_job_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.ashbyhq.com/",
        "https://jobs.ashbyhq.com/ferncliff",
        f"https://jobs.ashbyhq.com/ferncliff/{ASHBY_JOB}/something-else",
        "https://www.greenhouse.io/careers",
        "https://boards.greenhouse.io/embed/job_app?for=acmerobotics&token=4000001",
        "https://evil.example.com/ferncliff/jobs/1",
        "not a url",
    ],
)
def test_parse_job_url_rejects_other_shapes(url):
    assert connectors.parse_job_url(url) is None
