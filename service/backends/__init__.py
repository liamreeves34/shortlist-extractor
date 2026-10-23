"""Picks the backend named by EXTRACTOR_BACKEND.

Imports happen inside each branch on purpose. The student backend imports
PyTorch, which isn't even installed in the stub image. Importing it only when
it's chosen keeps the other backends working without it.
"""

from service.backends.base import Backend


def load_backend(name: str) -> Backend:
    if name == "stub":
        from service.backends.stub import StubBackend

        return StubBackend()
    # Added later, one per stage:
    # if name == "rules":   from service.backends.rules import RulesBackend; return RulesBackend()
    # if name == "teacher": from service.backends.teacher import TeacherBackend; return TeacherBackend()
    # if name == "student": from service.backends.student import StudentBackend; return StudentBackend()
    raise NotImplementedError(f"Backend {name!r} isn't built yet.")
