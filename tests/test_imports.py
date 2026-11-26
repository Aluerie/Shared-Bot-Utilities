# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Every module of the package can be imported."""

import importlib
from pathlib import Path

import pytest

import shared

SHARED_ROOT = Path(shared.__file__).parent


def _all_modules() -> list[str]:
    """Dotted names of all modules in the package, without the tests and hidden folders like a local ``.venv``."""
    modules: list[str] = []
    for dirpath, dirnames, filenames in SHARED_ROOT.walk():
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "_")) and d != "tests")
        package = dirpath.relative_to(SHARED_ROOT).parts
        modules.extend(
            ".".join(("shared", *package, name.removesuffix(".py")))
            for name in sorted(filenames)
            if name.endswith(".py") and name != "__init__.py"
        )
    return modules


@pytest.mark.parametrize("module", _all_modules())
def test_module_imports(module: str) -> None:
    importlib.import_module(module)


@pytest.mark.parametrize("module_name", [*_all_modules(), "shared", "shared.concepts"])
def test_all_names_exist(module_name: str) -> None:
    """Names listed in ``__all__`` really are defined in their modules."""
    module = importlib.import_module(module_name)
    for name in getattr(module, "__all__", ()):
        assert hasattr(module, name), f"{module_name}.__all__ lists missing {name!r}"
