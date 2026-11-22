"""Step 4.2 and 4.3: one metric per field type, plus bootstrap intervals.

Every metric takes `pairs`: a list of (gold, predicted) values, one pair per posting,
and returns a float between 0 and 1. That shared shape is what lets `bootstrap` wrap
any of them.

| Field type | Fields                                          | Metrics                       |
| ---------- | ----------------------------------------------- | ----------------------------- |
| category   | citizenship, clearance, work_mode, deadline_type | accuracy, macro-F1            |
| date       | deadline                                        | exact match (null == null)    |
| set        | degree_levels, skills                           | set precision, recall, F1     |
| number     | pay                                             | min, max, period exact        |
| short text | title, organization, location, start_term       | exact after lowercase + trim  |
"""

import random
from collections.abc import Callable

Pairs = list[tuple[object, object]]
Metric = Callable[[Pairs], float]


# ---------- category ----------


def accuracy(pairs: Pairs) -> float:
    """Share of postings where the prediction equals the gold label."""
    if not pairs:
        return 0.0
    return sum(gold == pred for gold, pred in pairs) / len(pairs)


def macro_f1(pairs: Pairs) -> float:
    """F1 for each class, averaged with equal weight per class.

    Accuracy is dominated by the common class (most postings are NONE_MENTIONED);
    macro-F1 shows whether the rare classes (US_CITIZEN, REQUIRED, ...) are found too.
    Classes are every label that appears in gold or predictions.
    """
    classes = {gold for gold, _ in pairs} | {pred for _, pred in pairs}
    if not classes:
        return 0.0
    scores = []
    for label in classes:
        tp = sum(gold == label and pred == label for gold, pred in pairs)
        fp = sum(gold != label and pred == label for gold, pred in pairs)
        fn = sum(gold == label and pred != label for gold, pred in pairs)
        scores.append(_f1(tp, fp, fn))
    return sum(scores) / len(scores)


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0:
        return 0.0
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


# ---------- date ----------


def exact_match(pairs: Pairs) -> float:
    """Exact equality, so a correct null (no deadline, predicted none) counts as correct."""
    return accuracy(pairs)


# ---------- set ----------


def _set_counts(pairs: Pairs) -> tuple[int, int, int]:
    """True positives, false positives, false negatives, summed over all postings."""
    tp = fp = fn = 0
    for gold, pred in pairs:
        gold_set = {_normalize(item) for item in gold or []}
        pred_set = {_normalize(item) for item in pred or []}
        tp += len(gold_set & pred_set)
        fp += len(pred_set - gold_set)
        fn += len(gold_set - pred_set)
    return tp, fp, fn


def set_precision(pairs: Pairs) -> float:
    """Of everything predicted, the share that's in the gold set. Empty everywhere -> 1.0."""
    tp, fp, _ = _set_counts(pairs)
    return tp / (tp + fp) if tp + fp else 1.0


def set_recall(pairs: Pairs) -> float:
    """Of everything in the gold sets, the share that was predicted. Empty everywhere -> 1.0."""
    tp, _, fn = _set_counts(pairs)
    return tp / (tp + fn) if tp + fn else 1.0


def set_f1(pairs: Pairs) -> float:
    tp, fp, fn = _set_counts(pairs)
    if tp + fp + fn == 0:
        return 1.0  # nothing expected and nothing predicted: perfect
    return _f1(tp, fp, fn)


# ---------- number (pay) ----------


def _pay_part(pay: object, part: str) -> object:
    """One part of a pay value (dict or None); numbers rounded so 32 == 32.0 == 32.001."""
    if not pay:
        return None
    value = pay.get(part) if isinstance(pay, dict) else getattr(pay, part, None)
    return round(float(value), 2) if isinstance(value, int | float) else value


def pay_min(pairs: Pairs) -> float:
    return accuracy([(_pay_part(g, "min"), _pay_part(p, "min")) for g, p in pairs])


def pay_max(pairs: Pairs) -> float:
    return accuracy([(_pay_part(g, "max"), _pay_part(p, "max")) for g, p in pairs])


def pay_period(pairs: Pairs) -> float:
    return accuracy([(_pay_part(g, "period"), _pay_part(p, "period")) for g, p in pairs])


# ---------- short text ----------


def _normalize(value: object) -> object:
    """Lowercase and collapse whitespace; anything that isn't a string is left alone."""
    return " ".join(value.lower().split()) if isinstance(value, str) else value


def text_match(pairs: Pairs) -> float:
    return accuracy([(_normalize(g), _normalize(p)) for g, p in pairs])


# ---------- which metrics each field gets ----------

CATEGORY = {"accuracy": accuracy, "macro_f1": macro_f1}
SET = {"precision": set_precision, "recall": set_recall, "f1": set_f1}

FIELD_METRICS: dict[str, dict[str, Metric]] = {
    "title": {"exact": text_match},
    "organization": {"exact": text_match},
    "location": {"exact": text_match},
    "start_term": {"exact": text_match},
    "deadline": {"exact": exact_match},
    "deadline_type": CATEGORY,
    "degree_levels": SET,
    "citizenship": CATEGORY,
    "clearance": CATEGORY,
    "work_mode": CATEGORY,
    "pay": {"min": pay_min, "max": pay_max, "period": pay_period},
    "skills": SET,
}


# ---------- 4.3 bootstrap ----------


def bootstrap(pairs: Pairs, metric: Metric, n: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% interval for metric(pairs): resample postings with replacement n times,
    recompute the metric each time, and take the 2.5th and 97.5th percentiles.

    The interval says: had we drawn a different test set of this size, the score would
    plausibly land in this range. With ~125 postings, expect it to be wide.

    The seed is fixed, so the interval is reproducible. Every field's pairs have one entry
    per posting in the same order, so with the same seed each field is resampled with the
    same postings, as they should be: a posting's fields aren't independent.
    """
    if not pairs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    scores = sorted(metric(rng.choices(pairs, k=len(pairs))) for _ in range(n))
    return scores[int(0.025 * n)], scores[int(0.975 * n) - 1]
