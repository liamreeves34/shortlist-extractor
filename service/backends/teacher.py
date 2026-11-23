"""Steps 5.1-5.3: the teacher backend, a hosted Claude model with structured outputs.

For each requested field the model returns a `value` and a verbatim `evidence` quote, plus
one `unsure_fields` list for the whole posting. The code then checks the answer (is each
quote really in the posting? is the deadline a real date?) and sets `needs_review` per
field from those checks. Every call, including failures, is logged to data/teacher_runs/.

The input is the posting as `service.normalize.render_posting` writes it: the job board's
title, organization and location as a header, then the body. Training, eval and serving
must all use that same shape.
"""

import hashlib
import json
import re
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from anthropic import AnthropicFoundry, transform_schema
from pydantic import BaseModel, ValidationError, create_model

from service.normalize import content_hash, render_posting
from service.schemas import ALL_FIELDS, FieldResult, Pay
from service.settings import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEACHER_GUIDE = PROJECT_ROOT / "service" / "backends" / "teacher_prompt.md"
LOGS = PROJECT_ROOT / "data" / "teacher_runs"

DEGREE_LEVELS = ["HIGH_SCHOOL", "ASSOCIATE", "BACHELOR", "MASTER", "PHD"]

FIELD_TYPES = {
    # Text fields. Their formatting rules (City, ST; "Summer 2027") go in the prompt, not the type.
    "title": str,  # the guide says it's always present
    "organization": str,  # the guide says it's always present
    "location": str | None,
    "start_term": str | None,  # "Season YYYY", checked in review_reasons
    "deadline": str | None,  # "YYYY-MM-DD", checked in review_reasons
    # Category fields: NONE_MENTIONED is one of the allowed values
    "deadline_type": Literal["FIXED", "ROLLING", "NONE_MENTIONED"],
    "citizenship": Literal[
        "US_CITIZEN", "US_PERSON", "NO_SPONSORSHIP", "WORK_AUTHORIZED", "NONE_MENTIONED"
    ],
    "clearance": Literal["REQUIRED", "ABLE_TO_OBTAIN", "PREFERRED", "NONE_MENTIONED"],
    "work_mode": Literal["ONSITE", "HYBRID", "REMOTE", "NONE_MENTIONED"],
    # Set fields: empty list means not stated
    "degree_levels": list[Literal["HIGH_SCHOOL", "ASSOCIATE", "BACHELOR", "MASTER", "PHD"]],
    "skills": list[str],
    # Object field
    "pay": Pay | None,
}

TERM_RE = re.compile(r"(Spring|Summer|Fall|Winter) \d{4}")  # same check as label_gold.py
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")  # fromisoformat alone also accepts 20261205

# Characters the model tends to "fix" when it copies a quote. Undo them on both sides
# before checking, so a straightened apostrophe doesn't count as a made-up quote.
_LOOKALIKES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
        "…": "...",
    }
)


# ---------- the response schema ----------


def _slot(field: str) -> type[BaseModel]:
    """writes:
    class Slot_pay(BaseModel):
        value: Pay | None
        evidence: str | None
    """
    return create_model(
        f"Slot_{field}",
        value=(FIELD_TYPES[field], ...),  # ... means required, no default
        evidence=(str | None, ...),
    )


@lru_cache
def output_model(fields: tuple[str, ...]) -> type[BaseModel]:
    """
    output_model(("title", "pay")) is the same as writing by hand:
        class TeacherLabel(BaseModel):
            title: Slot_title
            pay: Slot_pay
            unsure_fields: list[Literal["title", "pay"]]

    `unsure_fields` comes last on purpose: the model fills in every field first, then
    says which ones were judgment calls. Pass the fields in ALL_FIELDS order, so
    ("pay", "title") and ("title", "pay") share one cache entry.
    """
    slots = {field: (_slot(field), ...) for field in fields}
    return create_model(
        "TeacherLabel",
        **slots,
        unsure_fields=(list[Literal[fields]], ...),  # Literal[("a", "b")] == Literal["a", "b"]
    )


@lru_cache
def output_format(fields: tuple[str, ...]) -> dict:
    """output_model(fields) as the API's json_schema format, the way messages.parse() builds it."""
    schema = transform_schema(output_model(fields).model_json_schema())
    return {"type": "json_schema", "schema": schema}


# ---------- checking the answer ----------


def is_stated(value: object) -> bool:
    """False for the guide's "not stated" values: null, [] and NONE_MENTIONED."""
    return value is not None and value != [] and value != "NONE_MENTIONED"


def _squash(text: str) -> str:
    return " ".join(text.translate(_LOOKALIKES).split()).casefold()


