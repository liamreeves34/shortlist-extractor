"""Steps 2.5 and 2.9: service/connectors/greenhouse.py. Runs against
tests/fixtures/greenhouse_jobs.json through an httpx.MockTransport, never the real API."""

import re
from datetime import datetime

import httpx
import pytest

from service.connectors import greenhouse
from service.normalize import content_hash
from service.schemas import SourcePosting, Structured

INTERN_ID = "4000001"


@pytest.fixture
def postings(http):
    return greenhouse.fetch("acmerobotics", http=http)


@pytest.fixture
def intern(postings):
    (posting,) = postings
    return posting


def test_calls_the_board_api_with_content(http, boards):
    greenhouse.fetch("acmerobotics", http=http)
    (request,) = boards.requests
    assert request.method == "GET"
    assert str(request.url).startswith(greenhouse.API.format(token="acmerobotics"))
    assert request.url.params["content"] == "true"


def test_only_the_internship_comes_back(postings):
    # The fixture also has a full-time job, "Internal Audit Manager", and "International Sales".
    assert [p.external_id for p in postings] == [INTERN_ID]


def test_returns_source_postings(postings):
    assert all(isinstance(p, SourcePosting) for p in postings)


def test_fields_are_mapped(intern):
    assert intern.external_id == INTERN_ID  # a number in the API, a string here
    assert intern.title == "Software Engineering Intern, Summer 2027"
    assert intern.organization == "Acme Robotics"
    assert intern.location_raw == "Austin, TX"
    assert intern.url == "https://job-boards.greenhouse.io/acmerobotics/jobs/4000001"
    assert intern.updated_at == datetime.fromisoformat("2026-10-20T14:03:11-04:00")


def test_text_has_no_html(intern):
    assert not re.search(r"<[^>]+>", intern.text)
    assert "&lt;" not in intern.text
    assert "&amp;" not in intern.text


def test_text_is_readable(intern):
    flat = " ".join(intern.text.split())
    assert "Acme Robotics builds warehouse robots & the software that runs them." in flat
    assert "What you'll do" in flat
    assert "Write Python services for our fleet manager" in flat
    assert "our team’s page" in flat  # link text kept, raw curly quote untouched
    assert "$28" in flat and "$34 USD" in flat  # pay range split across <span>s
    assert "equal opportunity employer" in flat  # content after the <hr>


def test_hash_matches_the_text(intern):
    assert intern.content_hash.startswith("sha256:")
    assert intern.content_hash == content_hash(intern.text)


def test_hash_is_stable_across_fetches(http):
    first = greenhouse.fetch("acmerobotics", http=http)
    second = greenhouse.fetch("acmerobotics", http=http)
    assert [p.content_hash for p in first] == [p.content_hash for p in second]


def test_unknown_board_raises(http):
    with pytest.raises(greenhouse.UnknownBoard, match="nosuchboard"):
        greenhouse.fetch("nosuchboard", http=http)


def test_server_error_raises_http_status_error(http, boards):
    # The dispatcher (2.7) retries on this, so the adapter must not swallow it.
    boards.queue(httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        greenhouse.fetch("acmerobotics", http=http)


def test_empty_board_gives_no_postings(http, boards):
    boards.queue(httpx.Response(200, json={"jobs": [], "meta": {"total": 0}}))
    assert greenhouse.fetch("acmerobotics", http=http) == []


# ---------- 2.9: application_deadline is an API field ----------


def test_structured_has_a_deadline_field():
    assert Structured().deadline is None


def test_application_deadline_goes_into_structured(intern):
    assert intern.structured.deadline == "2026-12-01"


@pytest.mark.parametrize("absent", ["null", "missing"])
def test_no_application_deadline_is_none(http, boards, greenhouse_jobs, absent):
    # The real API sends `"application_deadline": null`; older boards may omit the key.
    job = greenhouse_jobs["jobs"][0]
    if absent == "null":
        job["application_deadline"] = None
    else:
        del job["application_deadline"]
    boards.queue(httpx.Response(200, json={"jobs": [job], "meta": {"total": 1}}))
    (posting,) = greenhouse.fetch("acmerobotics", http=http)
    assert posting.structured.deadline is None
