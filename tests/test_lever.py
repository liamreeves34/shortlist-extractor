"""Step 2.6: service/connectors/lever.py. Runs against tests/fixtures/lever_postings.json
through an httpx.MockTransport, never the real API.

Lever raises the same UnknownBoard as Greenhouse, so main.py has one exception to map to 404.
"""

import re
from datetime import UTC, datetime

import httpx
import pytest
from service.connectors.lever import UnknownBoard

from service.connectors import lever
from service.normalize import content_hash
from service.schemas import Pay, SourcePosting

BY_COMMITMENT = (
    "3f2b6c1e-8a4d-4c7e-9b1a-0d5e6f7a8b91"  # "Data Engineer", commitment "Intern (Hourly)"
)
BY_TITLE = "7c9d0e1f-2a3b-4c5d-8e6f-1a2b3c4d5e6f"  # "...Intern, Summer 2027", no commitment


@pytest.fixture
def postings(http):
    return {p.external_id: p for p in lever.fetch("quillworks", http=http)}


@pytest.fixture
def data_engineer(postings):
    return postings[BY_COMMITMENT]


def test_calls_the_postings_api_as_json(http, boards):
    lever.fetch("quillworks", http=http)
    (request,) = boards.requests
    assert request.method == "GET"
    assert request.url.host == "api.lever.co"
    assert request.url.path == "/v0/postings/quillworks"
    assert request.url.params["mode"] == "json"


def test_internships_by_title_or_commitment(postings):
    # Dropped: "Product Designer" and "Internal Communications Lead", both Full-time.
    assert set(postings) == {BY_COMMITMENT, BY_TITLE}


def test_returns_source_postings(postings):
    assert all(isinstance(p, SourcePosting) for p in postings.values())


def test_fields_are_mapped(data_engineer):
    assert data_engineer.title == "Data Engineer"
    assert data_engineer.location_raw == "New York, NY"
    assert data_engineer.url == f"https://jobs.lever.co/quillworks/{BY_COMMITMENT}"


def test_organization_falls_back_to_the_token(data_engineer):
    # Lever postings carry no company name.
    assert data_engineer.organization == "quillworks"


def test_created_at_milliseconds_become_a_utc_datetime(data_engineer):
    assert data_engineer.updated_at == datetime.fromtimestamp(1792944000, UTC)


def test_text_combines_description_lists_and_additional(data_engineer):
    flat = " ".join(data_engineer.text.split())
    assert "Quillworks makes note-taking tools for research teams." in flat
    assert "You’ll join a small data team." in flat
    assert "Build data pipelines in Python" in flat
    assert "Keep our reports & dashboards honest" in flat  # list HTML is decoded
    assert "Applications close December 5, 2026." in flat
    assert "&amp;" not in data_engineer.text


def test_text_has_no_html(data_engineer):
    assert not re.search(r"<[^>]+>", data_engineer.text)


def test_hash_matches_the_text(data_engineer):
    assert data_engineer.content_hash == content_hash(data_engineer.text)


def test_hash_is_stable_across_fetches(http):
    first = lever.fetch("quillworks", http=http)
    second = lever.fetch("quillworks", http=http)
    assert [p.content_hash for p in first] == [p.content_hash for p in second]


def test_commitment_goes_into_structured(postings):
    assert postings[BY_COMMITMENT].structured.commitment == "Intern (Hourly)"
    assert postings[BY_TITLE].structured.commitment is None


def test_workplace_type_becomes_work_mode(postings):
    assert postings[BY_COMMITMENT].structured.work_mode == "HYBRID"
    assert postings[BY_TITLE].structured.work_mode == "REMOTE"


def test_salary_range_becomes_pay(postings):
    assert postings[BY_COMMITMENT].structured.pay == Pay(
        min=30, max=38, period="per-hour-wage", currency="USD"
    )


def test_missing_salary_range_is_none(postings):
    assert postings[BY_TITLE].structured.pay is None

def test_unknown_board_raises(http):
    with pytest.raises(UnknownBoard, match="nosuchboard"):
        lever.fetch("nosuchboard", http=http)


def test_server_error_raises_http_status_error(http, boards):
    boards.queue(httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        lever.fetch("quillworks", http=http)


def test_empty_board_gives_no_postings(http, boards):
    boards.queue(httpx.Response(200, json=[]))
    assert lever.fetch("quillworks", http=http) == []
