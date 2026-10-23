from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

CONTRACT_VERSION = "1.0"
FieldName = Literal[
    "title",
    "organization",
    "location",
    "start_term",
    "deadline",
    "deadline_type",
    "degree_levels",
    "citizenship",
    "clearance",
    "work_mode",
    "pay",
    "skills",
]
ALL_FIELDS: tuple[str, ...] = get_args(FieldName)


# ---------- /v1/extract ----------


class ExtractRequest(BaseModel):
    text: str | None = Field(default=None, max_length=100_000)
    url: str | None = None
    fields: list[FieldName] | None = None  # None means "every field"

    @model_validator(mode="after")
    def exactly_one_input(self) -> "ExtractRequest":
        if (self.text is None) == (self.url is None):
            raise ValueError("Send exactly one of 'text' or 'url'.")
        return self


class Pay(BaseModel):
    min: float | None = None
    max: float | None = None
    period: Literal["HOUR", "YEAR", "UNKNOWN"] = "UNKNOWN"
    currency: str | None = None


class FieldResult(BaseModel):
    value: str | list[str] | Pay | None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str | None = None
    needs_review: bool
    source: Literal["model", "rules"]


class ExtractResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    backend: str
    model_version: str
    fields: dict[FieldName, FieldResult]
    warnings: list[str] = []


# ---------- /v1/sources/fetch ----------
class FetchRequest(BaseModel):
    provider: Literal["greenhouse", "lever", "ashby"]
    token: str = Field(min_length=1, max_length=100)


class Structured(BaseModel):
    work_mode: str | None = None
    pay: Pay | None = None
    commitment: str | None = None


class SourcePosting(BaseModel):
    external_id: str
    title: str
    organization: str
    location_raw: str | None = None
    url: str
    updated_at: datetime | None = None
    text: str
    content_hash: str
    structured: Structured = Structured()


class FetchResponse(BaseModel):
    provider: str
    token: str
    fetched_at: datetime
    postings: list[SourcePosting]


# ---------- /healthz ----------
class Health(BaseModel):
    status: Literal["ok"] = "ok"
    backend: str
    connector_mode: str
