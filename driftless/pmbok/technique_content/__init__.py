"""Composes technique explanation content out of per-family modules living in
this package, so ten families' worth of writing can happen in ten concurrent
pull requests without any of them touching a shared list.

A content module (a plain ``.py`` file directly inside this package, or inside
a fixture package a test points at) exports exactly two names:

``FAMILY: str``
    The ``driftless.pmbok.tt.FAMILIES`` key the module supplies content for.
``CONTENT: dict[str, TechniqueContent]``
    Explanation fields for zero or more technique keys, all of which must
    belong to ``FAMILY``.

``collect_content`` finds every such module with ``pkgutil.iter_modules`` —
never a hand-maintained import list — so adding a family's content is a
single new file here: nothing in this module or in ``definitions.py`` has to
name it. A module that claims a key outside its own family, a key
``tt.TT_CATALOG`` does not hold at all, or a key another module already
claimed, fails loudly at collection time rather than silently losing content.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from dataclasses import dataclass

from driftless.pmbok.tt import FAMILIES, TT_CATALOG


@dataclass(frozen=True)
class TechniqueContent:
    """One technique's explanation fields. Everything about a technique that
    is not an explanation — key, display name, family, source — stays in
    ``driftless.pmbok.definitions.TechniqueDefinition``."""

    summary: str = ""
    when_to_use: str = ""
    when_to_avoid: str = ""
    steps: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    pitfalls: tuple[str, ...] = ()
    worked_example: str = ""
    further_reading: tuple[str, ...] = ()


def collect_content(
    *,
    package_name: str = __name__,
    package_path: Iterable[str] = __path__,
) -> dict[str, TechniqueContent]:
    """Import every submodule of the given package (this package, by
    default) and merge their ``CONTENT`` dicts, keyed by technique key.

    ``package_name``/``package_path`` are only ever overridden by tests, which
    point this at a fixture package to prove the discovery mechanism itself —
    real callers take the defaults and get this package's own modules.
    """
    content: dict[str, TechniqueContent] = {}
    owners: dict[str, str] = {}
    for module_info in pkgutil.iter_modules(package_path, package_name + "."):
        module = importlib.import_module(module_info.name)

        family = getattr(module, "FAMILY", None)
        if not isinstance(family, str):
            raise TypeError(f"{module_info.name} must define FAMILY: str")
        if family not in FAMILIES:
            raise ValueError(
                f"{module_info.name} FAMILY {family!r} is not one of tt.FAMILIES's keys"
            )
        family_keys = FAMILIES[family]

        module_content = getattr(module, "CONTENT", None)
        if not isinstance(module_content, dict):
            raise TypeError(f"{module_info.name} must define CONTENT: dict[str, TechniqueContent]")

        for key, value in module_content.items():
            if not isinstance(key, str):
                raise TypeError(f"{module_info.name} CONTENT has a non-string key {key!r}")
            if not isinstance(value, TechniqueContent):
                raise TypeError(f"{module_info.name} CONTENT[{key!r}] must be a TechniqueContent")
            if key not in TT_CATALOG:
                raise ValueError(f"{module_info.name} claims unknown technique key {key!r}")
            if key not in family_keys:
                raise ValueError(
                    f"{module_info.name} declares FAMILY {family!r} but claims {key!r}, "
                    "which belongs to a different family"
                )
            if key in owners:
                raise ValueError(
                    f"technique key {key!r} is claimed by both "
                    f"{owners[key]!r} and {module_info.name!r}"
                )
            owners[key] = module_info.name
            content[key] = value

    return content
