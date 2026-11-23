"""Step 3.4: a terminal helper for hand-labeling the gold set (test + calibration splits).

Shows one posting at a time, asks for each field following docs/labeling_guide.md, and
appends one JSON line per posting to data/labels/gold.jsonl. Resumable: postings already
in gold.jsonl are skipped, so you can quit at any time and pick up where you stopped.

Run from the project root:
    uv run python -m pipeline.label_gold                 # test split, then calibration
    uv run python -m pipeline.label_gold --split test    # just one split

At any prompt:  ?  show the posting again in a pager    q  save nothing for this posting and quit
Enter accepts the [default] shown in brackets.
"""

import argparse
import json
import pydoc
import re
import textwrap
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"
MANIFESTS = PROJECT_ROOT / "data" / "manifests"
GOLD = PROJECT_ROOT / "data" / "labels" / "gold.jsonl"

GUIDE_VERSION = 2  # bump together with "Version:" in docs/labeling_guide.md

GOLD_SPLITS = ("test", "calibration")

# Allowed values, from docs/labeling_guide.md. The first entry is the default.
DEADLINE_TYPES = ["NONE_MENTIONED", "FIXED", "ROLLING"]
CITIZENSHIP = ["NONE_MENTIONED", "WORK_AUTHORIZED", "NO_SPONSORSHIP", "US_PERSON", "US_CITIZEN"]
CLEARANCE = ["NONE_MENTIONED", "PREFERRED", "ABLE_TO_OBTAIN", "REQUIRED"]
WORK_MODES = ["NONE_MENTIONED", "ONSITE", "HYBRID", "REMOTE"]
DEGREE_LEVELS = ["HIGH_SCHOOL", "ASSOCIATE", "BACHELOR", "MASTER", "PHD"]
DEGREE_CODES = {"h": "HIGH_SCHOOL", "a": "ASSOCIATE", "b": "BACHELOR", "m": "MASTER", "p": "PHD"}
PAY_PERIODS = {"h": "HOUR", "y": "YEAR", "u": "UNKNOWN"}

TERM_RE = re.compile(r"(Spring|Summer|Fall|Winter) \d{4}")
# Board values that are fine to offer as Enter defaults (guide v2)
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")  # "geocomply-2", "loftorbital"
PROGRAM_RE = re.compile(
    r"\b(?:intern(?:ship)?s?|program(?:me)?s?|recruit(?:ing|ment)|careers?|university|campus)\b"
    r"|\b(?:inc|llc|ltd|corp|corporation)\b\.?",
    re.IGNORECASE,
)
USPS = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH"
    "|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|PR"
)
# Already US `City, ST` (one or more). "Toronto, ON" isn't: non-US is City, Country.
LOCATION_RE = re.compile(rf"[^,;]+, (?:{USPS})(?:; [^,;]+, (?:{USPS}))*")


class Quit(Exception):
    """The labeler typed q."""


class Invalid(ValueError):
    """An answer that doesn't follow the guide; the prompt repeats."""


# ---------- parsing answers (pure functions, tested in tests/test_label_gold.py) ----------


def parse_text(answer: str) -> str | None:
    """Free text; '-' means not stated (null)."""
    answer = " ".join(answer.split())
    return None if answer in ("", "-") else answer


def parse_start_term(answer: str) -> str | None:
    answer = " ".join(answer.split())
    if answer in ("", "-"):
        return None
    answer = answer.title()
    if not TERM_RE.fullmatch(answer):
        raise Invalid("write it as Season YYYY, e.g. Summer 2027 (or - for none)")
    return answer


def parse_date(answer: str) -> str | None:
    answer = answer.strip()
    if answer in ("", "-"):
        return None
    try:
        return date.fromisoformat(answer).isoformat()
    except ValueError:
        raise Invalid("write it as YYYY-MM-DD (or - for none)") from None


def parse_choice(answer: str, choices: list[str]) -> str:
    """A number from the menu, or the value itself (case-insensitive)."""
    answer = answer.strip()
    if answer.isdigit() and 1 <= int(answer) <= len(choices):
        return choices[int(answer) - 1]
    for choice in choices:
        if answer.upper() == choice:
            return choice
    raise Invalid(f"pick 1-{len(choices)}")


def parse_degrees(answer: str) -> list[str]:
    """Letters from DEGREE_CODES, e.g. 'bm' or 'b m'; '-' for none. Returned in guide order."""
    letters = answer.replace(" ", "").replace(",", "").lower()
    if letters in ("", "-"):
        return []
    unknown = set(letters) - set(DEGREE_CODES)
    if unknown:
        raise Invalid(f"unknown letter(s) {''.join(sorted(unknown))}; use h a b m p")
    chosen = {DEGREE_CODES[letter] for letter in letters}
    return [level for level in DEGREE_LEVELS if level in chosen]


