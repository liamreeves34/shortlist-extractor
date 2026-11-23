"""Steps 5.1-5.4: the teacher backend and label_teacher, with a fake client (no network).

All posting text here is invented.
"""

import json
from types import SimpleNamespace

import pytest

from pipeline import label_teacher
from service.backends import load_backend, teacher
from service.backends.teacher import (
    TeacherBackend,
    output_format,
    output_model,
    quote_found,
    review_reasons,
)
from service.normalize import render_posting
from service.schemas import ALL_FIELDS, Pay

POSTING = {
    "title": "Robotics Software Intern (Summer 2027)",
    "organization": "acmerobotics",
    "location_raw": "Austin, Texas, United States",
    "text": (
        "We’re Acme Robotics! We build warehouse robots.\n"
        "Pursuing a BS or MS in CS.\n"
        "Experience with Python and C++.\n"
        "Pay: $30–$38/hr\n"
        "Applications close December 1, 2026."
    ),
}
TEXT = render_posting(POSTING)

# A full, correct answer for TEXT. Tests copy it and change one thing.
ANSWER = {
    "title": {
        "value": "Robotics Software Intern (Summer 2027)",
        "evidence": "Robotics Software Intern (Summer 2027)",
    },
    "organization": {"value": "Acme Robotics", "evidence": "We're Acme Robotics!"},  # straight '
    "location": {"value": "Austin, TX", "evidence": "Location: Austin, Texas, United States"},
    "start_term": {"value": "Summer 2027", "evidence": "Robotics Software Intern (Summer 2027)"},
    "deadline": {"value": "2026-12-01", "evidence": "Applications close December 1, 2026."},
    "deadline_type": {"value": "FIXED", "evidence": "Applications close December 1, 2026."},
    "degree_levels": {"value": ["MASTER", "BACHELOR"], "evidence": "Pursuing a BS or MS in CS."},
    "citizenship": {"value": "NONE_MENTIONED", "evidence": None},
    "clearance": {"value": "NONE_MENTIONED", "evidence": None},
    "work_mode": {"value": "NONE_MENTIONED", "evidence": None},
    "pay": {
        "value": {"min": 30, "max": 38, "period": "HOUR", "currency": "USD"},
        "evidence": "Pay: $30-$38/hr",
    },  # hyphen where the posting has an en dash
    "skills": {"value": ["Python", "C++", "Python"], "evidence": "Experience with Python and C++."},
    "unsure_fields": [],
}


def answer(**changes) -> dict:
    result = json.loads(json.dumps(ANSWER))
    result.update(changes)
    return result


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        """Like messages.create: the reply comes back as JSON text. None means cut off."""
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        text = '{"title": {"value": "Robo' if reply is None else json.dumps(reply)
        return SimpleNamespace(
            stop_reason="max_tokens" if reply is None else "end_turn",
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=400,
                cache_read_input_tokens=7000,
                cache_creation_input_tokens=0,
            ),
            content=[SimpleNamespace(type="text", text=text)],
        )


def fake_teacher(*replies) -> TeacherBackend:
    return TeacherBackend(client=SimpleNamespace(messages=FakeMessages(replies)))


@pytest.fixture(autouse=True)
def logs(tmp_path, monkeypatch):
    """Run logs go to a temp folder, never data/teacher_runs/."""
    monkeypatch.setattr(teacher, "LOGS", tmp_path / "teacher_runs")
    return tmp_path / "teacher_runs"


def read_logs(folder) -> list[dict]:
    return [json.loads(line) for file in folder.glob("*.jsonl") for line in file.open()]


# ---------- render_posting ----------


def test_render_posting_puts_the_board_header_first():
    assert TEXT.splitlines()[:4] == [
        "Robotics Software Intern (Summer 2027)",
        "Organization: acmerobotics",
        "Location: Austin, Texas, United States",
        "",
    ]
    assert TEXT.endswith(POSTING["text"])


def test_render_posting_skips_a_missing_location():
    text = render_posting({**POSTING, "location_raw": None})
    assert "Location:" not in text


# ---------- quote_found ----------


@pytest.mark.parametrize(
    "quote",
    [
        "We're Acme Robotics!",  # straight apostrophe, posting has a curly one
        "pay: $30-$38/HR",  # case and dash differences
        "Python and   C++.",  # extra spaces
        "Pursuing a BS or MS in CS. | Experience with Python",  # list evidence
    ],
)
def test_quote_found_ignores_copying_slips(quote):
    assert quote_found(quote, TEXT)


@pytest.mark.parametrize("quote", [None, "", " | ", "Must be a U.S. citizen.", "BS | PhD"])
def test_quote_found_rejects_missing_or_made_up_quotes(quote):
    assert not quote_found(quote, TEXT)


# ---------- the schema ----------


def test_output_model_limits_unsure_fields_to_the_requested_fields():
    model = output_model(("title", "pay"))
    schema = model.model_json_schema()
    assert list(schema["properties"]) == ["title", "pay", "unsure_fields"]
    assert schema["properties"]["unsure_fields"]["items"]["enum"] == ["title", "pay"]


