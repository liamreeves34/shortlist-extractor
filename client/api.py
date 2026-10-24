import os

import httpx

from .models import ExtractionResult, FetchedPosting, FieldValue
from .stub_data import STUB_FIELDS, stub_postings

TIMEOUT_SECONDS = 30.0


class ExtractionError(Exception):
    """The extraction service couldn't answer. Fall back to manual entry."""


def _mode() -> str:
    return os.environ.get("EXTRACTOR_MODE", "stub")


def _base_url() -> str:
    return os.environ.get("EXTRACTOR_URL", "http://localhost:8001")


def extract(
    *,
    text: str | None = None,
    url: str | None = None,
    fields: list[str] | None = None,
    http: httpx.Client | None = None,
) -> ExtractionResult:
    # Extract fields from posting text (or a supported job board URL).
    if (text is None) == (url is None):
        raise ValueError("Pass exactly one of text= or url=.")
    if _mode() == "stub":
        wanted = fields or list(STUB_FIELDS)
        return ExtractionResult(
            backend="offline-stub",  # "stub" means the service answered; this means it was never called
            model_version="stub-1",
            fields={name: FieldValue(**STUB_FIELDS[name]) for name in wanted},
        )
    data = _post("/v1/extract", {"text": text, "url": url, "fields": fields}, http)
    return ExtractionResult.from_json(data)


def fetch_source(
    *, provider: str, token: str, http: httpx.Client | None = None
) -> list[FetchedPosting]:
    # Fetch one employer's internship postings from its public job board.
    if _mode() == "stub":
        return [FetchedPosting.from_json(p) for p in stub_postings(provider, token)]
    data = _post("/v1/sources/fetch", {"provider": provider, "token": token}, http)
    return [FetchedPosting.from_json(p) for p in data["postings"]]


def _post(path: str, payload: dict, http: httpx.Client | None) -> dict:
    # `http` lets tests pass FastAPI's TestClient instead of a real network client.
    try:
        if http is not None:
            response = http.post(path, json=payload)
        else:
            with httpx.Client(base_url=_base_url(), timeout=TIMEOUT_SECONDS) as client:
                response = client.post(path, json=payload)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        status, body = exc.response.status_code, exc.response.text[:200]
        raise ExtractionError(f"Extractor returned {status}: {body}") from exc
    except httpx.HTTPError as exc:
        raise ExtractionError(f"Couldn't reach the extractor at {_base_url()}: {exc}") from exc
