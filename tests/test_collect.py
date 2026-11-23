"""Step 3.2: pipeline/collect.py, the write-once raw store and its manifest.

Runs against the fake boards (conftest.py `network`), never the real APIs, and writes
into a temporary directory instead of data/.
"""

import json

import httpx
import pytest
import yaml

from pipeline import collect

MANIFEST_KEYS = {"hash", "provider", "token", "organization", "external_id", "fetched_at"}

ALL_BOARDS = [
    {"provider": "greenhouse", "token": "acmerobotics"},  # 1 internship
    {"provider": "lever", "token": "quillworks"},  # 2 internships
    {"provider": "ashby", "token": "ferncliff"},  # 2 internships
]


@pytest.fixture
def run(tmp_path, monkeypatch, network):
    """Point collect.py at tmp_path; return a function that runs it over the given sources."""
    raw = tmp_path / "data" / "raw"
    manifest = tmp_path / "data" / "manifests" / "collected.jsonl"
    sources = tmp_path / "sources.yaml"
    monkeypatch.setattr(collect, "DATA_PATH", raw)
    monkeypatch.setattr(collect, "MANIFEST", manifest)
    monkeypatch.setattr(collect, "source_path", sources)

    def run_with(boards):
        entries = [{**b, "organization": b["token"], "enabled": True} for b in boards]
        sources.write_text(yaml.safe_dump({"sources": entries}), encoding="utf-8")
        collect.write_raw()
        files = sorted(raw.glob("*.json")) if raw.exists() else []
        lines = manifest.read_text(encoding="utf-8").splitlines() if manifest.exists() else []
        return files, [json.loads(line) for line in lines]

    return run_with


# ---------- the raw store ----------


def test_writes_one_file_per_posting(run):
    files, _ = run(ALL_BOARDS)
    assert len(files) == 5


def test_creates_missing_directories(run, tmp_path):
    assert not (tmp_path / "data").exists()
    files, _ = run(ALL_BOARDS)
    assert files


def test_file_is_named_by_hash_without_the_prefix(run):
    files, _ = run(ALL_BOARDS)
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        assert path.name == record["content_hash"].removeprefix("sha256:") + ".json"
        assert ":" not in path.name


def test_raw_record_has_source_and_posting_fields(run):
    files, _ = run([{"provider": "lever", "token": "quillworks"}])
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["provider"] == "lever"
    assert record["token"] == "quillworks"
    assert record["fetched_at"]
    for key in (
        "external_id",
        "title",
        "organization",
        "url",
        "text",
        "content_hash",
        "structured",
    ):
        assert key in record, key


def test_second_run_writes_nothing_new(run):
    files, lines = run(ALL_BOARDS)
    before = {path.name: path.read_text(encoding="utf-8") for path in files}
    files, lines_after = run(ALL_BOARDS)
    assert {path.name: path.read_text(encoding="utf-8") for path in files} == before
    assert lines_after == lines


def test_same_posting_from_two_sources_is_stored_once(run):
    files, lines = run(
        [{"provider": "greenhouse", "token": "acmerobotics"}] * 2,
    )
    assert len(files) == 1
    assert len(lines) == 1


# ---------- the manifest ----------


def test_one_manifest_line_per_new_posting(run):
    files, lines = run(ALL_BOARDS)
    assert len(lines) == len(files)
    file_hashes = {"sha256:" + path.stem for path in files}
    assert {line["hash"] for line in lines} == file_hashes


def test_manifest_has_ids_and_hashes_only(run):
    _, lines = run(ALL_BOARDS)
    for line in lines:
        assert set(line) == MANIFEST_KEYS, line


def test_manifest_never_contains_posting_text(run):
    files, lines = run(ALL_BOARDS)
    manifest_text = json.dumps(lines)
    for path in files:
        text = json.loads(path.read_text(encoding="utf-8"))["text"]
        first_sentence = text.strip().splitlines()[0]
        assert first_sentence not in manifest_text


def test_manifest_records_the_organization(run):
    _, lines = run([{"provider": "greenhouse", "token": "acmerobotics"}])
    assert lines[0]["organization"] == "Acme Robotics"


# ---------- failing boards ----------


def test_unknown_board_is_skipped_and_the_rest_collected(run):
    files, _ = run([{"provider": "greenhouse", "token": "nosuchboard"}, *ALL_BOARDS])
    assert len(files) == 5


def test_board_that_stays_down_is_skipped_and_the_rest_collected(run, network):
    network.queue(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    files, lines = run(ALL_BOARDS)  # greenhouse gets all three 503s
    assert len(files) == 4
    assert "greenhouse" not in {line["provider"] for line in lines}


def test_skipped_board_is_reported(run, capsys):
    run([{"provider": "greenhouse", "token": "nosuchboard"}])
    assert "nosuchboard" in capsys.readouterr().out


# ---------- politeness ----------


def test_pauses_between_boards(run, network):
    run(ALL_BOARDS)
    assert network.sleeps.count(1) >= len(ALL_BOARDS) - 1
