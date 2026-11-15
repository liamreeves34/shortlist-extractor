"""Stretch: service/connectors/ashby.py. Runs against tests/fixtures/ashby_jobs.json
through an httpx.MockTransport, never the real API.

Ashby's public job board API returns {"apiVersion": "1", "jobs": [...]}. With
includeCompensation=true, each job carries compensation.summaryComponents.

Ashby raises the same UnknownBoard as Greenhouse, so main.py has one exception to map to 404.
"""

import re
from datetime import UTC, datetime

import httpx
import pytest

from service.connectors import ashby
from service.connectors.greenhouse import UnknownBoard
from service.normalize import content_hash
from service.schemas import Pay, SourcePosting

BY_TITLE = "0b8f6a2e-1c3d-4e5f-9a7b-2c4d6e8f0a1b"  # "Software Engineering Intern", paid hourly
BY_EMPLOYMENT_TYPE = (
    "5d7e9f1a-3b5c-4d7e-8f9a-1b3c5d7e9f2a"  # "Research Assistant, ...", employmentType "Intern"
)


@pytest.fixture
def postings(http):
    return {p.external_id: p for p in ashby.fetch("ferncliff", http=http)}


@pytest.fixture
def swe_intern(postings):
    return postings[BY_TITLE]


def one_job_board(ashby_jobs, **changes) -> dict:
    """The board with only the first job, with `changes` applied to it."""
    job = {**ashby_jobs["jobs"][0], **changes}
    return {"apiVersion": "1", "jobs": [job]}


def test_calls_the_job_board_api_with_compensation(http, boards):
    ashby.fetch("ferncliff", http=http)
    (request,) = boards.requests
    assert request.method == "GET"
    assert request.url.host == "api.ashbyhq.com"
    assert request.url.path == "/posting-api/job-board/ferncliff"
    assert request.url.params["includeCompensation"] == "true"


def test_internships_by_title_or_employment_type(postings):
    # Dropped: "Product Designer" and "Internal Tools Engineer", both FullTime.
    assert set(postings) == {BY_TITLE, BY_EMPLOYMENT_TYPE}


def test_returns_source_postings(postings):
    assert all(isinstance(p, SourcePosting) for p in postings.values())


def test_fields_are_mapped(swe_intern):
    assert swe_intern.title == "Software Engineering Intern"
    assert swe_intern.location_raw == "Denver, CO"
    assert swe_intern.url == f"https://jobs.ashbyhq.com/ferncliff/{BY_TITLE}"


def test_organization_falls_back_to_the_token(swe_intern):
    # The job board API carries no company name.
    assert swe_intern.organization == "ferncliff"


def test_published_at_becomes_a_utc_datetime(swe_intern):
    assert swe_intern.updated_at == datetime(2026, 10, 20, 15, 30, tzinfo=UTC)


def test_text_is_the_plain_description(swe_intern):
    flat = " ".join(swe_intern.text.split())
    assert "Ferncliff builds trail-mapping software for park services." in flat
    assert "You’ll ship features with the platform team." in flat
    assert "Write Python & TypeScript" in flat


def test_text_has_no_html(swe_intern):
    assert not re.search(r"<[^>]+>", swe_intern.text)
    assert "&amp;" not in swe_intern.text


def test_hash_matches_the_text(swe_intern):
    assert swe_intern.content_hash == content_hash(swe_intern.text)


def test_hash_is_stable_across_fetches(http):
    first = ashby.fetch("ferncliff", http=http)
    second = ashby.fetch("ferncliff", http=http)
    assert [p.content_hash for p in first] == [p.content_hash for p in second]


def test_employment_type_goes_into_commitment(postings):
    assert postings[BY_TITLE].structured.commitment == "Intern"
    assert postings[BY_EMPLOYMENT_TYPE].structured.commitment == "Intern"


@pytest.mark.parametrize(
    ("workplace_type", "work_mode"),
    [("Hybrid", "HYBRID"), ("Remote", "REMOTE"), ("OnSite", "ONSITE"), (None, None)],
)
def test_workplace_type_becomes_work_mode(http, boards, ashby_jobs, workplace_type, work_mode):
    boards.queue(httpx.Response(200, json=one_job_board(ashby_jobs, workplaceType=workplace_type)))
    (result,) = ashby.fetch("ferncliff", http=http)
    assert result.structured.work_mode == work_mode


def test_salary_component_becomes_pay(swe_intern):
    # The equity component next to it is ignored.
    assert swe_intern.structured.pay == Pay(min=35, max=45, period="HOUR", currency="USD")


def test_no_salary_component_is_none(postings):
    assert postings[BY_EMPLOYMENT_TYPE].structured.pay is None


def test_missing_compensation_is_none(http, boards, ashby_jobs):
    board = one_job_board(ashby_jobs)
    del board["jobs"][0]["compensation"]
    boards.queue(httpx.Response(200, json=board))
    (result,) = ashby.fetch("ferncliff", http=http)
    assert result.structured.pay is None


@pytest.mark.parametrize(
    ("interval", "period"),
    [("1 HOUR", "HOUR"), ("1 YEAR", "YEAR"), ("1 MONTH", "UNKNOWN")],
)
def test_salary_interval_maps_to_pay_period(http, boards, ashby_jobs, interval, period):
    board = one_job_board(ashby_jobs)
    board["jobs"][0]["compensation"]["summaryComponents"][0]["interval"] = interval
    boards.queue(httpx.Response(200, json=board))
    (result,) = ashby.fetch("ferncliff", http=http)
    assert result.structured.pay.period == period


def test_unknown_board_raises(http):
    with pytest.raises(UnknownBoard, match="nosuchboard"):
        ashby.fetch("nosuchboard", http=http)


def test_server_error_raises_http_status_error(http, boards):
    boards.queue(httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        ashby.fetch("ferncliff", http=http)


def test_empty_board_gives_no_postings(http, boards):
    boards.queue(httpx.Response(200, json={"apiVersion": "1", "jobs": []}))
    assert ashby.fetch("ferncliff", http=http) == []
