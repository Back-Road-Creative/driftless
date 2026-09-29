"""Composes process explanation content out of per-knowledge-area modules
living in this package, so ten areas' worth of writing can happen in ten
concurrent pull requests without any of them touching a shared list — the
same shape as ``driftless.pmbok.technique_content``, over processes instead
of techniques.

A content module (a plain ``.py`` file directly inside this package, or
inside a fixture package a test points at) exports exactly two names:

``AREA: str``
    The ``driftless.pmbok.model.KnowledgeArea`` value the module supplies
    content for.
``CONTENT: dict[str, ProcessContent]``
    Explanation fields for zero or more process ids (PMBOK-6 clause numbers,
    e.g. ``"4.1"``), all of which must belong to ``AREA``.

``collect_content`` finds every such module with ``pkgutil.iter_modules`` —
never a hand-maintained import list — so adding an area's content is a
single new file here: nothing in this module or in
``process_definitions.py`` has to name it. A module that claims a key
outside its own area, a process id ``catalog.PROCESSES`` does not hold at
all, or a key another module already claimed, fails loudly at collection
time rather than silently losing content.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from dataclasses import dataclass

from driftless.pmbok import catalog
from driftless.pmbok.model import KnowledgeArea


@dataclass(frozen=True)
class ProcessContent:
    """One process's plain-language explanation fields. Everything about a
    process that is not an explanation — id, name, group, area, ITTOs —
    stays in ``driftless.pmbok.model.Process``.

    ``plain_summary`` is one sentence a non-PM understands; ``why_bother``,
    ``done_when`` and ``first_time_tip`` are each one to three sentences.
    ``worked_example`` walks a small realistic project through this process;
    ``pitfalls`` is two to four first-timer mistakes. Both default empty,
    like the older four fields once did, while areas still fill them in.
    """

    plain_summary: str = ""
    why_bother: str = ""
    done_when: str = ""
    first_time_tip: str = ""
    worked_example: str = ""
    pitfalls: tuple[str, ...] = ()


def collect_content(
    *,
    package_name: str = __name__,
    package_path: Iterable[str] = __path__,
) -> dict[str, ProcessContent]:
    """Import every submodule of the given package (this package, by
    default) and merge their ``CONTENT`` dicts, keyed by process id.

    ``package_name``/``package_path`` are only ever overridden by tests, which
    point this at a fixture package to prove the discovery mechanism itself —
    real callers take the defaults and get this package's own modules.
    """
    valid_areas = {area.value for area in KnowledgeArea}
    ids_by_area: dict[str, set[str]] = {}
    for process in catalog.PROCESSES:
        ids_by_area.setdefault(process.area.value, set()).add(process.id)

    content: dict[str, ProcessContent] = {}
    owners: dict[str, str] = {}
    for module_info in pkgutil.iter_modules(package_path, package_name + "."):
        module = importlib.import_module(module_info.name)

        area = getattr(module, "AREA", None)
        if not isinstance(area, str):
            raise TypeError(f"{module_info.name} must define AREA: str")
        if area not in valid_areas:
            raise ValueError(
                f"{module_info.name} AREA {area!r} is not one of KnowledgeArea's values"
            )
        area_ids = ids_by_area.get(area, set())

        module_content = getattr(module, "CONTENT", None)
        if not isinstance(module_content, dict):
            raise TypeError(f"{module_info.name} must define CONTENT: dict[str, ProcessContent]")

        for key, value in module_content.items():
            if not isinstance(key, str):
                raise TypeError(f"{module_info.name} CONTENT has a non-string key {key!r}")
            if not isinstance(value, ProcessContent):
                raise TypeError(f"{module_info.name} CONTENT[{key!r}] must be a ProcessContent")
            if key not in area_ids:
                raise ValueError(
                    f"{module_info.name} declares AREA {area!r} but claims {key!r}, "
                    "which is not a process in that area"
                )
            if key in owners:
                raise ValueError(
                    f"process id {key!r} is claimed by both "
                    f"{owners[key]!r} and {module_info.name!r}"
                )
            owners[key] = module_info.name
            content[key] = value

    return content
