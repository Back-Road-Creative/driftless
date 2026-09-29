"""The served surface must not depend on which module the process imported first.

``driftless.web.*`` used to import its session and write helpers from
``driftless.api.app``, so mounting the web routers *at that module's import* closed a
cycle: a process that reached for a page module first re-entered ``api.app``, which
asked the half-executed web module for a router it had not defined yet and died with a
circular ``ImportError`` — eleven of the fourteen ``driftless/web`` submodules did, the
suite staying green only because isort sorts ``driftless.api`` above ``driftless.web``
in every test file that imports both.

The cycle is gone: those helpers live in the leaf modules ``driftless.api.deps``,
``driftless.assess.percent`` and ``driftless.services.*``, and nothing under
``driftless/web`` imports ``driftless.api.app`` any more. So the machinery that made the
old order survivable — a ``web_mid_import()`` probe reading ``__spec__._initializing``
off every loaded module, a ``_web_mounted`` flag, and a second ``mount_web`` call from
the lifespan as the backstop — is gone with it. The mount is one unconditional call at
import.

This file holds both halves. The behavioural half is unchanged and still driven through
real subprocesses, because the defect belonged to a *fresh interpreter's* import order,
which a process already holding both modules cannot see. The structural half is new: it
fails if the flag or the backstop comes back, so removing them stays removed rather than
being re-added the next time an import looks circular.
"""

import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from driftless.api import assembly
from driftless.api.app import app
from driftless import web

ROOT = Path(__file__).resolve().parents[1]


def _paths(served: Any) -> list[str]:
    """Every route path ``served`` answers, descending into ``include_router`` wrappers —
    FastAPI hangs an included router's routes off one rather than copying them onto the
    app, so a flat read of ``app.routes`` finds no page at all."""

    def leaves(route: Any) -> list[Any]:
        for holder in (route, getattr(route, "original_router", None)):
            children = getattr(holder, "routes", None)
            if children:
                return [leaf for child in children for leaf in leaves(child)]
        return [route]

    return sorted({getattr(leaf, "path", "") for r in served.routes for leaf in leaves(r)})


# Imports a web submodule first, then reports what the app serves: the route paths, and
# whether a page-surface 404 still renders the designed HTML.
PROBE = """
import json
from typing import Any

import driftless.web.status  # the import that used to raise a circular ImportError
from fastapi.testclient import TestClient

from driftless.api.app import app

%s

with TestClient(app) as client:
    missing = client.get("/nope", headers={"accept": "text/html"})
print(json.dumps({
    "paths": _paths(app),
    "missing": [missing.status_code, missing.headers["content-type"].split(";")[0]],
}))
""" % inspect.getsource(_paths)

# The same web-first order WITHOUT ever starting the app. The lifespan used to be the
# backstop that mounted the pages for this order, so a bare import had to serve a
# smaller table than a started one; now there is nothing left to run late.
NO_LIFESPAN_PROBE = """
import json
from typing import Any

import driftless.web.status

from driftless.api.app import app

%s

print(json.dumps({"paths": _paths(app)}))
""" % inspect.getsource(_paths)


def _run(tmp_path: Path, code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a clean interpreter reading THIS checkout, from ``tmp_path`` so
    the sqlite file the lifespan opens never lands in the tree."""
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "DRIFTLESS_DATABASE_URL": f"sqlite:///{tmp_path / 'probe.db'}",
    }
    return subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True
    )


def test_a_web_submodule_imports_on_its_own_in_a_clean_process(tmp_path: Path) -> None:
    """The plain reproduction: no app, no client, just the import a caller would write."""
    done = _run(tmp_path, "import driftless.web.status")

    assert done.returncode == 0, done.stderr


def test_the_served_surface_is_the_same_whichever_module_was_imported_first(
    tmp_path: Path,
) -> None:
    """The route table a bare ``import driftless.api.app`` exposes — what the credential
    gate compiles its page patterns from, and what dozens of tests read before any
    lifespan runs — is also what a web-first process serves, error pages included."""
    done = _run(tmp_path, PROBE)
    assert done.returncode == 0, f"the web-first process failed:\n{done.stderr}"
    web_first: dict[str, Any] = json.loads(done.stdout)
    at_import = _paths(app)

    assert {"/", "/static", "/projects/{project_id}/hub"} <= set(at_import), "mounted on import"
    assert web_first["paths"] == at_import
    assert web_first["missing"] == [404, "text/html"], "the designed HTML page, not JSON"


def test_the_pages_are_mounted_without_starting_the_app(tmp_path: Path) -> None:
    """Web-first AND never started — the order the deleted backstop existed to rescue."""
    done = _run(tmp_path, NO_LIFESPAN_PROBE)
    assert done.returncode == 0, f"the web-first process failed:\n{done.stderr}"

    assert json.loads(done.stdout)["paths"] == _paths(app)


def test_the_import_order_machinery_is_gone() -> None:
    """No flag, no probe — the cycle they worked around no longer exists to work around.

    Asserted on the module's own surface rather than on behaviour, because the failure
    they cause is silent: a re-added ``_web_mounted`` guard would keep every test above
    green while quietly making the mount depend on call order again.
    """
    gone = [name for name in ("web_mid_import", "_web_mounted") if hasattr(assembly, name)]
    assert not gone, f"the mount is unconditional now: {gone}"


def test_the_web_mount_has_exactly_one_unconditional_call_site() -> None:
    """One call, inside ``create_app``, reached whenever the factory runs.

    It sat at module scope when this check was written, and "not inside any function" was
    how the check said "unconditional". The factory moved it inside ``create_app`` on
    purpose, so that wording would now fail for the right code. What still matters, and is
    what a second mount or a re-added ``_web_mounted`` guard would break, is that there is
    exactly ONE call and no condition decides whether it runs.
    """
    tree = ast.parse((ROOT / "driftless" / "api" / "app.py").read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        if node.func.id == "mount_web"
    ]
    assert len(calls) == 1, f"mount_web is called {len(calls)} times"

    factory = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    assert calls[0] in set(ast.walk(factory)), "the mount left create_app"
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        if calls[0] in set(ast.walk(node))
    ]
    assert not guarded, "a condition decides whether the pages mount again"


def test_the_web_package_resolves_its_names_eagerly() -> None:
    """No ``__getattr__``: the package imports its router factories at load.

    The lazy resolver existed for the same cycle the mount flag did — eagerly importing
    the submodules here would have re-entered ``driftless.api.app``. With that gone, a
    deferred name buys nothing and costs the thing every lazy attribute costs: a typo in
    ``__all__`` raises at first use rather than at import.
    """
    assert not hasattr(web, "__getattr__"), "the names resolve at import now"
    missing = [name for name in web.__all__ if not hasattr(web, name)]
    assert not missing, f"declared in __all__ but never bound: {missing}"


def test_nothing_defers_a_web_import_to_dodge_a_cycle() -> None:
    """A function-body ``driftless.web`` import in the assembly module meant one thing."""
    tree = ast.parse((ROOT / "driftless" / "api" / "assembly.py").read_text())
    deferred = [
        node.module
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("driftless")
    ]
    assert not deferred, f"import these at module scope: {sorted(set(deferred))}"
