"""Pins ``driftless.pmbok.technique_content``'s composition rules: a family
content module's fields reach ``TECHNIQUES``, a key with no content module
still gets an empty-but-present ``TechniqueDefinition``, a module that claims
a key outside its own family or outside ``TT_CATALOG`` entirely fails loudly,
duplicate claims across modules fail loudly, and — the point of this whole
package — a brand-new content module needs no existing file touched to be
picked up.
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import fields
from pathlib import Path

import pytest

from driftless.pmbok.definitions import TECHNIQUES, TechniqueDefinition, _definition
from driftless.pmbok.technique_content import TechniqueContent, collect_content
from driftless.pmbok.tt import FAMILIES, TT_CATALOG


def _build_package(tmp_path: Path, name: str, modules: dict[str, str]) -> tuple[str, list[str]]:
    """Builds a throwaway package on disk with a unique name, so a test can
    exercise ``collect_content``'s real discovery mechanism
    (``pkgutil.iter_modules`` over a package's ``__path__``) against modules
    that do not exist anywhere in the checkout. Pair with ``_teardown_package``."""
    pkg_dir = tmp_path / name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    for modname, source in modules.items():
        (pkg_dir / f"{modname}.py").write_text(textwrap.dedent(source))
    sys.path.insert(0, str(tmp_path))
    return name, [str(pkg_dir)]


def _teardown_package(tmp_path: Path, name: str, modnames: list[str]) -> None:
    sys.path.remove(str(tmp_path))
    for modname in modnames:
        sys.modules.pop(f"{name}.{modname}", None)
    sys.modules.pop(name, None)


def test_a_family_modules_content_reaches_techniques(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_reaches_techniques",
        {
            "general_content": """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {
                    "meetings": TechniqueContent(
                        summary="Structured touchpoints for decisions and status.",
                        steps=("Set an agenda.", "Capture decisions."),
                        pitfalls=("No agenda, no decisions.",),
                    ),
                }
                """
        },
    )
    try:
        content = collect_content(package_name=name, package_path=path)
        assert content["meetings"].summary == "Structured touchpoints for decisions and status."
        assert content["meetings"].steps == ("Set an agenda.", "Capture decisions.")
    finally:
        _teardown_package(tmp_path, name, ["general_content"])


def test_a_key_absent_from_content_still_yields_an_empty_definition() -> None:
    """A technique no content module claims is still a full registry member,
    just an unexplained one.

    Every catalog member now carries content, so ``TECHNIQUES`` holds no example
    to look up and this used to skip — leaving ``definitions._EMPTY_CONTENT`` and
    the ``_CONTENT.get(key, _EMPTY_CONTENT)`` fallback that returns it exercised
    by nothing at all. The skip reason claimed the fixture tests covered it; they
    cover ``collect_content``'s discovery and never build a definition. So the
    fallback is called directly here, with a key no content module claims, and
    *every* explanation field is required empty — read off the dataclass rather
    than named, so a field added to ``TechniqueContent`` is covered the moment it
    exists.

    Any catalog member that is genuinely uncovered is checked the same way below,
    which is a no-op while the catalog is fully explained and turns back into a
    real assertion the moment a technique is added ahead of its content.
    """
    absent = "a_technique_no_content_module_claims"
    assert absent not in collect_content(), "pick a key no content module claims"

    definition = _definition(absent, next(iter(FAMILIES)))
    assert definition.key == absent
    _assert_unexplained(definition)

    for key in sorted(TT_CATALOG - set(collect_content())):
        _assert_unexplained(TECHNIQUES[key])


def _assert_unexplained(definition: TechniqueDefinition) -> None:
    """Every ``TechniqueContent`` field of ``definition`` is at its empty
    default, walked off the dataclass so no second list of field names exists."""
    for field in fields(TechniqueContent):
        assert getattr(definition, field.name) == field.default, (
            f"{definition.key}.{field.name} is not empty"
        )


def test_every_family_has_a_discoverable_module_owning_only_its_own_keys() -> None:
    """Each family ships a module discovery can find, declaring that family and
    claiming nothing outside it.

    This deliberately says nothing about how *much* content a module carries.
    The point of this package is that a family's explanations arrive without any
    existing file being touched, so an assertion that content is still empty
    would have to be edited by all ten family pull requests at once — turning the
    property into its own violation.
    """
    for family in FAMILIES:
        module = __import__(
            f"driftless.pmbok.technique_content.{family}", fromlist=["FAMILY", "CONTENT"]
        )
        assert module.FAMILY == family
        assert set(module.CONTENT) <= FAMILIES[family], (
            f"{family} module claims keys outside its own family"
        )


def test_a_module_claiming_a_foreign_key_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_foreign_key",
        {
            "bad": """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {"decomposition": TechniqueContent(summary="wrong family")}
                """
        },
    )
    try:
        with pytest.raises(ValueError, match="belongs to a different family"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_claiming_an_unknown_key_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_unknown_key",
        {
            "bad": """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {"not_a_real_technique": TechniqueContent(summary="nope")}
                """
        },
    )
    try:
        with pytest.raises(ValueError, match="unknown technique key"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_duplicate_keys_across_modules_raise(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_duplicate_key",
        {
            "first": """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {"meetings": TechniqueContent(summary="from first")}
                """,
            "second": """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {"meetings": TechniqueContent(summary="from second")}
                """,
        },
    )
    try:
        with pytest.raises(ValueError, match="claimed by both"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["first", "second"])


def test_adding_a_content_module_requires_touching_no_existing_file(tmp_path: Path) -> None:
    """The whole point of ``technique_content``: a brand-new module, written
    to a package this test builds from scratch, is picked up by
    ``collect_content`` without editing that package's ``__init__.py`` or any
    other module in it."""
    name, path = _build_package(tmp_path, "fixture_growable_package", {})
    try:
        assert collect_content(package_name=name, package_path=path) == {}

        pkg_dir = Path(path[0])
        (pkg_dir / "new_family.py").write_text(
            textwrap.dedent(
                """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {"meetings": TechniqueContent(summary="added after the fact")}
                """
            )
        )
        content = collect_content(package_name=name, package_path=path)
        assert content["meetings"].summary == "added after the fact"
    finally:
        _teardown_package(tmp_path, name, ["new_family"])


def test_a_non_techniquecontent_value_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_bad_value_type",
        {
            "bad": """\
                FAMILY = "general"
                CONTENT = {"meetings": "not a TechniqueContent"}
                """
        },
    )
    try:
        with pytest.raises(TypeError, match="must be a TechniqueContent"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_missing_family_or_content_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_missing_family",
        {"bad": "CONTENT = {}\n"},
    )
    try:
        with pytest.raises(TypeError, match="must define FAMILY"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_with_an_unknown_family_name_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_unknown_family",
        {"bad": 'FAMILY = "not_a_real_family"\nCONTENT = {}\n'},
    )
    try:
        with pytest.raises(ValueError, match="is not one of tt.FAMILIES's keys"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_missing_content_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_missing_content",
        {"bad": 'FAMILY = "general"\n'},
    )
    try:
        with pytest.raises(TypeError, match="must define CONTENT"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_non_string_content_key_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_non_string_key",
        {
            "bad": """\
                from driftless.pmbok.technique_content import TechniqueContent

                FAMILY = "general"
                CONTENT = {1: TechniqueContent(summary="bad key type")}
                """
        },
    )
    try:
        with pytest.raises(TypeError, match="non-string key"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])