# ---------- review_reasons ----------


def test_not_stated_values_need_no_evidence():
    reasons = review_reasons(
        {"clearance": "NONE_MENTIONED", "skills": [], "pay": None},
        {"clearance": None, "skills": None, "pay": None},
        [],
        TEXT,
    )
    assert reasons == {"clearance": [], "skills": [], "pay": []}


def test_a_stated_value_without_a_real_quote_is_flagged():
    reasons = review_reasons({"citizenship": "US_CITIZEN"}, {"citizenship": None}, [], TEXT)
    assert reasons["citizenship"] == ["evidence not found in posting"]


@pytest.mark.parametrize("deadline", ["2026-13-01", "20261201", "Dec 1"])
def test_bad_deadline_formats_are_flagged(deadline):
    reasons = review_reasons(
        {"deadline": deadline, "deadline_type": "FIXED"},
        {"deadline": "Applications close December 1, 2026.", "deadline_type": "close"},
        [],
        TEXT,
    )
    assert "deadline isn't a real YYYY-MM-DD date" in reasons["deadline"]


def test_fixed_without_a_date_is_allowed():
    reasons = review_reasons(
        {"deadline": None, "deadline_type": "FIXED"},
        {"deadline": None, "deadline_type": "Applications close"},
        [],
        TEXT,
    )
    assert reasons == {"deadline": [], "deadline_type": []}


def test_a_date_needs_fixed():
    reasons = review_reasons(
        {"deadline": "2026-12-01", "deadline_type": "ROLLING"},
        {"deadline": "Applications close December 1, 2026.", "deadline_type": "Applications"},
        [],
        TEXT,
    )
    assert (
        reasons["deadline"] == reasons["deadline_type"] == ["deadline and deadline_type disagree"]
    )


def test_bad_start_term_and_reversed_pay_are_flagged():
    reasons = review_reasons(
        {"start_term": "summer of 2027", "pay": Pay(min=38, max=30, period="HOUR")},
        {"start_term": "Summer 2027", "pay": "Pay: $30–$38/hr"},
        [],
        TEXT,
    )
    assert reasons["start_term"] == ["start_term isn't 'Season YYYY'"]
    assert reasons["pay"] == ["pay min is bigger than max"]


# ---------- extract / label ----------


def test_a_clean_answer_flags_nothing_and_tidies_lists(logs):
    results = fake_teacher(ANSWER).extract(TEXT, list(ALL_FIELDS))

    assert set(results) == set(ALL_FIELDS)
    assert not [field for field, result in results.items() if result.needs_review]
    assert results["degree_levels"].value == ["BACHELOR", "MASTER"]  # guide order
    assert results["skills"].value == ["Python", "C++"]  # repeat dropped
    assert results["pay"].value == Pay(min=30, max=38, period="HOUR", currency="USD")
    assert all(result.source == "model" for result in results.values())

    (record,) = read_logs(logs)
    assert record["review_reasons"] == {}
    assert record["raw_output"]["skills"]["value"] == ["Python", "C++", "Python"]  # raw, untidied


def test_unsure_flags_only_the_listed_field():
    results = fake_teacher(answer(unsure_fields=["skills"])).extract(TEXT, list(ALL_FIELDS))
    assert [field for field, result in results.items() if result.needs_review] == ["skills"]


def test_requested_fields_come_back_in_contract_order():
    reply = {"pay": ANSWER["pay"], "title": ANSWER["title"], "unsure_fields": []}
    fake = fake_teacher(reply)
    results = fake.extract(TEXT, ["pay", "title"])
    assert list(results) == ["title", "pay"]
    sent = fake.client.messages.calls[0]["output_config"]["format"]
    assert sent == output_format(("title", "pay"))
    assert sent["schema"]["properties"]["unsure_fields"]["items"]["enum"] == ["title", "pay"]


def test_label_logs_the_manifest_hash_and_tokens(logs):
    _results, record = fake_teacher(ANSWER).label(TEXT, [], posting_hash="sha256:abc")
    assert record["posting_hash"] == "sha256:abc"
    assert record["requested_fields"] == list(ALL_FIELDS)  # empty means every field
    assert record["token_counts"]["cache_read_input_tokens"] == 7000
    assert read_logs(logs)[0]["posting_hash"] == "sha256:abc"


def test_without_a_manifest_hash_only_the_input_hash_is_logged():
    _results, record = fake_teacher(ANSWER).label(TEXT, [])
    assert record["posting_hash"] is None
    assert record["input_hash"].startswith("sha256:")


def test_a_cut_off_reply_is_logged_with_its_tokens(logs):
    fake = fake_teacher(None)
    with pytest.raises(ValueError, match="didn't match the schema"):
        fake.extract(TEXT, list(ALL_FIELDS))
    (record,) = read_logs(logs)
    assert record["stop_reason"] == "max_tokens"
    assert record["raw_reply"].startswith('{"title"')
    assert record["token_counts"]["output_tokens"] == 400
    assert fake.token_totals["output_tokens"] == 400  # billed, so it counts toward cost


