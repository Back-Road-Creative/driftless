"""The sign-off write is a service both surfaces call, and it resolves the signer once.

``driftless.web.sign_off`` used to call the JSON *route function* to append its row.
That kept the two write paths honest — the property
``tests/test_secure.py::test_the_privileged_paths_are_exactly_the_routes_that_write_a_sign_off``
still derives from the live route table — but it was the last name ``driftless.web``
read off ``driftless.api.app``, and so the last strand of the import cycle the
mount-once flag and the lifespan backstop exist to sequence around.

The write moves to :mod:`driftless.services.sign_offs`, which neither side imports the
other to reach. Two things that were previously true only by reading the code are
asserted here instead: the service is a leaf, and the signer is resolved **once** per
write path. The web form used to stamp the principal over the posted claim and then
hand the result to the route, which stamped it again — harmless only because
:func:`driftless.api.deps.signer` happens to be idempotent, which is not a property the
ledger should depend on.
"""

from __future__ import annotations

import ast
from pathlib import Path

from driftless.api import app as app_module
from driftless.services import sign_offs

SRC = Path(app_module.__file__).resolve().parents[1]
MOVED = frozenset({"create_sign_off", "stamped_signal"})


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _imported_from(tree: ast.Module, module: str) -> set[str]:
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    }


def test_the_write_moved_off_the_app() -> None:
    """The point of the unit — no module reaches into ``driftless.api.app`` for it."""
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if MOVED & _imported_from(_tree(path), "driftless.api.app")
    ]
    assert not offenders, f"import these from driftless.services.sign_offs: {offenders}"


def test_the_service_layer_is_a_leaf() -> None:
    """A service that imports a caller back would rebuild the cycle one level down."""
    above = ("driftless.api.app", "driftless.web")
    offenders = {
        path.relative_to(SRC).as_posix(): sorted(
            node.module or ""
            for node in ast.walk(_tree(path))
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(above)
        )
        for path in (SRC / "services").rglob("*.py")
    }
    assert not {k: v for k, v in offenders.items() if v}, offenders


def test_the_score_lookup_is_no_longer_deferred() -> None:
    """``stamped_signal`` deferred its ``assess`` import because it sat above it."""
    deferred = [
        node.module
        for fn in ast.walk(_tree(Path(sign_offs.__file__)))
        if isinstance(fn, ast.FunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not deferred, f"import these at module scope: {deferred}"


def test_the_signer_is_resolved_once_per_write_path() -> None:
    """Each handler resolves the principal; the service takes the name already decided."""
    counted = {
        path: sum(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "signer"
            for node in ast.walk(_tree(SRC / path))
        )
        for path in ("api/app.py", "web/sign_off.py", "services/sign_offs.py")
    }
    assert counted == {"api/app.py": 1, "web/sign_off.py": 1, "services/sign_offs.py": 0}
