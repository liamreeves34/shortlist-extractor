"""Step 2.10: scripts/seed_sources.py and the sources.yaml it writes.

Only the offline parts are tested. Calling each board's API and check_sources.py
hit live APIs, so they're run by hand, never in CI.

Shape assumed for the script:
    find_tokens(markdown: str) -> dict[str, list[str]]
        {"greenhouse": [...], "lever": [...]}, each lowercased, de-duplicated, sorted.
"""

import re
from pathlib import Path

import yaml

from scripts.seed_sources import find_tokens

SOURCES_YAML = Path(__file__).resolve().parent.parent / "sources.yaml"

# Invented rows in the style of the Simplify README: a table of HTML links with tracking params.
README = """
| Company | Role | Location | Application |
| --- | --- | --- | --- |
| **Acme Robotics** | Software Engineering Intern | Austin, TX | <a href="https://job-boards.greenhouse.io/acmerobotics/jobs/4000001?utm_source=Simplify&ref=Simplify"><img src="apply.png"></a> |
| ↳ | Hardware Intern | Austin, TX | <a href="https://boards.greenhouse.io/AcmeRobotics/jobs/4000009?utm_source=Simplify">Apply</a> |
| **Birchwood Labs** | ML Intern | Remote | <a href="https://job-boards.greenhouse.io/birchwoodlabs/jobs/77">Apply</a> |
| **Quillworks** | Data Intern | NYC | <a href="https://jobs.lever.co/quillworks/3f2b6c1e-8a4d-4c7e-9b1a-0d5e6f7a8b91/apply?utm_source=Simplify">Apply</a> |
| ↳ | Design Intern | NYC | <a href="https://jobs.lever.co/Quillworks/7c9d0e1f-2a3b-4c5d-8e6f-1a2b3c4d5e6f">Apply</a> |
| **Ferncliff** | SWE Intern | Denver, CO | <a href="https://jobs.ashbyhq.com/ferncliff/1234">Apply</a> |
| **Greenhouse itself** | Marketing Intern | NYC | <a href="https://www.greenhouse.io/careers">Apply</a> |
"""


# ---------- find_tokens ----------


def test_finds_greenhouse_tokens_on_both_hosts():
    assert find_tokens(README)["greenhouse"] == ["acmerobotics", "birchwoodlabs"]


def test_finds_lever_tokens():
    assert find_tokens(README)["lever"] == ["quillworks"]


def test_tokens_are_lowercased_and_deduplicated():
    tokens = find_tokens(README)
    for provider_tokens in tokens.values():
        assert provider_tokens == sorted({t.lower() for t in provider_tokens})


def test_tracking_params_and_paths_are_not_part_of_the_token():
    for token in find_tokens(README)["greenhouse"] + find_tokens(README)["lever"]:
        assert re.fullmatch(r"[a-z0-9_-]+", token), token


def test_non_board_links_are_ignored():
    tokens = find_tokens(README)
    assert "careers" not in tokens["greenhouse"]
    assert "ferncliff" not in tokens["greenhouse"] + tokens["lever"]


def test_embed_links_do_not_yield_embed_as_a_token():
    # Some boards link through the embed page; "embed" is not an employer.
    md = '<a href="https://boards.greenhouse.io/embed/job_app?for=acmerobotics&token=4000001">x</a>'
    assert "embed" not in find_tokens(md)["greenhouse"]


def test_no_links_gives_empty_lists():
    assert find_tokens("nothing here") == {"greenhouse": [], "lever": []}


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
        assert re.fullmatch(r"[a-z0-9_-]{1,100}", entry["token"]), entry
        assert isinstance(entry["organization"], str) and entry["organization"].strip(), entry
        assert isinstance(entry["enabled"], bool), entry


def test_no_duplicate_sources():
    keys = [(e["provider"], e["token"]) for e in load_sources()]
    assert len(keys) == len(set(keys))
