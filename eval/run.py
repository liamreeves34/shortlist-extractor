"""Step 4.4: score a backend on a split, print the table, and record it in eval/results.md.

Run from the project root:
    uv run python -m eval.run --backend rules --split test
"""

import argparse
from datetime import date
from pathlib import Path

from eval.harness import MANIFESTS, evaluate
from service.backends import load_backend

RESULTS = Path(__file__).resolve().parent / "results.md"


def format_table(result: dict) -> str:
    lines = [
        "| Field | Metric | Score | 95% interval |",
        "| --- | --- | --- | --- |",
    ]
    for field, metrics in result["fields"].items():
        for name, (point, low, high) in metrics.items():
            lines.append(f"| {field} | {name} | {point:.3f} | [{low:.3f}, {high:.3f}] |")
    return "\n".join(lines)


def format_section(result: dict, split: str, n_boot: int) -> str:
    header = (
        f"## {result['backend']} ({result['model_version']}) on {split}, "
        f"{date.today().isoformat()}\n\n"
        f"{result['postings']} labeled postings"
        f" ({result['unlabeled']} in the split not labeled yet). "
        f"Intervals: {n_boot} bootstrap resamples of postings.\n"
    )
    return f"{header}\n{format_table(result)}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a backend against the gold labels.")
    parser.add_argument("--backend", required=True, help="stub, rules, teacher, student")
    parser.add_argument("--split", default="test", choices=["test", "calibration"])
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--no-save", action="store_true", help="print only; don't touch results.md")
    args = parser.parse_args()

    backend = load_backend(args.backend)
    result = evaluate(backend, MANIFESTS / f"{args.split}.jsonl", n_boot=args.n_boot)

    if result["postings"] == 0:
        print(f"No gold labels for the {args.split} split yet. Label some with:")
        print("  uv run python -m pipeline.label_gold")
        return

    section = format_section(result, args.split, args.n_boot)
    print(section)
    if not args.no_save:
        new_file = not RESULTS.exists()
        with open(RESULTS, "a", encoding="utf-8") as file:
            if new_file:
                file.write("# Results\n\nOne section per run of `eval.run`; newest last.\n\n")
            file.write(section + "\n")
        print(f"Added to {RESULTS}")


if __name__ == "__main__":
    main()
