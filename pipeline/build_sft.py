"""Step 6.1: turn the teacher's labels into training examples for the student.

Fine-tuning learns from (input, answer) pairs. Here each pair is one posting and the
teacher's labels for it, written as a chat:

    system     the student's instructions (service/backends/student_prompt.md)
    user       the posting, exactly as every backend sees it (render_posting, in <posting> tags)
    assistant  the teacher's 12 field values as one JSON object

During training the model reads the system and user turns and is graded only on how well
it predicts the assistant turn, token by token ("loss masking"). So it learns to write the
teacher's answer, not to repeat the posting.

Why a short student prompt instead of the teacher's 18 KB guide: the teacher needed the
rules spelled out because it never saw examples. The student learns the rules from 2,500
worked examples, so the prompt only has to name the fields and their allowed values.
A short prompt also makes every training step and every CPU inference faster. student.py
must send this same prompt, so its hash is stored with the data.

Why evidence quotes are included (the default): the app shows the quote each value came
from, and student.py can check that a quote really appears in the posting, the same check
that flags made-up answers for review in the teacher. The cost is a longer answer: about
1,300 characters instead of 400, so training takes about 17% longer and CPU inference
writes about three times as many tokens. Bulk extraction runs on the GPU, so only the few
new postings a day pay that on CPU. --no-evidence builds the values-only version.

Validation split: 5% of organizations (not postings) are held out, so postings from one
employer never land on both sides. Otherwise near-identical postings (same company
boilerplate) would make validation loss look better than it is.

Reads the train_pool manifest, so training on a different subset is a one-line change.

Run from the project root:
    uv run python -m pipeline.build_sft
    uv run python -m pipeline.build_sft --no-evidence
Writes data/sft/train.jsonl, data/sft/val.jsonl and data/sft/meta.json (data/ is gitignored).
"""

import argparse
import hashlib
import json
from pathlib import Path

from service.normalize import render_posting
from service.schemas import ALL_FIELDS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"
TRAIN_POOL = PROJECT_ROOT / "data" / "manifests" / "train_pool.jsonl"
TEACHER_LABELS = PROJECT_ROOT / "data" / "labels" / "teacher.jsonl"
TEACHER_RUNS = PROJECT_ROOT / "data" / "teacher_runs"
STUDENT_PROMPT = PROJECT_ROOT / "service" / "backends" / "student_prompt.md"
OUT = PROJECT_ROOT / "data" / "sft"

VAL_SHARE = 0.05

# Added to the student prompt when answers carry evidence, so the prompt describes the
# answer's real shape. student.py must send the exact system prompt saved in meta.json.
EVIDENCE_NOTE = (
    'Write each key as {"value": <the value>, "evidence": <the shortest passage from the '
    "posting that supports it, copied exactly, or null when the value is not stated>}."
)


def newest_by_hash(path: Path) -> dict[str, dict]:
    """The newest line per hash wins (the same rule as label_teacher and gold.jsonl)."""
    records = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[record["hash"]] = record
    return records


def evidence_by_hash() -> dict[str, dict]:
    """The teacher's evidence quotes per posting, from the call logs (newest wins)."""
    evidence = {}
    for log in sorted(TEACHER_RUNS.glob("*.jsonl")):
        with open(log, encoding="utf-8") as file:
            for line in file:
                record = json.loads(line) if line.strip() else {}
                raw = record.get("raw_output")
                if record.get("posting_hash") and isinstance(raw, dict):
                    evidence[record["posting_hash"]] = {
                        field: raw[field].get("evidence")
                        for field in ALL_FIELDS
                        if isinstance(raw.get(field), dict)
                    }
    return evidence


def in_validation(organization: str) -> bool:
    """Same answer every run, and per organization rather than per posting.

    The first 8 hex digits of a hash, read as a fraction of the maximum, are spread evenly
    between 0 and 1, so about VAL_SHARE of organizations fall below the cutoff.
    """
    digest = hashlib.sha256(organization.casefold().encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF < VAL_SHARE


def answer(fields: dict, evidence: dict | None) -> str:
    """The assistant turn: every field, always in ALL_FIELDS order.

    A fixed key order matters: the model learns one layout instead of many, and student.py
    can rely on it.
    """
    if evidence is None:
        target = {field: fields[field] for field in ALL_FIELDS}
    else:
        target = {
            field: {"value": fields[field], "evidence": evidence.get(field)} for field in ALL_FIELDS
        }
    return json.dumps(target, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the student's training data.")
    parser.add_argument("--no-evidence", action="store_true", help="values only, no quotes")
    args = parser.parse_args()

    with_evidence = not args.no_evidence
    system_prompt = STUDENT_PROMPT.read_text(encoding="utf-8").strip()
    if with_evidence:
        system_prompt += "\n\n" + EVIDENCE_NOTE
    labels = newest_by_hash(TEACHER_LABELS)
    evidence = evidence_by_hash() if with_evidence else None

    with open(TRAIN_POOL, encoding="utf-8") as file:
        pool = [json.loads(line) for line in file if line.strip()]

    splits = {"train": [], "val": []}
    skipped = {"no teacher label": 0, "no raw file": 0, "empty text": 0, "no evidence": 0}
    for entry in pool:
        label = labels.get(entry["hash"])
        raw_file = RAW / f"{entry['hash'].removeprefix('sha256:')}.json"
        if label is None:
            skipped["no teacher label"] += 1
            continue
        if not raw_file.exists():
            skipped["no raw file"] += 1
            continue
        posting = json.loads(raw_file.read_text(encoding="utf-8"))
        if not posting.get("text", "").strip():
            skipped["empty text"] += 1
            continue
        quotes = None
        if evidence is not None:
            quotes = evidence.get(entry["hash"])
            if quotes is None:
                skipped["no evidence"] += 1
                continue

        example = {
            "hash": entry["hash"],
            "organization": entry["organization"],
            "messages": [
                {"role": "system", "content": system_prompt},
                # Same wrapper the teacher saw, so the student reads the same input shape
                {"role": "user", "content": f"<posting>\n{render_posting(posting)}\n</posting>"},
                {"role": "assistant", "content": answer(label["fields"], quotes)},
            ],
        }
        splits["val" if in_validation(entry["organization"]) else "train"].append(example)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, examples in splits.items():
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as file:
            for example in examples:
                file.write(json.dumps(example, ensure_ascii=False) + "\n")

    chars = [len(m["content"]) for ex in splits["train"] for m in ex["messages"]]
    longest = max(sum(len(m["content"]) for m in ex["messages"]) for ex in splits["train"])
    meta = {
        "train": len(splits["train"]),
        "val": len(splits["val"]),
        "val_organizations": len({ex["organization"] for ex in splits["val"]}),
        "train_organizations": len({ex["organization"] for ex in splits["train"]}),
        "skipped": skipped,
        "with_evidence": with_evidence,
        "system_prompt": system_prompt,
        "student_prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "teacher_prompt_hashes": sorted(
            {labels[ex["hash"]]["prompt_hash"] for s in splits.values() for ex in s}
        ),
        "longest_example_chars": longest,
        "total_chars": sum(chars),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print(f"Wrote {OUT / 'train.jsonl'} and {OUT / 'val.jsonl'}")


if __name__ == "__main__":
    main()
