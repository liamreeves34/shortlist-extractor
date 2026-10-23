"""What every backend must look like.

The API never knows which backend it's talking to. It only knows this shape:
a name, a model version, and an extract() method. Stub, rules, teacher, and
student all fit it, which is why switching between them is one setting.
"""

from typing import Protocol

from service.schemas import FieldResult

# class Field_Result(BaseModel):
#     value        : str | list[str] | Pay | None
#     confidence   : float =Field(ge=0.0, le=1.0)
#     evidence     : str | None = None
#     needs_review : bool
#     source       : Literal["model", "rules"]


class Backend(Protocol):
    name: str
    model_version: str

    def extract(self, text: str, fields: list[str]) -> dict[str, FieldResult]:
        """Return a FieldResult for each requested field, and only those."""
        ...
