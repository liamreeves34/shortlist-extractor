"""The stub backend: canned answers, instantly, for any text."""

from client.stub_data import STUB_FIELDS
from service.schemas import FieldResult


class StubBackend:
    name = "stub"
    model_version = "stub-1"

    def extract(self, text: str, fields: list[str]) -> dict[str, FieldResult]:
        return {field: FieldResult(**STUB_FIELDS[field]) for field in fields}
