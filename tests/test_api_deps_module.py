"""The request-scoped dependencies live below the app, not inside it.

``driftless.web`` needs the session dependency and the sign-off signer; it used to
import both from ``driftless.api.app``, which imports ``driftless.web`` back to mount
the page routers. That cycle is why the mount runs behind a flag and a lifespan
backstop. Moving the dependencies into a leaf module (``driftless.api.deps``) removes
the reason for the edge rather than sequencing around it.

``api.app`` keeps importing the same objects, so ``app.get_session`` stays the very
object every test overrides — ``dependency_overrides`` keys on identity, and 58 test
modules take their key from ``driftless.api.app``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from driftless.api import app as app_module
from driftless.api import deps

WEB = Path(app_module.__file__).resolve().parents[1] / "web"

# The names ``driftless.web`` used to take off ``driftless.api.app``. Each is now
# ``driftless.api.deps``'s to define; a web module reaching for one off ``app`` puts
# the cycle back.
MOVED = frozenset({"Db", "_actor", "get_session", "signer"})


def _imports_from_api_app(source: str) -> set[str]:
    """Every name a module imports out of ``driftless.api.app``."""
    tree = ast.parse(source)
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "driftless.api.app"
        for alias in node.names
    }


@pytest.mark.parametrize("path", sorted(WEB.glob("*.py")), ids=lambda p: p.name)
def test_no_web_module_takes_a_dependency_off_the_app(path: Path) -> None:
    assert not (_imports_from_api_app(path.read_text()) & MOVED), (
        f"{path.name} imports a moved dependency from driftless.api.app; "
        "import it from driftless.api.deps"
    )


def test_the_app_re_exports_the_same_objects() -> None:
    """Identity, not merely equality — ``dependency_overrides`` keys on the callable.

    ``_actor`` is deliberately NOT re-exported: nothing outside the dependencies
    themselves ever took it off the app.
    """
    for name in ("get_session", "signer"):
        assert getattr(app_module, name) is getattr(deps, name), name
    assert app_module.Db is deps.Db


def test_the_dependencies_do_not_import_the_app_back() -> None:
    """A leaf, or the move bought nothing."""
    assert not _imports_from_api_app(Path(deps.__file__).read_text())