def test_client_errors_are_logged_and_raised(logs):
    with pytest.raises(RuntimeError):
        fake_teacher(RuntimeError("overloaded")).extract(TEXT, list(ALL_FIELDS))
    assert read_logs(logs)[0]["error"] == "RuntimeError: overloaded"


# ---------- settings and load_backend ----------


def test_missing_settings_raise(monkeypatch):
    monkeypatch.setattr(teacher.settings, "TEACHER_API_KEY", "")
    with pytest.raises(RuntimeError, match="TEACHER_API_KEY"):
        TeacherBackend()


def test_load_backend_returns_the_teacher(monkeypatch):
    monkeypatch.setattr(teacher.settings, "TEACHER_API_KEY", "test-key")
    monkeypatch.setattr(teacher.settings, "TEACHER_BASE_URL", "https://example.test/anthropic")
    backend = load_backend("teacher")
    assert isinstance(backend, TeacherBackend)
    assert backend.name == "teacher"


# ---------- label_teacher ----------


@pytest.fixture
def pool(tmp_path, monkeypatch):
    """Two invented postings in a temp raw store and train pool."""
    raw = tmp_path / "raw"
    raw.mkdir()
    hashes = ["sha256:" + "a" * 64, "sha256:" + "b" * 64]
    for posting_hash in hashes:
        (raw / f"{posting_hash.removeprefix('sha256:')}.json").write_text(
            json.dumps(POSTING), encoding="utf-8"
        )
    manifest = tmp_path / "train_pool.jsonl"
    manifest.write_text("".join(json.dumps({"hash": h}) + "\n" for h in hashes))
    monkeypatch.setattr(label_teacher, "RAW", raw)
    monkeypatch.setattr(label_teacher, "TRAIN_POOL", manifest)
    monkeypatch.setattr(label_teacher, "TEACHER_LABELS", tmp_path / "labels" / "teacher.jsonl")
    return hashes


def labels_file() -> list[dict]:
    return [json.loads(line) for line in label_teacher.TEACHER_LABELS.open()]


def test_label_teacher_writes_gold_shaped_records(pool):
    label_teacher.main([], teacher=fake_teacher(ANSWER, answer(unsure_fields=["pay"])))

    first, second = labels_file()
    assert [first["hash"], second["hash"]] == pool
    assert first["split"] == "train"
    assert list(first["fields"]) == list(ALL_FIELDS)
    assert first["fields"]["pay"] == {"min": 30, "max": 38, "period": "HOUR", "currency": "USD"}
    assert (first["unsure"], first["needs_review"]) == (False, [])
    assert (second["unsure"], second["unsure_fields"], second["needs_review"]) == (
        True,
        ["pay"],
        ["pay"],
    )
    assert "evidence" not in json.dumps(first)  # quotes stay in the gitignored run logs


def test_label_teacher_resumes_and_retries_failures(pool):
    label_teacher.main([], teacher=fake_teacher(RuntimeError("boom"), ANSWER))
    assert [record["hash"] for record in labels_file()] == [pool[1]]

    fake = fake_teacher(ANSWER)
    label_teacher.main([], teacher=fake)
    assert len(fake.client.messages.calls) == 1  # only the failed one was asked again
    assert sorted(record["hash"] for record in labels_file()) == sorted(pool)


def test_label_teacher_redoes_labels_from_an_older_prompt(pool):
    label_teacher.main(["--limit", "1"], teacher=fake_teacher(ANSWER))
    newer = fake_teacher(ANSWER, ANSWER)
    newer.system_prompt_hash = "a-newer-prompt"
    label_teacher.main([], teacher=newer)
    assert len(newer.client.messages.calls) == 2
    assert [record["prompt_hash"] for record in labels_file()][-2:] == ["a-newer-prompt"] * 2


def test_label_teacher_newest_line_wins_after_a_prompt_revert(pool):
    label_teacher.main(["--limit", "1"], teacher=fake_teacher(ANSWER))  # prompt A, first posting
    newer = fake_teacher(ANSWER, ANSWER)
    newer.system_prompt_hash = "prompt-b"
    label_teacher.main([], teacher=newer)  # prompt B, both postings
    reverted = fake_teacher(ANSWER, ANSWER)  # back to prompt A: both newest lines are B
    label_teacher.main([], teacher=reverted)
    assert len(reverted.client.messages.calls) == 2


def test_label_teacher_stops_after_many_failures_in_a_row(pool, monkeypatch):
    monkeypatch.setattr(label_teacher, "MAX_FAILURES_IN_A_ROW", 2)
    fake = fake_teacher(RuntimeError("bad key"), RuntimeError("bad key"))
    label_teacher.main([], teacher=fake)
    assert not label_teacher.TEACHER_LABELS.exists() or labels_file() == []