def parse_skills(answer: str) -> list[str]:
    """Comma-separated; whitespace trimmed, empty items and exact repeats dropped."""
    if answer.strip() in ("", "-"):
        return []
    skills: list[str] = []
    for item in answer.split(","):
        item = " ".join(item.split())
        if item and item not in skills:
            skills.append(item)
    return skills


def _number(text: str) -> float | None:
    text = text.strip().lower().replace(",", "").replace("$", "")
    if text in ("", "-"):
        return None
    multiplier = 1000 if text.endswith("k") else 1
    try:
        value = float(text.removesuffix("k")) * multiplier
    except ValueError:
        raise Invalid(f"{text!r} isn't a number") from None
    return int(value) if value.is_integer() else value


def parse_pay(answer: str) -> dict | None:
    """'min max period [currency]', e.g. '25 32 h', '80k 80k y', '- 40 h', '6000 6000 u CAD'.

    '-' for a missing min or max; Enter or '-' alone for no pay figure (null).
    """
    parts = answer.split()
    if not parts or parts == ["-"]:
        return None
    if len(parts) not in (3, 4):
        raise Invalid("write: min max period [currency], e.g. 25 32 h  (period h/y/u)")
    low, high = _number(parts[0]), _number(parts[1])
    if low is None and high is None:
        raise Invalid("give at least a min or a max (or Enter for no pay)")
    if low is not None and high is not None and low > high:
        raise Invalid("min is bigger than max")
    period = PAY_PERIODS.get(parts[2].lower())
    if period is None:
        raise Invalid("period is h (hour), y (year) or u (unknown)")
    currency = parts[3].upper() if len(parts) == 4 else "USD"
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise Invalid("currency is a 3-letter code like USD or CAD")
    return {"min": low, "max": high, "period": period, "currency": currency}


def check_consistency(fields: dict) -> list[str]:
    """Cross-field rules from the guide. Returns problems; empty means fine."""
    # FIXED with no date is allowed: a deadline with no year (guide v2, then set unsure).
    problems = []
    if fields["deadline_type"] != "FIXED" and fields["deadline"] is not None:
        problems.append("a deadline date needs deadline_type FIXED")
    if not fields["title"] or not fields["organization"]:
        problems.append("title and organization are always present")
    return problems


def must_be_unsure(fields: dict) -> list[str]:
    """Cases where the guide requires `unsure` (guide v2). Empty means none."""
    reasons = []
    if fields["deadline_type"] == "FIXED" and fields["deadline"] is None:
        reasons.append("a FIXED deadline with no year (deadline left null)")
    return reasons


# ---------- files ----------


def raw_path(content_hash: str) -> Path:
    return RAW / f"{content_hash.removeprefix('sha256:')}.json"


def load_queue(splits: tuple[str, ...]) -> list[tuple[str, str]]:
    """(split, hash) for every posting to label, in manifest order."""
    queue = []
    for split in splits:
        with open(MANIFESTS / f"{split}.jsonl", encoding="utf-8") as file:
            queue.extend((split, json.loads(line)["hash"]) for line in file if line.strip())
    return queue


def labeled_hashes(path: Path | None = None) -> set[str]:
    path = path or GOLD  # looked up at call time, not when the function is defined
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as file:
        return {json.loads(line)["hash"] for line in file if line.strip()}


def append_label(record: dict, path: Path | None = None) -> None:
    path = path or GOLD
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------- the interactive part ----------


def show(posting: dict) -> str:
    header = (
        f"{posting['title']}\n{posting['organization']}  |  {posting.get('location_raw') or '-'}\n"
        f"{posting['url']}\n" + "-" * 80 + "\n"
    )
    body = "\n".join(
        textwrap.fill(paragraph, 100) if paragraph.strip() else ""
        for paragraph in posting["text"].splitlines()
    )
    return header + body


def ask(prompt: str, parse, posting: dict, default: str = ""):
    """Ask until the answer parses. '?' re-shows the posting, 'q' quits."""
    shown_default = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{shown_default}: ")
        if answer.strip() == "?":
            pydoc.pager(show(posting))
            continue
        if answer.strip().lower() == "q":
            raise Quit
        try:
            return parse(answer if answer.strip() else default)
        except Invalid as problem:
            print(f"  ! {problem}")


def menu(choices: list[str]) -> str:
    return "  ".join(f"{i}={choice}" for i, choice in enumerate(choices, 1))


