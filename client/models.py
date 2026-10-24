"""Plain result objects the team app works with.

Standard-library dataclasses on purpose: the team repo then needs no Pydantic,
only httpx. Dates stay ISO strings; Django parses them where it needs to.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FieldValue:
    value: Any
    confidence: float
    evidence: str | None
    needs_review: bool
    source: str


@dataclass(frozen=True)
class ExtractionResult:
    backend: str
    model_version: str
    fields: dict[str, FieldValue]
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> "ExtractionResult":
        return cls(
            backend=data["backend"],
            model_version=data["model_version"],
            fields={name: FieldValue(**f) for name, f in data["fields"].items()},
            warnings=data.get("warnings", []),
        )


@dataclass(frozen=True)
class FetchedPosting:
    external_id: str
    title: str
    organization: str
    location_raw: str | None
    url: str
    updated_at: str | None
    text: str
    content_hash: str
    structured: dict

    @classmethod
    def from_json(cls, data: dict) -> "FetchedPosting":
        return cls(**data)