def quote_found(evidence: str | None, text: str) -> bool:
    """True if every ` | `-separated part of the quote appears in the posting.

    Case, whitespace, curly quotes and dashes are ignored, so this catches made-up or
    paraphrased quotes, not copying slips.
    """
    if not evidence:
        return False
    parts = [part for part in evidence.split(" | ") if part.strip()]
    haystack = _squash(text)
    return bool(parts) and all(_squash(part) in haystack for part in parts)


def tidy(field: str, value: object) -> object:
    """Formatting the guide fixes exactly: degree levels in guide order, no repeated skills."""
    if field == "degree_levels":
        return [level for level in DEGREE_LEVELS if level in value]
    if field == "skills":
        return list(dict.fromkeys(value))
    return value


def review_reasons(
    values: dict[str, object],
    evidence: dict[str, str | None],
    unsure_fields: list[str],
    text: str,
) -> dict[str, list[str]]:
    """Why each field needs a person to look at it. An empty list means it doesn't."""
    reasons: dict[str, list[str]] = {field: [] for field in values}
    for field, value in values.items():
        if field in unsure_fields:
            reasons[field].append("model unsure")
        # A "not stated" value has no quote by design, so only stated values need one.
        if is_stated(value) and not quote_found(evidence[field], text):
            reasons[field].append("evidence not found in posting")

    deadline = values.get("deadline")
    if deadline is not None:
        try:
            if not DATE_RE.fullmatch(deadline):
                raise ValueError
            date.fromisoformat(deadline)
        except ValueError:
            reasons["deadline"].append("deadline isn't a real YYYY-MM-DD date")

    term = values.get("start_term")
    if term is not None and not TERM_RE.fullmatch(term):
        reasons["start_term"].append("start_term isn't 'Season YYYY'")

    # A date needs FIXED. FIXED without a date is allowed (a deadline with no year, guide v2);
    # the prompt has the model mark that field unsure, so it's flagged anyway.
    both = "deadline" in values and "deadline_type" in values
    if both and deadline is not None and values["deadline_type"] != "FIXED":
        for field in ("deadline", "deadline_type"):
            reasons[field].append("deadline and deadline_type disagree")

    pay = values.get("pay")
    if isinstance(pay, Pay) and pay.min is not None and pay.max is not None and pay.min > pay.max:
        reasons["pay"].append("pay min is bigger than max")
    return reasons


# ---------- the backend ----------


class TeacherBackend:
    name = "teacher"
    model_version = "teacher-2"  # 2: per-field unsure, evidence checks, posting header

    def __init__(self, client=None):
        """`client` is for tests. Normally it's built from TEACHER_* settings."""
        self.deployment_name = settings.TEACHER_MODEL
        if client is None:
            if not settings.TEACHER_BASE_URL or not settings.TEACHER_API_KEY:
                raise RuntimeError(
                    "Set TEACHER_API_KEY and TEACHER_BASE_URL in .env to use the teacher backend."
                )
            client = AnthropicFoundry(
                api_key=settings.TEACHER_API_KEY,
                base_url=settings.TEACHER_BASE_URL,
                max_retries=5,  # rides out short rate-limit (429) and overload (529) spells
            )
        self.client = client
        # Tokens for every call this backend made, failed ones included, for cost reports
        self.token_totals = dict.fromkeys(PRICE_PER_MTOK, 0)
        # The teacher guide is the whole system prompt
        self.system_prompt = TEACHER_GUIDE.read_text(encoding="utf-8")
        self.system_prompt_hash = hashlib.sha256(self.system_prompt.encode()).hexdigest()

    def extract(self, text: str, fields: list[str]) -> dict[str, FieldResult]:
        results, _record = self.label(text, fields)
        return results

    def label(
        self, text: str, fields: list[str], *, posting_hash: str | None = None
    ) -> tuple[dict[str, FieldResult], dict]:
        """extract(), plus the run-log record (tokens, raw output, review reasons).

        `posting_hash` is the manifest hash, for scripts that label stored postings. It's
        logged as given (None when unknown). The header makes the text differ from the raw
        body, so content_hash(text) is logged separately as `input_hash`: it never matches
        a manifest hash.
        """
        # ALL_FIELDS order, so the same field set always hits the same output_model cache entry
        requested = fields or ALL_FIELDS
        fields = [f for f in ALL_FIELDS if f in requested]

        # Filled in as the call goes, and written in `finally` so failures are logged too.
        record: dict = {
            "model_id": self.deployment_name,
            "model_version": self.model_version,
            "prompt_hash": self.system_prompt_hash,
            "timestamp": datetime.now(UTC).isoformat(),
            "posting_hash": posting_hash,
            "input_hash": content_hash(text),
            "requested_fields": fields,
        }
        model = output_model(tuple(fields))
        try:
            response = self.client.messages.create(
                model=self.deployment_name,
                max_tokens=4000,  # 12 fields with evidence quotes can run past 1024
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": f"<posting>\n{text}\n</posting>"}],
                output_config={"format": output_format(tuple(fields))},
            )
            record["stop_reason"] = response.stop_reason
            record["token_counts"] = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
                "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
            }
            for kind, count in record["token_counts"].items():  # billed even if parsing fails
                self.token_totals[kind] += count

            # Validated here, not by messages.parse(), so a reply cut off at max_tokens or a
            # refusal still has its stop reason, tokens and raw text in the log.
            reply = "".join(block.text for block in response.content if block.type == "text")
            try:
                labels = model.model_validate_json(reply)
            except ValidationError:
                record["raw_reply"] = reply
                raise ValueError(
                    f"Reply didn't match the schema (stop_reason={response.stop_reason})"
                ) from None
            record["raw_output"] = labels.model_dump(mode="json")

            values = {field: tidy(field, getattr(labels, field).value) for field in fields}
            evidence = {field: getattr(labels, field).evidence for field in fields}
            reasons = review_reasons(values, evidence, labels.unsure_fields, text)
            record["review_reasons"] = {field: why for field, why in reasons.items() if why}
        except BaseException as error:  # BaseException so Ctrl+C mid-call is logged too
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            write_log(record)

        results = {
            field: FieldResult(
                value=values[field],
                confidence=0.5,  # placeholder until Stage 7 calibration
                evidence=evidence[field],
                needs_review=bool(reasons[field]),
                source="model",
            )
            for field in fields
        }
        return results, record


