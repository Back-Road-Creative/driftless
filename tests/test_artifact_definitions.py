"""Pins ``driftless.pmbok.artifact_content``'s composition rules and
``driftless.pmbok.artifact_definitions``'s derivation rules: a family content
module's fields reach ``ARTIFACTS``, a kind with no content module still gets
an empty-but-present ``ArtifactDefinition``, a module that claims a kind
outside its own family or outside ``ARTIFACT_KINDS`` entirely fails loudly,
duplicate claims across modules fail loudly, ``produced_by``/``read_by`` are
read off the real catalog rather than typed, and ``tracked_by`` agrees with
``mapping.is_tracked``.
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import fields
from pathlib import Path

import pytest

from driftless.pmbok.artifact_content import ArtifactContent, collect_content
from driftless.pmbok.artifact_definitions import ARTIFACTS, ArtifactDefinition, _definition
from driftless.pmbok.artifacts import FAMILIES
from driftless.pmbok.catalog import PROCESSES
from driftless.pmbok.mapping import is_tracked


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


def test_a_family_modules_content_reaches_artifacts(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_reaches_artifacts",
        {
            "plans_content": """\
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {
                    "project_charter": ArtifactContent(
                        plain_summary="Starts the project.",
                        why_it_matters="It gives someone the authority to act.",
                        what_it_looks_like_here="Generated on read.",
                    ),
                }
                """
        },
    )
    try:
        content = collect_content(package_name=name, package_path=path)
        assert content["project_charter"].plain_summary == "Starts the project."
    finally:
        _teardown_package(tmp_path, name, ["plans_content"])


def test_a_kind_absent_from_content_still_yields_an_empty_definition() -> None:
    """A kind no content module claims is still a full registry member, just
    an unexplained one."""
    absent = "a_kind_no_content_module_claims"
    assert absent not in collect_content(), "pick a key no content module claims"

    definition = _definition(absent, next(iter(FAMILIES)))
    assert definition.key == absent
    _assert_unexplained(definition)


def _assert_unexplained(definition: ArtifactDefinition) -> None:
    """Every ``ArtifactContent`` field of ``definition`` is at its empty
    default, walked off the dataclass so no second list of field names exists."""
    for field in fields(ArtifactContent):
        assert getattr(definition, field.name) == field.default, (
            f"{definition.key}.{field.name} is not empty"
        )


def test_every_family_has_a_discoverable_module_owning_only_its_own_keys() -> None:
    for family in FAMILIES:
        module = __import__(
            f"driftless.pmbok.artifact_content.{family}", fromlist=["FAMILY", "CONTENT"]
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
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {"scope_baseline": ArtifactContent(plain_summary="wrong family")}
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
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {"not_a_real_kind": ArtifactContent(plain_summary="nope")}
                """
        },
    )
    try:
        with pytest.raises(ValueError, match="unknown artifact kind"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_duplicate_keys_across_modules_raise(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_duplicate_key",
        {
            "first": """\
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {"project_charter": ArtifactContent(plain_summary="from first")}
                """,
            "second": """\
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {"project_charter": ArtifactContent(plain_summary="from second")}
                """,
        },
    )
    try:
        with pytest.raises(ValueError, match="claimed by both"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["first", "second"])


def test_adding_a_content_module_requires_touching_no_existing_file(tmp_path: Path) -> None:
    name, path = _build_package(tmp_path, "fixture_growable_package", {})
    try:
        assert collect_content(package_name=name, package_path=path) == {}

        pkg_dir = Path(path[0])
        (pkg_dir / "new_family.py").write_text(
            textwrap.dedent(
                """\
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {
                    "project_charter": ArtifactContent(plain_summary="added after the fact")
                }
                """
            )
        )
        content = collect_content(package_name=name, package_path=path)
        assert content["project_charter"].plain_summary == "added after the fact"
    finally:
        _teardown_package(tmp_path, name, ["new_family"])


def test_a_non_techniquecontent_value_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_bad_value_type",
        {
            "bad": """\
                FAMILY = "plans"
                CONTENT = {"project_charter": "not an ArtifactContent"}
                """
        },
    )
    try:
        with pytest.raises(TypeError, match="must be an ArtifactContent"):
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
        with pytest.raises(ValueError, match="is not one of artifacts.FAMILIES's keys"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_missing_content_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_missing_content",
        {"bad": 'FAMILY = "plans"\n'},
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
                from driftless.pmbok.artifact_content import ArtifactContent

                FAMILY = "plans"
                CONTENT = {1: ArtifactContent(plain_summary="bad key type")}
                """
        },
    )
    try:
        with pytest.raises(TypeError, match="non-string key"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_produced_by_and_read_by_are_read_off_the_real_catalog() -> None:
    """Not typed: for any kind, ``produced_by``/``read_by`` must be exactly
    the set of process ids that actually name it as an output/input."""
    for key, definition in sorted(ARTIFACTS.items()):
        expected_produced = tuple(p.id for p in PROCESSES if key in p.outputs)
        expected_read = tuple(p.id for p in PROCESSES if key in p.inputs)
        assert definition.produced_by == expected_produced
        assert definition.read_by == expected_read


def test_tracked_by_agrees_with_mapping_is_tracked() -> None:
    for key, definition in sorted(ARTIFACTS.items()):
        assert definition.tracked_by is is_tracked(key)
