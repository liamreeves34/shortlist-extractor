import importlib

import pytest


# Placeholder until E1 adds real tests. It also proves the repo root is on
# sys.path (pyproject's pythonpath setting), which tests need with package = false.
@pytest.mark.parametrize("module", ["service", "service.backends", "service.connectors", "client"])
def test_package_imports(module):
    importlib.import_module(module)
