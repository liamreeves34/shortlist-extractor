import json
import random
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = PROJECT_ROOT / "data" / "manifests"
COLLECTED = MANIFESTS / "collected.jsonl"

SEED = 42

CALIBRATION_SIZE = 50  # postings but will most likey be close to 50 because whole organizations are needed
TEST_SIZE = 125

# Organizations with more postings than this stay in the train pool, so a single
# company's template can't dominate the small held-out splits.
MAX_HELDOUT_ORG_SIZE = 10

# Different names for the same employer -> one key. Keys and values are normalized
# (lowercase, single spaces). Add to this when you spot a new pair.
ALIASES = {
    "astera labs early career": "astera",
    "astera labs early career - north america 2027": "astera",
    "atoms careers page": "atoms",
    "drw - university jobs": "drw",
    "flow traders spring 2027 co-op opportunities": "flow traders",
    "graphcore early careers": "graphcore",
    "integra fec - internships": "integra fec",
}

SPLITS = ("train_pool", "calibration", "test")


def org_key(organization: str) -> str:
    """The grouping key for an organization: lowercase, whitespace collapsed, aliases applied."""
    key = " ".join(organization.lower().split())
    return ALIASES.get(key, key)


def split(lines: list[dict], seed: int = SEED) -> dict[str, list[dict]]:
    """Assign every manifest line to exactly one split, keeping each organization together."""
    by_org: dict[str, list[dict]] = defaultdict(list)
    for line in lines:
        by_org[org_key(line["organization"])].append(line)

    # Sort before shuffling so the result depends only on the seed and the set of
    # postings, not on the order collect.py happened to write them in.
    orgs = sorted(by_org)
    random.Random(seed).shuffle(orgs)

    result: dict[str, list[dict]] = {name: [] for name in SPLITS}
    for org in orgs:
        postings = by_org[org]
        small = len(postings) <= MAX_HELDOUT_ORG_SIZE
        if small and len(result["calibration"]) + len(postings) <= CALIBRATION_SIZE:
            result["calibration"].extend(postings)
        elif small and len(result["test"]) + len(postings) <= TEST_SIZE:
            result["test"].extend(postings)
        else:
            result["train_pool"].extend(postings)

    # Stable order inside each file, so re-running gives a byte-identical diff.
    for name in SPLITS:
        result[name].sort(key=lambda line: (org_key(line["organization"]), line["hash"]))
    return result


def load(path: Path) -> list[dict]:
    """Manifest lines, with any repeated hash kept once."""
    seen: dict[str, dict] = {}
    with open(path, encoding="utf-8") as file:
        for raw in file:
            if raw.strip():
                line = json.loads(raw)
                seen.setdefault(line["hash"], line)
    return list(seen.values())


def write(splits: dict[str, list[dict]], out_dir: Path, seed: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, lines in splits.items():
        with open(out_dir / f"{name}.jsonl", "w", encoding="utf-8") as file:
            file.writelines(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)

    summary = {
        "seed": seed,
        "source": "collected.jsonl",
        "max_heldout_org_size": MAX_HELDOUT_ORG_SIZE,
        "splits": {
            name: {
                "postings": len(lines),
                "organizations": len({org_key(line["organization"]) for line in lines}),
            }
            for name, lines in splits.items()
        },
    }
    (out_dir / "split.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    lines = load(COLLECTED)
    splits = split(lines, SEED)
    write(splits, MANIFESTS, SEED)

    print(f"seed {SEED}, {len(lines)} postings")
    for name, chosen in splits.items():
        orgs = len({org_key(line["organization"]) for line in chosen})
        print(f"  {name:<12} {len(chosen):>5} postings  {orgs:>4} organizations")


if __name__ == "__main__":
    main()