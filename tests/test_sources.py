"""Step 2.10: scripts/seed_sources.py and the sources.yaml it writes.

Only the offline parts are tested. Calling each board's API and check_sources.py
hit live APIs, so they're run by hand, never in CI.

Shape assumed for the script:
    find_tokens(urls: list[str]) -> dict[str, list[str]]
        {"greenhouse": [...], "lever": [...], "ashby": [...]}, each lowercased,
        de-duplicated, sorted.
"""

import re
from pathlib import Path

import yaml

from scripts.seed_sources import find_tokens

SOURCES_YAML = Path(__file__).resolve().parent.parent / "sources.yaml"

# Real tokens can contain dots ("arcteryx.com", "mistral.ai") and, on Ashby, spaces
# ("hippocratic ai", written Hippocratic%20AI in the URL). Never "%": tokens are stored decoded.
TOKEN_RE = r"[a-z0-9][a-z0-9._ -]{0,99}"

# Invented application URLs in the style of the Simplify listings JSON: tracking params, mixed case.
URLS = [
    "https://job-boards.greenhouse.io/acmerobotics/jobs/4000001?utm_source=Simplify&ref=Simplify",
    "https://boards.greenhouse.io/AcmeRobotics/jobs/4000009?utm_source=Simplify",
    "https://job-boards.greenhouse.io/birchwoodlabs/jobs/77",
    "https://jobs.lever.co/quillworks/3f2b6c1e-8a4d-4c7e-9b1a-0d5e6f7a8b91/apply?utm_source=Simplify",
    "https://jobs.lever.co/Quillworks/7c9d0e1f-2a3b-4c5d-8e6f-1a2b3c4d5e6f",
    "https://jobs.ashbyhq.com/ferncliff/0b8f6a2e-1c3d-4e5f-9a7b-2c4d6e8f0a1b",
    "https://jobs.ashbyhq.com/Ferncliff/5d7e9f1a-3b5c-4d7e-8f9a-1b3c5d7e9f2a/application?utm_source=Simplify",
    "https://www.greenhouse.io/careers",
    "https://jobs.lever.co/arcteryx.com/1a2b3c4d-0000-4000-8000-000000000000",
    "https://jobs.ashbyhq.com/Hippocratic%20AI/9f8e7d6c-0000-4000-8000-000000000000",
]


# ---------- find_tokens ----------


def test_finds_greenhouse_tokens_on_both_hosts():
    assert find_tokens(URLS)["greenhouse"] == ["acmerobotics", "birchwoodlabs"]


def test_finds_lever_tokens():
    assert find_tokens(URLS)["lever"] == ["arcteryx.com", "quillworks"]


def test_finds_ashby_tokens():
    assert find_tokens(URLS)["ashby"] == ["ferncliff", "hippocratic ai"]


def test_percent_encoded_tokens_are_decoded():
    assert "hippocratic%20ai" not in find_tokens(URLS)["ashby"]


def test_tokens_are_lowercased_and_deduplicated():
    tokens = find_tokens(URLS)
    for provider_tokens in tokens.values():
        assert provider_tokens == sorted({t.lower() for t in provider_tokens})


def test_tracking_params_and_paths_are_not_part_of_the_token():
    for token in (t for tokens in find_tokens(URLS).values() for t in tokens):
        assert re.fullmatch(TOKEN_RE, token), token


def test_non_board_links_are_ignored():
    tokens = find_tokens(URLS)
    assert "careers" not in tokens["greenhouse"]


def test_tokens_land_under_their_own_provider():
    tokens = find_tokens(URLS)
    assert "ferncliff" not in tokens["greenhouse"] + tokens["lever"]
    assert "quillworks" not in tokens["greenhouse"] + tokens["ashby"]


def test_embed_links_do_not_yield_embed_as_a_token():
    # Some boards link through the embed page; "embed" is not an employer.
    urls = ["https://boards.greenhouse.io/embed/job_app?for=acmerobotics&token=4000001"]
    assert "embed" not in find_tokens(urls)["greenhouse"]


def test_no_urls_gives_empty_lists():
    assert find_tokens([]) == {"greenhouse": [], "lever": [], "ashby": []}


# ---------- sources.yaml ----------


def load_sources() -> list[dict]:
    data = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and "sources" in data, "sources.yaml needs a top-level `sources:`"
    return data["sources"]


def test_sources_yaml_is_not_empty():
    assert load_sources()


def test_every_source_is_well_formed():
    for entry in load_sources():
        assert set(entry) == {"provider", "token", "organization", "enabled"}, entry
        assert entry["provider"] in {"greenhouse", "lever", "ashby"}, entry
        assert re.fullmatch(TOKEN_RE, entry["token"]), entry
        assert isinstance(entry["organization"], str) and entry["organization"].strip(), entry
        assert isinstance(entry["enabled"], bool), entry


def test_no_duplicate_sources():
    keys = [(e["provider"], e["token"]) for e in load_sources()]
    assert len(keys) == len(set(keys))
