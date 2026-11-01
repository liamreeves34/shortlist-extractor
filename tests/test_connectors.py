"""Steps 2.7 and 2.11: service/connectors/__init__.py, the dispatcher.

The `network` fixture (conftest.py) points every httpx.Client at the fake boards
and records time.sleep calls instead of sleeping.
"""

import httpx
import pytest
from service.connectors.greenhouse import UnknownBoard

from service import connectors

UA = "shortlist-extractor tests (test@example.com)"


def test_dispatches_to_greenhouse(network):
    postings = connectors.fetch("greenhouse", "acmerobotics", user_agent=UA)
    assert [p.external_id for p in postings] == ["4000001"]
    assert network.requests[0].url.host == "boards-api.greenhouse.io"


def test_dispatches_to_lever(network):
    postings = connectors.fetch("lever", "quillworks", user_agent=UA)
    assert len(postings) == 2
    assert network.requests[0].url.host == "api.lever.co"


def test_unknown_provider_raises_value_error(network):
    with pytest.raises(ValueError):
        connectors.fetch("workday", "acme", user_agent=UA)
    assert network.requests == []


# ---------- 2.11 politeness ----------


@pytest.mark.parametrize(
    ("provider", "token"), [("greenhouse", "acmerobotics"), ("lever", "quillworks")]
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
