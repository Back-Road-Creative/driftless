"""Composes artifact-kind explanation content out of per-family modules living
in this package, so eight families' worth of writing can happen in eight
concurrent pull requests without any of them touching a shared list.

A content module (a plain ``.py`` file directly inside this package, or inside
a fixture package a test points at) exports exactly two names:

``FAMILY: str``
    The ``driftless.pmbok.artifacts.FAMILIES`` key the module supplies content for.
``CONTENT: dict[str, ArtifactContent]``
    Explanation fields for zero or more artifact kinds, all of which must
    belong to ``FAMILY``.

``collect_content`` finds every such module with ``pkgutil.iter_modules`` —
never a hand-maintained import list — so adding a family's content is a
single new file here: nothing in this module or in ``artifact_definitions.py``
has to name it. A module that claims a kind outside its own family, a kind
``artifacts.ARTIFACT_KINDS`` does not hold at all, or a kind another module
already claimed, fails loudly at collection time rather than silently losing
content.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from dataclasses import dataclass

from driftless.pmbok.artifacts import ARTIFACT_KINDS, FAMILIES


@dataclass(frozen=True)
class ArtifactContent:
    """One artifact kind's plain-language explanation fields. Everything about
    a kind that is not an explanation — key, display name, family, who
    produces/reads/tracks it — stays in
    ``driftless.pmbok.artifact_definitions.ArtifactDefinition``."""

    plain_summary: str = ""
    why_it_matters: str = ""
    what_it_looks_like_here: str = ""


def collect_content(
    *,
    package_name: str = __name__,
    package_path: Iterable[str] = __path__,
) -> dict[str, ArtifactContent]:
    """Import every submodule of the given package (this package, by
    default) and merge their ``CONTENT`` dicts, keyed by artifact kind.

    ``package_name``/``package_path`` are only ever overridden by tests, which
    point this at a fixture package to prove the discovery mechanism itself —
    real callers take the defaults and get this package's own modules.
    """
    content: dict[str, ArtifactContent] = {}
    owners: dict[str, str] = {}
    for module_info in pkgutil.iter_modules(package_path, package_name + "."):
        module = importlib.import_module(module_info.name)

        family = getattr(module, "FAMILY", None)
        if not isinstance(family, str):
            raise TypeError(f"{module_info.name} must define FAMILY: str")
        if family not in FAMILIES:
            raise ValueError(
                f"{module_info.name} FAMILY {family!r} is not one of artifacts.FAMILIES's keys"
            )
        family_keys = FAMILIES[family]

        module_content = getattr(module, "CONTENT", None)
        if not isinstance(module_content, dict):
            raise TypeError(f"{module_info.name} must define CONTENT: dict[str, ArtifactContent]")

        for key, value in module_content.items():
            if not isinstance(key, str):
                raise TypeError(f"{module_info.name} CONTENT has a non-string key {key!r}")
            if not isinstance(value, ArtifactContent):
                raise TypeError(f"{module_info.name} CONTENT[{key!r}] must be an ArtifactContent")
            if key not in ARTIFACT_KINDS:
                raise ValueError(f"{module_info.name} claims unknown artifact kind {key!r}")
            if key not in family_keys:
                raise ValueError(
                    f"{module_info.name} declares FAMILY {family!r} but claims {key!r}, "
                    "which belongs to a different family"
                )
            if key in owners:
                raise ValueError(
                    f"artifact kind {key!r} is claimed by both "
                    f"{owners[key]!r} and {module_info.name!r}"
                )
            owners[key] = module_info.name
            content[key] = value

    return content
