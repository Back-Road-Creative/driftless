"""Server-rendered views. The caller mounts the routers where it wants them.

These four names used to be resolved lazily through ``__getattr__``, because
``driftless.web`` submodules imported their write helpers from ``driftless.api.app``
while ``api.app`` mounted these routers at its own import — a cycle whose outcome
depended on which module loaded first and which, loaded wrong, silently dropped the
mounted routes. Those helpers live in leaf modules now (``driftless.api.deps``,
``driftless.assess.percent``, ``driftless.services``), nothing here imports
``driftless.api.app``, and so the names are plain imports again: a typo in ``__all__``
fails at import rather than at whatever moment first reaches for the attribute.
"""

from pathlib import Path

from driftless.web.configuration import create_configuration_router
from driftless.web.departments import create_departments_router
from driftless.web.home import create_router
from driftless.web.scorecard import create_scorecard_router


def static_dir() -> str:
    """The directory of vendored static assets (served at ``/static``)."""
    return str(Path(__file__).parent / "static")


__all__ = [
    "create_configuration_router",
    "create_departments_router",
    "create_router",
    "create_scorecard_router",
    "static_dir",
]
