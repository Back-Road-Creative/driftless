"""One write boundary: the wizard, the status page and sign-off all go through
:mod:`driftless.services`, every write entry point there requires a
caller-supplied actor, and the stale-write rule they could someday reuse lives
in exactly one place.

Wave 1.2's grounding (``api/crud.py:47-108`` carried the only ``If-Match``/
``row_revision`` check, and ``driftless.services`` held exactly two modules) is
pinned here: a write function that grows an optional actor, or a second copy of
the precondition check, fails this file. ``api/app.py`` and ``web/status.py``
hand through the identity ``driftless.api.deps.get_session`` already resolved
(``driftless.api.deps.resolved_actor``) rather than re-deriving it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from driftless.api import crud
from driftless.services import concurrency, wizard_writes
from driftless.services.concurrency import check_revision
from driftless.services.sign_offs import create_sign_off
from driftless.services.status_snapshots import create_status_snapshot
from driftless.services.wizard_writes import produce

SRC = Path(__file__).resolve().parents[1] / "driftless"

#: Every public write entry point in ``driftless.services``, and the name of the
#: parameter that must carry a non-optional actor.
REQUIRED_ACTOR_ENTRY_POINTS = {
    create_status_snapshot: "actor",
    create_sign_off: "signed_by",
    produce: "actor",
}


def test_every_write_entry_point_requires_an_actor() -> None:
    for fn, actor_param in REQUIRED_ACTOR_ENTRY_POINTS.items():
        signature = inspect.signature(fn)
        assert actor_param in signature.parameters, f"{fn.__qualname__} takes no {actor_param}"
        param = signature.parameters[actor_param]
        assert param.default is inspect.Parameter.empty, (
            f"{fn.__qualname__}'s {actor_param} carries a default — an omitted actor "
            "would write silently uncredited"
        )
        assert param.annotation in (str, "str"), (
            f"{fn.__qualname__}'s {actor_param} is not a bare str"
        )


def test_calling_a_write_entry_point_with_no_actor_refuses() -> None:
    """The signature check above is static; this is the same guarantee at the call
    site — an omitted actor is a ``TypeError``, not a write that lands uncredited."""
    for fn, actor_param in REQUIRED_ACTOR_ENTRY_POINTS.items():
        bound = {name: object() for name in inspect.signature(fn).parameters if name != actor_param}
        try:
            fn(**bound)  # type: ignore[arg-type]
        except TypeError as error:
            assert actor_param in str(error), f"{fn.__qualname__} refused for the wrong reason"
        else:
            raise AssertionError(f"{fn.__qualname__} accepted a call with no {actor_param}")


def test_the_precondition_rule_is_not_duplicated() -> None:
    """``driftless.api.crud`` imports the one rule rather than keeping its own copy."""
    assert crud.check_revision is check_revision


def test_the_stale_write_rule_lives_in_services_concurrency() -> None:
    tree = ast.parse(Path(concurrency.__file__).read_text())
    defined = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef,))}
    assert "check_revision" in defined


def _calls_session_write(tree: ast.Module) -> list[str]:
    """Every ``<something>.add(``/``.commit(``/``.flush(`` call in ``tree`` — a
    module writing through ``insert``/``services.*`` never spells these itself."""
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"add", "commit", "flush"}
    ]


def test_the_wizard_and_web_write_surfaces_never_touch_the_session_directly() -> None:
    """The three surfaces this wave moved behind ``services/*`` stay moved.

    Scoped to the files the plan named, not every module under ``web/``/``wizard/``:
    a write outside this wave's scope (``web/login.py``'s session-revoking commit,
    say) is somebody else's boundary to move, not a regression this file catches.
    """
    scoped = (
        SRC / "wizard" / "engine.py",
        SRC / "wizard" / "cli.py",
        SRC / "web" / "wizard_pages.py",
        SRC / "web" / "status.py",
        SRC / "web" / "sign_off.py",
    )
    offenders = {
        path.relative_to(SRC).as_posix(): calls
        for path in scoped
        if (calls := _calls_session_write(ast.parse(path.read_text())))
    }
    assert not offenders, f"writes the session directly instead of through services/*: {offenders}"


def test_services_stays_a_leaf_including_the_new_modules() -> None:
    """Same guarantee ``test_sign_off_service.py`` already pins, extended to the
    two modules this wave adds."""
    above = ("driftless.api.app", "driftless.web")
    offenders = {
        path.relative_to(SRC).as_posix(): sorted(
            node.module or ""
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(above)
        )
        for path in (SRC / "services").rglob("*.py")
    }
    assert not {k: v for k, v in offenders.items() if v}, offenders


def test_wizard_writes_reuses_the_status_snapshot_service() -> None:
    """The wizard's status-report producer files through the one shared service,
    rather than a second copy of "stamp percent from calc"."""
    source = inspect.getsource(wizard_writes._make_status_report)
    assert "create_status_snapshot" in source
