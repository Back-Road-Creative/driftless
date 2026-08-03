"""Scaffold-level contract tests.

These assert the three things every later phase depends on: the package is
importable under its declared name, `driftless.calc` exists as a package so the
pure-calculation modules (evm, rollup, forecast) can be added independently
without any of them editing a shared registry file, and no module reaches into
another module's private names.
"""

import ast
import importlib
from pathlib import Path

import driftless


def test_package_exposes_version() -> None:
    assert isinstance(driftless.__version__, str)
    assert driftless.__version__.count(".") == 2


def test_calc_is_an_importable_package() -> None:
    calc = importlib.import_module("driftless.calc")
    assert calc.__spec__ is not None
    assert calc.__spec__.submodule_search_locations is not None


def test_no_module_imports_a_private_name_from_another_module() -> None:
    """A leading underscore means "mine" — so nothing else may import it.

    Walks the package's own source rather than trusting review: an
    ``from driftless.x import _y`` marks ``_y`` private and depends on it in the
    same breath, and the next person refactoring ``x`` reads the underscore as
    permission to change it and silently breaks the importer. A helper two
    modules need is public API and carries a public name; a name that stays
    private stays unimported. Aliasing a public name privately on import
    (``import trend_delta as _trend_delta``) is untouched — the imported NAME is
    what the owning module marked — and so are dunders (``__version__``), which the
    convention makes public rather than private.
    """
    package = Path(driftless.__file__).parent
    reach_ins = [
        f"{path.relative_to(package)}:{node.lineno} imports {name} from {node.module}"
        for path in sorted(package.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("driftless")
        for name in (alias.name for alias in node.names)
        if name.startswith("_") and not name.endswith("__")
    ]
    assert not reach_ins, "private names imported across modules: " + "; ".join(reach_ins)
