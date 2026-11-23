"""Step 3.4: pipeline/label_gold.py. The answer parsers and the resume logic; never reads data/."""

import json

import pytest

from pipeline import label_gold as lg
from pipeline.label_gold import Invalid

# ---------- parsers ----------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("  Acme   Robotics ", "Acme Robotics"), ("-", None), ("", None)],
)
def test_parse_text(answer, expected):
    assert lg.parse_text(answer) == expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("Summer 2027", "Summer 2027"), ("summer 2027", "Summer 2027"), ("-", None), ("", None)],
)
def test_parse_start_term(answer, expected):
    assert lg.parse_start_term(answer) == expected


@pytest.mark.parametrize("answer", ["Summer", "2027", "June 2027", "Summer 27"])
def test_parse_start_term_rejects_other_shapes(answer):
    with pytest.raises(Invalid):
        lg.parse_start_term(answer)


def test_parse_date():
    assert lg.parse_date("2026-12-01") == "2026-12-01"
    assert lg.parse_date("-") is None
    with pytest.raises(Invalid):
        lg.parse_date("12/01/2026")
    with pytest.raises(Invalid):
        lg.parse_date("2026-02-30")


def test_parse_choice_by_number_or_name():
    assert lg.parse_choice("2", lg.CITIZENSHIP) == "WORK_AUTHORIZED"
    assert lg.parse_choice("us_person", lg.CITIZENSHIP) == "US_PERSON"
    with pytest.raises(Invalid):
        lg.parse_choice("9", lg.CITIZENSHIP)
    with pytest.raises(Invalid):
        lg.parse_choice("CITIZEN", lg.CITIZENSHIP)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("bm", ["BACHELOR", "MASTER"]),
        ("m b", ["BACHELOR", "MASTER"]),  # guide order, whatever order typed
        ("b,m,p", ["BACHELOR", "MASTER", "PHD"]),
        ("bb", ["BACHELOR"]),
        ("-", []),
        ("", []),
    ],
)
def test_parse_degrees(answer, expected):
    assert lg.parse_degrees(answer) == expected


def test_parse_degrees_rejects_unknown_letters():
    with pytest.raises(Invalid):
        lg.parse_degrees("bx")


def test_parse_skills():
    assert lg.parse_skills(" Python, SQL ,,Python , C++") == ["Python", "SQL", "C++"]
    assert lg.parse_skills("-") == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("25 32 h", {"min": 25, "max": 32, "period": "HOUR", "currency": "USD"}),
        ("32.50 32.50 h", {"min": 32.5, "max": 32.5, "period": "HOUR", "currency": "USD"}),
        ("80k 95k y", {"min": 80000, "max": 95000, "period": "YEAR", "currency": "USD"}),
        ("$80,000 $80,000 y", {"min": 80000, "max": 80000, "period": "YEAR", "currency": "USD"}),
        ("- 40 h", {"min": None, "max": 40, "period": "HOUR", "currency": "USD"}),
        ("6000 6000 u cad", {"min": 6000, "max": 6000, "period": "UNKNOWN", "currency": "CAD"}),
        ("", None),
        ("-", None),
    ],
)
def test_parse_pay(answer, expected):
    assert lg.parse_pay(answer) == expected


@pytest.mark.parametrize(
    "answer",
    ["25 32", "25 32 m", "32 25 h", "- - h", "abc 32 h", "25 32 h dollars", "1 2 3 4 5"],
)
def test_parse_pay_rejects_bad_input(answer):
    with pytest.raises(Invalid):
        lg.parse_pay(answer)


def test_pay_matches_the_service_schema():
    from service.schemas import Pay

    Pay(**lg.parse_pay("25 32 h"))
    Pay(**lg.parse_pay("6000 6000 u"))


# ---------- cross-field rules ----------


def fields(**changes):
    base = {
        "title": "Data Intern",
        "organization": "Acme",
        "deadline_type": "NONE_MENTIONED",
        "deadline": None,
    }
    return {**base, **changes}


def test_consistent_fields_pass():
    assert lg.check_consistency(fields()) == []
    assert lg.check_consistency(fields(deadline_type="FIXED", deadline="2026-12-01")) == []


def test_fixed_needs_a_date_and_a_date_needs_fixed():
    assert lg.check_consistency(fields(deadline_type="FIXED")) == []  # no year (guide v2)
    assert lg.check_consistency(fields(deadline_type="ROLLING", deadline="2026-12-01"))


def test_fixed_without_a_date_must_be_unsure():
    assert lg.must_be_unsure(fields(deadline_type="FIXED"))
    assert lg.must_be_unsure(fields(deadline_type="FIXED", deadline="2026-12-01")) == []


def test_location_default_only_for_us_city_state():
    assert lg.LOCATION_RE.fullmatch("Austin, TX; Washington, DC")
    assert not lg.LOCATION_RE.fullmatch("Toronto, ON")
    assert not lg.LOCATION_RE.fullmatch("London, UK")


def test_title_and_organization_are_required():
    assert lg.check_consistency(fields(title=None))


def test_allowed_values_match_the_guide():
    guide = (lg.PROJECT_ROOT / "docs" / "labeling_guide.md").read_text(encoding="utf-8")
    for value in (
        *lg.DEADLINE_TYPES,
        *lg.CITIZENSHIP,
        *lg.CLEARANCE,
        *lg.WORK_MODES,
        *lg.DEGREE_LEVELS,
    ):
        assert f"`{value}`" in guide, value


# ---------- resuming ----------


def test_labeled_hashes_and_append(tmp_path):
    gold = tmp_path / "labels" / "gold.jsonl"
    assert lg.labeled_hashes(gold) == set()
    lg.append_label({"hash": "sha256:a", "fields": {}}, gold)
    lg.append_label({"hash": "sha256:b", "fields": {"title": "Ingénieur"}}, gold)
    assert lg.labeled_hashes(gold) == {"sha256:a", "sha256:b"}
    lines = gold.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["fields"]["title"] == "Ingénieur"


def test_load_queue_reads_test_then_calibration(tmp_path, monkeypatch):
    monkeypatch.setattr(lg, "MANIFESTS", tmp_path)
    (tmp_path / "test.jsonl").write_text('{"hash": "sha256:t1"}\n{"hash": "sha256:t2"}\n')
    (tmp_path / "calibration.jsonl").write_text('{"hash": "sha256:c1"}\n')
    assert lg.load_queue(lg.GOLD_SPLITS) == [
        ("test", "sha256:t1"),
        ("test", "sha256:t2"),
        ("calibration", "sha256:c1"),
    ]


def test_raw_path_strips_the_prefix():
    assert lg.raw_path("sha256:abc").name == "abc.json"


def test_gold_path_is_looked_up_at_call_time(tmp_path, monkeypatch):
    # A default argument of `path=GOLD` would freeze the real data/ path at import time.
    monkeypatch.setattr(lg, "GOLD", tmp_path / "gold.jsonl")
    lg.append_label({"hash": "sha256:x", "fields": {}})
    assert lg.labeled_hashes() == {"sha256:x"}
