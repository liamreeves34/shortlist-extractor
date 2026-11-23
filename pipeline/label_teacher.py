"""Step 5.4: run the teacher over the training pool and save its labels.

For each posting in data/manifests/train_pool.jsonl, asks the teacher backend for all 12
fields and appends one JSON line to data/labels/teacher.jsonl. Stage 6 trains the student
on this file.

Resumable: postings already labeled with the current teacher prompt are skipped, so you
can stop at any time (Ctrl+C) and run it again to continue. A posting that fails isn't
written, so the next run tries it again. If the prompt changes, older labels count as
stale and are redone; the newest line for a hash wins (the same rule as gold.jsonl).
Every call, including failures, is also logged by the teacher backend in
data/teacher_runs/.

Run from the project root:
    uv run python -m pipeline.label_teacher              # the whole pool
    uv run python -m pipeline.label_teacher --limit 5    # just the next 5, to test
"""

import argparse
import json
from datetime import date
from pathlib import Path

from service.backends.teacher import TeacherBackend, cost
from service.normalize import render_posting
from service.schemas import ALL_FIELDS, FieldResult, Pay

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"
TRAIN_POOL = PROJECT_ROOT / "data" / "manifests" / "train_pool.jsonl"
TEACHER_LABELS = PROJECT_ROOT / "data" / "labels" / "teacher.jsonl"

# Several failures in a row usually means something global is wrong (bad key, out of
# quota, provider down), not a bad posting. Stop instead of burning through the pool.
MAX_FAILURES_IN_A_ROW = 10


def load_pool_hashes(path: Path | None = None) -> list[str]:
    """Every posting hash in the training pool, in manifest order."""
    path = path or TRAIN_POOL  # looked up at call time, so tests can point it elsewhere
    with open(path, encoding="utf-8") as file:
        return [json.loads(line)["hash"] for line in file if line.strip()]


def load_done_hashes(prompt_hash: str, path: Path | None = None) -> tuple[set[str], set[str]]:
    """(hashes whose newest label uses this prompt, hashes whose newest label doesn't).

    Newest line wins, the same rule Stage 6 must use when it reads teacher.jsonl.
    """
    path = path or TEACHER_LABELS
    newest: dict[str, str] = {}  # hash -> prompt_hash of its last line
    if path.exists():
        with open(path, encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    record = json.loads(line)
                    newest[record["hash"]] = record["prompt_hash"]
    current = {h for h, prompt in newest.items() if prompt == prompt_hash}
    return current, set(newest) - current


def load_posting_text(posting_hash: str, raw_dir: Path | None = None) -> str:
    """The posting as the teacher sees it: board header plus body (see render_posting)."""
    raw_file = (raw_dir or RAW) / f"{posting_hash.removeprefix('sha256:')}.json"
    return render_posting(json.loads(raw_file.read_text(encoding="utf-8")))


def _plain(value: object) -> object:
    """Values in the same plain JSON form as gold labels (Pay model -> dict)."""
    return value.model_dump() if isinstance(value, Pay) else value


def build_record(posting_hash: str, results: dict[str, FieldResult], run: dict) -> dict:
    """One line of teacher.jsonl, in the same shape as gold.jsonl plus the review flags.

    Evidence quotes are left out on purpose: they're employer text, and data/labels/ is
    committed. They stay in the gitignored run logs.
    """
    unsure_fields = run["raw_output"]["unsure_fields"]
    return {
        "hash": posting_hash,
        "split": "train",
        "labeled_at": date.today().isoformat(),
        "model_id": run["model_id"],
        "model_version": run["model_version"],
        "prompt_hash": run["prompt_hash"],
        "unsure": bool(unsure_fields),  # posting-level, like gold.jsonl
        "unsure_fields": unsure_fields,
        "needs_review": [field for field in ALL_FIELDS if results[field].needs_review],
        "fields": {field: _plain(results[field].value) for field in ALL_FIELDS},
    }


def main(argv: list[str] | None = None, teacher: TeacherBackend | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="label at most this many postings, then stop")
    args = parser.parse_args(argv)

    teacher = teacher or TeacherBackend()
    pool = load_pool_hashes()
    done, stale = load_done_hashes(teacher.system_prompt_hash)

    # The postings still to label, in manifest order
    todo = [posting_hash for posting_hash in pool if posting_hash not in done]
    if args.limit is not None:
        todo = todo[: args.limit]

    print(
        f"Training pool: {len(pool)}. Labeled with this prompt: {len(done)}"
        f" (plus {len(stale)} stale, from an older prompt). This run: {len(todo)}."
    )
    if not todo:
        return

    TEACHER_LABELS.parent.mkdir(parents=True, exist_ok=True)
    labeled = 0
    failed = 0
    failures_in_a_row = 0
    flagged = 0

    try:
        with open(TEACHER_LABELS, "a", encoding="utf-8") as out:
            for number, posting_hash in enumerate(todo, start=1):
                text = load_posting_text(posting_hash)
                try:
                    results, run = teacher.label(text, list(ALL_FIELDS), posting_hash=posting_hash)
                except Exception as error:  # noqa: BLE001 -- logged by the backend; keep going
                    failed += 1
                    failures_in_a_row += 1
                    print(f"[{number}/{len(todo)}] FAILED {posting_hash}: {error}")
                    if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                        print(
                            f"Stopping: {failures_in_a_row} failures in a row. Check the run log."
                        )
                        break
                    continue

                failures_in_a_row = 0
                record = build_record(posting_hash, results, run)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()  # written now, so stopping mid-run loses at most the current posting
                labeled += 1
                flagged += bool(record["needs_review"])
                print(
                    f"[{number}/{len(todo)}] labeled {posting_hash[:19]}…"
                    f"  review: {', '.join(record['needs_review']) or '-'}"
                )
    except KeyboardInterrupt:
        print("\nStopped. Everything labeled so far is saved; run again to continue.")

    print(
        f"\nDone. Labeled {labeled}, failed {failed}."
        f" {flagged} of {labeled} have at least one field to review."
        f" Cost this run, failed calls included: ${cost(teacher.token_totals):.2f}."
        f" Labeled with this prompt: {len(done) + labeled} of {len(pool)}."
    )
    if failed:
        print("Run the command again to retry the failures.")


if __name__ == "__main__":
    main()