def label_one(posting: dict) -> dict:
    """Ask every field for one posting and return the fields dict."""
    fields: dict = {}
    print("  title: drop requisition codes (R-1234) and a trailing location")
    fields["title"] = ask("title", parse_text, posting, posting["title"])
    # The board's organization is often a slug or a program name, and its location is often
    # not in City, ST form, so they're only offered as the default when they're already right.
    organization = posting["organization"]
    print(
        f"  board organization: {organization}  (use the employer's own name;"
        " if the body never names it, answer yes to unsure)"
    )
    org_default = (
        "" if SLUG_RE.fullmatch(organization) or PROGRAM_RE.search(organization) else organization
    )
    fields["organization"] = ask("organization", parse_text, posting, org_default)
    location = posting.get("location_raw") or ""
    print(
        f"  board location: {location or '-'}  (rewrite as City, ST; header first, then the body's)"
    )
    fields["location"] = ask(
        "location (City, ST; several joined by '; '; - for none)",
        parse_text,
        posting,
        location if LOCATION_RE.fullmatch(location) else "",
    )
    fields["start_term"] = ask("start_term (Summer 2027; - for none)", parse_start_term, posting)

    print(f"  deadline_type: {menu(DEADLINE_TYPES)}")
    fields["deadline_type"] = ask(
        "deadline_type", lambda a: parse_choice(a, DEADLINE_TYPES), posting, "1"
    )
    if fields["deadline_type"] == "FIXED":
        fields["deadline"] = ask("deadline (YYYY-MM-DD)", parse_date, posting)
    else:
        fields["deadline"] = None

    fields["degree_levels"] = ask(
        "degree_levels (letters: h a b m p; - for none)", parse_degrees, posting
    )

    print(f"  citizenship: {menu(CITIZENSHIP)}")
    fields["citizenship"] = ask("citizenship", lambda a: parse_choice(a, CITIZENSHIP), posting, "1")
    print(f"  clearance: {menu(CLEARANCE)}")
    fields["clearance"] = ask("clearance", lambda a: parse_choice(a, CLEARANCE), posting, "1")
    print(f"  work_mode: {menu(WORK_MODES)}")
    fields["work_mode"] = ask("work_mode", lambda a: parse_choice(a, WORK_MODES), posting, "1")

    fields["pay"] = ask("pay (min max h/y/u [CUR]; Enter for none)", parse_pay, posting)
    fields["skills"] = ask("skills (comma-separated; - for none)", parse_skills, posting)
    return fields


def yes_no(prompt: str, default: bool = False) -> bool:
    answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if answer == "q":
        raise Quit
    return default if not answer else answer.startswith("y")


def run(splits: tuple[str, ...]) -> None:
    queue = load_queue(splits)
    done = labeled_hashes()
    todo = [(split, h) for split, h in queue if h not in done]
    print(
        f"{len(queue) - len(todo)}/{len(queue)} labeled; {len(todo)} to go. Guide v{GUIDE_VERSION}."
    )

    for position, (split, content_hash) in enumerate(todo, len(queue) - len(todo) + 1):
        posting = json.loads(raw_path(content_hash).read_text(encoding="utf-8"))
        print("\n" + "=" * 80)
        print(f"[{position}/{len(queue)}]  {split}  {content_hash[:19]}…")
        print("=" * 80)
        print(show(posting))
        print("=" * 80)
        try:
            while True:
                fields = label_one(posting)
                for problem in check_consistency(fields):
                    print(f"  ! {problem}")
                print(json.dumps(fields, indent=2, ensure_ascii=False))
                if check_consistency(fields):
                    print("  Fix the problems above: relabeling this posting.")
                    continue
                must = must_be_unsure(fields)
                for reason in must:
                    print(f"  ! the guide says unsure: {reason}")
                unsure = yes_no("unsure about any field?", default=bool(must))
                if yes_no("save?", default=True):
                    break
                print("  Relabeling this posting.")
        except Quit:
            print("\nQuit. Nothing saved for this posting; everything before it is saved.")
            return

        append_label(
            {
                "hash": content_hash,
                "split": split,
                "labeled_at": date.today().isoformat(),
                "guide_version": GUIDE_VERSION,
                "unsure": unsure,
                "fields": fields,
            }
        )
        print(f"Saved. {position}/{len(queue)} done.")

    print("\nAll gold postings are labeled.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=GOLD_SPLITS, help="label only this split")
    args = parser.parse_args()
    run((args.split,) if args.split else GOLD_SPLITS)


if __name__ == "__main__":
    main()