def write_log(record: dict) -> None:
    """Append one JSON line to today's run log (gitignored: it holds posting quotes)."""
    LOGS.mkdir(parents=True, exist_ok=True)
    file = LOGS / f"{datetime.now(UTC).date().isoformat()}.jsonl"
    with open(file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------- cost ----------
# Price per million tokens for the teacher model. Check the provider's current price
# before you write the estimate. These are Claude Sonnet 4.6's list prices on Foundry.
PRICE_PER_MTOK = {
    "input_tokens": 3.00,
    "output_tokens": 15.00,
    "cache_read_input_tokens": 0.30,  # 0.1x input
    "cache_creation_input_tokens": 3.75,  # 1.25x input, 5-minute cache
}


def cost(token_counts: dict[str, int]) -> float:
    """Dollars for one call's (or a run's summed) token counts."""
    return sum(count / 1_000_000 * PRICE_PER_MTOK[kind] for kind, count in token_counts.items())


# ---------- Step 5.3: pilot, then price it ----------
PILOT_SIZE = 50
TRAIN_POOL = PROJECT_ROOT / "data" / "manifests" / "train_pool.jsonl"
RAW = PROJECT_ROOT / "data" / "raw"


if __name__ == "__main__":
    with open(TRAIN_POOL, encoding="utf-8") as file:
        pool = [json.loads(line)["hash"] for line in file if line.strip()]

    teacher = TeacherBackend()
    succeeded, failed, flagged = 0, 0, 0
    flagged_by_field = dict.fromkeys(ALL_FIELDS, 0)

    for i, posting_hash in enumerate(pool[:PILOT_SIZE], start=1):
        raw_file = RAW / f"{posting_hash.removeprefix('sha256:')}.json"
        text = render_posting(json.loads(raw_file.read_text(encoding="utf-8")))
        try:
            results, record = teacher.label(text, list(ALL_FIELDS), posting_hash=posting_hash)
        except Exception as error:  # noqa: BLE001 -- already logged by label(); keep going
            failed += 1
            print(f"[{i}] failed: {error}")
            continue
        succeeded += 1
        flagged += any(result.needs_review for result in results.values())
        for field in record["review_reasons"]:
            flagged_by_field[field] += 1
        print(f"[{i}/{PILOT_SIZE}] done")

    totals = teacher.token_totals  # every call, failed ones too: they're billed
    per_posting = cost(totals) / max(succeeded + failed, 1)
    print(f"\nPilot: {succeeded} succeeded, {failed} failed")
    print(f"Postings with at least one field to review: {flagged} of {succeeded}")
    print("Fields to review, by field:")
    for field, count in flagged_by_field.items():
        print(f"  {field}: {count}")
    print("Average tokens per posting:")
    for kind, count in totals.items():
        print(f"  {kind}: {count / max(succeeded + failed, 1):,.0f}")
    print(f"Pilot cost: ${cost(totals):.2f} (${per_posting:.4f} per posting)")
    print(f"Estimate for the full pool ({len(pool):,} postings): ${per_posting * len(pool):.2f}")
