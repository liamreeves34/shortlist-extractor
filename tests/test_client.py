import pytest

from client import ExtractionError, extract, fetch_source


def test_stub_mode_needs_no_server(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODE", "stub")
    result = extract(text="any posting", fields=["deadline"])
    assert result.fields["deadline"].value == "2026-11-15"


def test_live_mode_round_trip(api, monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODE", "live")
    result = extract(text="any posting", fields=["deadline", "pay"], http=api)
    assert result.fields["deadline"].value == "2026-11-15"
    assert result.fields["pay"].value["period"] == "HOUR"


def test_live_fetch_round_trip(api, monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODE", "live")
    postings = fetch_source(provider="lever", token="examplecorp", http=api)
    assert [p.external_id for p in postings] == ["examplecorp-1001", "examplecorp-1002"]


def test_client_stub_and_service_stub_agree(api, monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODE", "stub")
    offline = extract(text="x")
    monkeypatch.setenv("EXTRACTOR_MODE", "live")
    online = extract(text="x", http=api)
    assert offline.fields == online.fields


def test_unreachable_service_raises_extraction_error(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODE", "live")
    monkeypatch.setenv("EXTRACTOR_URL", "http://127.0.0.1:9")  # nothing listens here
    with pytest.raises(ExtractionError):
        extract(text="any posting")


def test_must_pass_text_or_url():
    with pytest.raises(ValueError):
        extract()
