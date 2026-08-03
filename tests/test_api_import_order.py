"""The served surface must not depend on which module the process imported first.

``driftless.web.*`` imports its session and write helpers from ``driftless.api.app``,
so mounting the web routers *at that module's import* closed a cycle: a process that
reached for a page module first re-entered ``api.app``, which asked the half-executed
web module for a router it had not defined yet and died with a circular ``ImportError``
— eleven of the fourteen ``driftless/web`` submodules did, the suite staying green only
because isort sorts ``driftless.api`` above ``driftless.web`` in every test file that
imports both. Driven through real subprocesses rather than ``importlib.reload``: the
defect belongs to a *fresh interpreter's* import order, which a process already holding
both modules cannot see. This one is the api-first control, by its own import."""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from driftless.api.app import app

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

import driftless.web.pages  # the import that used to raise a circular ImportError
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
    done = _run(tmp_path, "import driftless.web.pages")

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
