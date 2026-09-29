"""The stamped percent belongs with the calc it reads, not with the API.

``stamped_percent`` computed a project's completion through
:func:`driftless.assess.adapters.project_snapshot` while living in
:mod:`driftless.api.app`, so it had to import ``assess`` from inside its own body —
``assess`` sits below the API, and a module-scope import would have run the wrong way.
Moving the function into ``assess`` removes the reason for the deferral rather than
keeping the deferral and a comment explaining it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from driftless.api import app as app_module
from driftless.assess import percent

SRC = Path(app_module.__file__).resolve().parents[1]


def _module_scope_names(tree: ast.Module) -> set[str]:
    """Names bound by an import at module scope — either import form, alias honoured."""
    return {
        (alias.asname or alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


def test_the_stamped_percent_lives_with_the_calc_it_reads() -> None:
    assert callable(percent.stamped_percent)


def test_nothing_takes_the_stamped_percent_off_the_app() -> None:
    """It was never re-exported: only two callers ever imported it, and both moved."""
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if "stamped_percent"
        in {
            alias.name
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom) and node.module == "driftless.api.app"
            for alias in node.names
        }
    ]
    assert not offenders, f"import it from driftless.assess.percent: {offenders}"


def test_the_calc_import_is_no_longer_deferred() -> None:
    """The whole point of the move — a function-body import here means it did not land."""
    tree = ast.parse(Path(percent.__file__).read_text())
    deferred = [
        node.module
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not deferred, f"import these at module scope: {deferred}"
    assert "adapters" in _module_scope_names(tree), "the calc is reached at module scope"
