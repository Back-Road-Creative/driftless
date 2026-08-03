"""Server-rendered views. The caller mounts the routers where it wants them.

The public names are resolved lazily (``__getattr__``) rather than imported at
package load. ``driftless.web.home`` and ``driftless.web.pages`` import ``get_session``
and the write helpers from ``driftless.api.app``, and ``api.app`` mounts these routers
at its own import time — so eagerly importing the submodules here would form an
import cycle whose outcome depends on which module loads first (and, loaded
wrong, silently drops the mounted routes). Deferring the import until the name is
actually used breaks that cycle cleanly.
"""

from pathlib import Path
from typing import Any


def static_dir() -> str:
    """The directory of vendored static assets (served at ``/static``)."""
    return str(Path(__file__).parent / "static")


def __getattr__(name: str) -> Any:
    if name == "create_router":
        from driftless.web.home import create_router

        return create_router
    if name == "create_pages_router":
        from driftless.web.pages import create_pages_router

        return create_pages_router
    if name == "create_departments_router":
        from driftless.web.departments import create_departments_router

        return create_departments_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["create_departments_router", "create_pages_router", "create_router", "static_dir"]
