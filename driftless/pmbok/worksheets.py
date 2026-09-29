"""Printable-worksheet registry: discovers sibling ``worksheets_*.py``
modules (each exporting ``ENTRIES: tuple[Worksheet, ...]``) in this package
via ``pkgutil.iter_modules``, the discipline ``technique_content`` already
holds — no hand-maintained list, and a key ``tt.TT_CATALOG`` does not hold, or
one another module already claimed, fails loudly at discovery time.

``ARTIFACT_TEMPLATES`` is a SECOND registry on the same discipline, over sibling
``templates_*.py`` modules: separate because a ``Worksheet.key`` is a technique key
and a ``Template.key`` is an artifact kind, which one registry could not both check."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.tt import TT_CATALOG


@dataclass(frozen=True)
class WorksheetSection:
    """A heading and its prompts: a checkbox (``kind="check"``) or a
    ``<textarea>`` (``kind="text"``), never mixed within one section."""

    heading: str
    prompts: tuple[str, ...]
    kind: Literal["check", "text"]


@dataclass(frozen=True)
class Worksheet:
    """One printable worksheet. ``key`` is a real technique key."""

    key: str
    title: str
    purpose: str
    sections: tuple[WorksheetSection, ...]
    outputs: tuple[str, ...]


def _discover(
    *, package_name: str = "driftless.pmbok", package_path: Iterable[str] | None = None
) -> dict[str, Worksheet]:
    """Imports every ``worksheets_*.py`` module in ``package_path`` and
    merges their ``ENTRIES``. Overridden only by tests."""
    if package_path is None:
        package_path = importlib.import_module(package_name).__path__
    entries: dict[str, Worksheet] = {}
    owners: dict[str, str] = {}
    modules = sorted(pkgutil.iter_modules(package_path, package_name + "."), key=lambda m: m.name)
    for module_info in modules:
        if not module_info.name.rsplit(".", 1)[-1].startswith("worksheets_"):
            continue
        module = importlib.import_module(module_info.name)
        module_entries = getattr(module, "ENTRIES", None)
        if not isinstance(module_entries, tuple):
            raise TypeError(f"{module_info.name} must define ENTRIES: tuple[Worksheet, ...]")
        for worksheet in module_entries:
            if not isinstance(worksheet, Worksheet):
                raise TypeError(f"{module_info.name} ENTRIES must hold only Worksheet instances")
            if worksheet.key not in TT_CATALOG:
                raise ValueError(
                    f"{module_info.name} claims unknown technique key {worksheet.key!r}"
                )
            if worksheet.key in owners:
                raise ValueError(
                    f"worksheet key {worksheet.key!r} is claimed by both "
                    f"{owners[worksheet.key]!r} and {module_info.name!r}"
                )
            owners[worksheet.key] = module_info.name
            entries[worksheet.key] = worksheet

    return entries


WORKSHEETS: Mapping[str, Worksheet] = _discover()


@dataclass(frozen=True)
class TemplateField:
    """One blank: what goes on the line, and a line saying what belongs there."""

    label: str
    guidance: str


@dataclass(frozen=True)
class TemplateSection:
    """A heading and the blanks filled in under it."""

    heading: str
    fields: tuple[TemplateField, ...]


@dataclass(frozen=True)
class Template:
    """One artifact kind's printable skeleton. ``filled_from`` names the record a
    filled-in copy is read back from; empty for a kind the store does not track."""

    key: str
    sections: tuple[TemplateSection, ...]
    filled_from: str = ""


def _discover_templates(
    *, package_name: str = "driftless.pmbok", package_path: Iterable[str] | None = None
) -> dict[str, Template]:
    """:func:`_discover`'s rule over the artifact vocabulary: every ``templates_*.py``
    module's ``ENTRIES``, merged. An unknown or twice-claimed kind fails at import."""
    if package_path is None:
        package_path = importlib.import_module(package_name).__path__
    entries: dict[str, Template] = {}
    owners: dict[str, str] = {}
    modules = sorted(pkgutil.iter_modules(package_path, package_name + "."), key=lambda m: m.name)
    for info in modules:
        if not info.name.rsplit(".", 1)[-1].startswith("templates_"):
            continue
        module_entries = getattr(importlib.import_module(info.name), "ENTRIES", None)
        if not isinstance(module_entries, tuple):
            raise TypeError(f"{info.name} must define ENTRIES: tuple[Template, ...]")
        for template in module_entries:
            if not isinstance(template, Template):
                raise TypeError(f"{info.name} ENTRIES must hold only Template instances")
            if template.key not in ARTIFACT_KINDS:
                raise ValueError(f"{info.name} claims unknown artifact kind {template.key!r}")
            if template.key in owners:
                raise ValueError(
                    f"artifact template {template.key!r} is claimed by both "
                    f"{owners[template.key]!r} and {info.name!r}"
                )
            owners[template.key] = info.name
            entries[template.key] = template
    return entries


ARTIFACT_TEMPLATES: Mapping[str, Template] = _discover_templates()
