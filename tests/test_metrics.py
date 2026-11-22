"""Steps 4.2-4.4: eval/metrics.py and eval/harness.py on tiny hand-made cases."""

import json

import pytest

from eval import metrics as m
from eval.harness import evaluate
from service.schemas import FieldResult

# ---------- category ----------


def test_accuracy_two_right_one_wrong():
    assert m.accuracy([("A", "A"), ("B", "B"), ("A", "B")]) == pytest.approx(2 / 3)


def test_macro_f1_by_hand():
    pairs = [("A", "A"), ("A", "A"), ("B", "A")]
    # A: tp 2, fp 1, fn 0 -> P 2/3, R 1 -> F1 0.8.  B: tp 0 -> F1 0.  Mean 0.4.
    assert m.macro_f1(pairs) == pytest.approx(0.4)


def test_macro_f1_punishes_always_guessing_the_common_class():
    pairs = [("NONE", "NONE")] * 9 + [("US_CITIZEN", "NONE")]
    assert m.accuracy(pairs) == pytest.approx(0.9)
    assert m.macro_f1(pairs) < 0.5


def test_empty_inputs_score_zero():
    assert m.accuracy([]) == 0.0
    assert m.macro_f1([]) == 0.0


# ---------- date ----------


def test_correct_null_counts_as_correct():
    pairs = [(None, None), ("2026-12-01", "2026-12-01"), ("2026-12-01", None)]
    assert m.exact_match(pairs) == pytest.approx(2 / 3)


# ---------- set ----------


def test_set_metrics_by_hand():
    pairs = [(["Python", "SQL"], ["python", "Java"]), (["Go"], ["Go"])]
    # tp: python, go = 2;  fp: java = 1;  fn: sql = 1
    assert m.set_precision(pairs) == pytest.approx(2 / 3)
    assert m.set_recall(pairs) == pytest.approx(2 / 3)
    assert m.set_f1(pairs) == pytest.approx(2 / 3)


def test_empty_sets_everywhere_is_perfect():
    assert m.set_f1([([], []), ([], [])]) == 1.0
    assert m.set_precision([([], [])]) == 1.0


def test_missing_set_counts_as_empty():
    assert m.set_recall([(["Python"], None)]) == 0.0


# ---------- pay ----------


def test_pay_parts():
    gold = {"min": 25, "max": 32, "period": "HOUR", "currency": "USD"}
    pairs = [
        (gold, {"min": 25.0, "max": 32.0, "period": "HOUR", "currency": "USD"}),  # all right
        (gold, {"min": 25, "max": 30, "period": "YEAR", "currency": "USD"}),  # max, period wrong
        (None, None),  # correct null
    ]
    assert m.pay_min(pairs) == pytest.approx(1.0)
    assert m.pay_max(pairs) == pytest.approx(2 / 3)
    assert m.pay_period(pairs) == pytest.approx(2 / 3)


def test_pay_predicted_but_gold_is_null():
    pairs = [(None, {"min": 25, "max": 32, "period": "HOUR", "currency": "USD"})]
    assert m.pay_min(pairs) == 0.0


# ---------- text ----------


def test_text_match_ignores_case_and_spacing():
    pairs = [("Austin, TX", " austin,  tx "), ("Acme", "Acme Inc"), (None, None)]
    assert m.text_match(pairs) == pytest.approx(2 / 3)


def test_every_field_has_metrics():
    from service.schemas import ALL_FIELDS

    assert set(m.FIELD_METRICS) == set(ALL_FIELDS)


# ---------- bootstrap ----------


def test_bootstrap_brackets_the_score():
    pairs = [("A", "A")] * 80 + [("A", "B")] * 20
    low, high = m.bootstrap(pairs, m.accuracy, n=500, seed=1)
    assert low < 0.8 < high
    assert 0.6 < low and high < 0.95


def test_bootstrap_is_reproducible():
    pairs = [("A", "A"), ("A", "B"), ("B", "B")] * 10
    assert m.bootstrap(pairs, m.accuracy, seed=3) == m.bootstrap(pairs, m.accuracy, seed=3)


def test_bootstrap_of_a_perfect_score_is_a_point():
    assert m.bootstrap([("A", "A")] * 10, m.accuracy, n=200) == (1.0, 1.0)


def test_more_postings_give_a_narrower_interval():
    small = [("A", "A")] * 8 + [("A", "B")] * 2
    large = small * 10
    low_s, high_s = m.bootstrap(small, m.accuracy, n=500)
    low_l, high_l = m.bootstrap(large, m.accuracy, n=500)
    assert high_l - low_l < high_s - low_s


# ---------- harness ----------


class EchoBackend:
    """Predicts 'US_CITIZEN' for citizenship whenever the text says 'citizen', else defaults."""

    name = "echo"
    model_version = "test"

    def extract(self, text, fields):
        value = "US_CITIZEN" if "citizen" in text else "NONE_MENTIONED"
        return {
            f: FieldResult(
                value=value if f == "citizenship" else None,
                confidence=0.5,
                needs_review=False,
                source="rules",
            )
            for f in fields
        }


def test_evaluate_scores_only_labeled_postings(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    texts = {"sha256:a": "Must be a citizen.", "sha256:b": "Anyone.", "sha256:c": "Unlabeled."}
    for h, text in texts.items():
        (raw / f"{h.removeprefix('sha256:')}.json").write_text(json.dumps({"text": text}))
    manifest = tmp_path / "test.jsonl"
    manifest.write_text("".join(json.dumps({"hash": h}) + "\n" for h in texts))
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps({"hash": "sha256:a", "fields": {"citizenship": "US_CITIZEN"}})
        + "\n"
        + json.dumps({"hash": "sha256:b", "fields": {"citizenship": "WORK_AUTHORIZED"}})
        + "\n"
    )

    result = evaluate(EchoBackend(), manifest, gold_path=gold, raw_dir=raw, n_boot=50)

    assert result["postings"] == 2
    assert result["unlabeled"] == 1
    assert result["backend"] == "echo"
    score, low, high = result["fields"]["citizenship"]["accuracy"]
    assert score == pytest.approx(0.5)
    assert 0.0 <= low <= score <= high <= 1.0


def test_evaluate_with_no_labels(tmp_path):
    manifest = tmp_path / "test.jsonl"
    manifest.write_text(json.dumps({"hash": "sha256:a"}) + "\n")
    result = evaluate(
        EchoBackend(), manifest, gold_path=tmp_path / "missing.jsonl", raw_dir=tmp_path
    )
    assert result["postings"] == 0
    assert result["unlabeled"] == 1
