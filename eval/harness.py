"""Step 4.4: score any backend against the gold labels of one split.

`evaluate(backend, manifest)` loads each labeled posting's raw text and gold fields,
calls `backend.extract(text, ALL_FIELDS)`, and scores every field with eval.metrics.
It only uses the Backend protocol (name, model_version, extract), so the same code
scores rules, teacher, and student.
"""

import json
from pathlib import Path

from eval.metrics import FIELD_METRICS, bootstrap
from service.backends.base import Backend
from service.schemas import ALL_FIELDS, Pay

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"
MANIFESTS = PROJECT_ROOT / "data" / "manifests"
GOLD = PROJECT_ROOT / "data" / "labels" / "gold.jsonl"


def manifest_hashes(manifest: Path) -> list[str]:
    with open(manifest, encoding="utf-8") as file:
        return [json.loads(line)["hash"] for line in file if line.strip()]


def load_gold(path: Path) -> dict[str, dict]:
    """hash -> gold fields. If a posting was labeled twice, the later line wins."""
    if not path.exists():
        return {}
    gold = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                gold[record["hash"]] = record["fields"]
    return gold


def _plain(value: object) -> object:
    """Predictions in the same plain form as gold labels (Pay model -> dict)."""
    return value.model_dump() if isinstance(value, Pay) else value


def evaluate(
    backend: Backend,
    manifest: Path,
    *,
    gold_path: Path = GOLD,
    raw_dir: Path = RAW,
    n_boot: int = 1000,
    seed: int = 0,
) -> dict:
    """Scores for every field on the labeled postings in `manifest`.

    Returns {"postings": n, "unlabeled": m, "fields": {field: {metric: (score, low, high)}}}.
    Postings in the manifest without a gold label yet are skipped and counted.
    """
    gold = load_gold(gold_path)
    hashes = manifest_hashes(manifest)
    labeled = [h for h in hashes if h in gold]

    pairs: dict[str, list] = {field: [] for field in ALL_FIELDS}
    for content_hash in labeled:
        raw_file = raw_dir / f"{content_hash.removeprefix('sha256:')}.json"
        text = json.loads(raw_file.read_text(encoding="utf-8"))["text"]
        predicted = backend.extract(text, list(ALL_FIELDS))
        for field in ALL_FIELDS:
            pairs[field].append((gold[content_hash].get(field), _plain(predicted[field].value)))

    scores = {}
    for field in ALL_FIELDS:
        scores[field] = {}
        for name, metric in FIELD_METRICS[field].items():
            point = metric(pairs[field])
            low, high = bootstrap(pairs[field], metric, n=n_boot, seed=seed)
            scores[field][name] = (point, low, high)

    return {
        "backend": backend.name,
        "model_version": backend.model_version,
        "postings": len(labeled),
        "unlabeled": len(hashes) - len(labeled),
        "fields": scores,
    }
