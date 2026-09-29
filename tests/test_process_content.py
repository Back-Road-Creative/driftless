"""Pins ``driftless.pmbok.process_content``'s composition rules: an area
content module's fields reach ``PROCESS_DEFINITIONS``, a process id with no
content module still gets an empty-but-present ``ProcessDefinition``, a
module that claims an id outside its own area or outside
``catalog.PROCESSES`` entirely fails loudly, duplicate claims across modules
fail loudly, and — the point of this whole package — a brand-new content
module needs no existing file touched to be picked up.

Mirrors ``tests/test_technique_content.py`` over processes/areas instead of
techniques/families.
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import fields
from pathlib import Path

import pytest

from driftless.pmbok import catalog
from driftless.pmbok.process_content import ProcessContent, collect_content
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS


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


def test_an_area_modules_content_reaches_process_definitions(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_reaches_process_definitions",
        {
            "integration_content": """\
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {
                    "4.1": ProcessContent(
                        plain_summary="Get sign-off that the project exists.",
                        why_bother="Otherwise nobody has agreed the project is real.",
                        done_when="A sponsor has signed a charter.",
                        first_time_tip="Keep it to a single page.",
                    ),
                }
                """
        },
    )
    try:
        content = collect_content(package_name=name, package_path=path)
        assert content["4.1"].plain_summary == "Get sign-off that the project exists."
        assert content["4.1"].done_when == "A sponsor has signed a charter."
    finally:
        _teardown_package(tmp_path, name, ["integration_content"])


def test_a_process_id_absent_from_content_still_yields_an_empty_definition() -> None:
    """A process id no content module claims is still a full registry member,
    just an unexplained one.

    Every catalog process now carries content, so ``PROCESS_DEFINITIONS`` holds
    no example to look up directly; instead every id the real ``collect_content``
    does NOT claim (there are none today) is checked the same way, which is a
    no-op while the catalog is fully explained and turns into a real assertion
    the moment a process is added ahead of its content.
    """
    absent = "not-a-real-process-id"
    assert absent not in collect_content(), "pick an id no content module claims"

    for process_id in sorted({p.id for p in catalog.PROCESSES} - set(collect_content())):
        _assert_unexplained(PROCESS_DEFINITIONS[process_id])


def _assert_unexplained(definition: object) -> None:
    """Every ``ProcessContent`` field of ``definition`` is at its empty
    default, walked off the dataclass so no second list of field names
    exists."""
    for field in fields(ProcessContent):
        assert getattr(definition, field.name) == field.default, (
            f"{definition!r}.{field.name} is not empty"
        )


def test_every_area_has_a_discoverable_module_owning_only_its_own_ids() -> None:
    """Each knowledge area ships a module discovery can find, declaring that
    area and claiming nothing outside it.

    This deliberately says nothing about how *much* content a module carries.
    The point of this package is that an area's explanations arrive without
    any existing file being touched, so an assertion that content is still
    empty would have to be edited by all ten area pull requests at once —
    turning the property into its own violation.
    """
    ids_by_area: dict[str, set[str]] = {}
    for process in catalog.PROCESSES:
        ids_by_area.setdefault(process.area.value, set()).add(process.id)

    for area in ids_by_area:
        module = __import__(f"driftless.pmbok.process_content.{area}", fromlist=["AREA", "CONTENT"])
        assert module.AREA == area
        assert set(module.CONTENT) <= ids_by_area[area], (
            f"{area} module claims ids outside its own area"
        )


def test_a_module_claiming_a_foreign_id_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_foreign_id",
        {
            "bad": """\
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {"5.1": ProcessContent(plain_summary="wrong area")}
                """
        },
    )
    try:
        with pytest.raises(ValueError, match="is not a process in that area"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_claiming_an_unknown_id_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_unknown_id",
        {
            "bad": """\
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {"99.9": ProcessContent(plain_summary="nope")}
                """
        },
    )
    try:
        with pytest.raises(ValueError, match="is not a process in that area"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_duplicate_ids_across_modules_raise(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_duplicate_id",
        {
            "first": """\
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {"4.1": ProcessContent(plain_summary="from first")}
                """,
            "second": """\
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {"4.1": ProcessContent(plain_summary="from second")}
                """,
        },
    )
    try:
        with pytest.raises(ValueError, match="claimed by both"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["first", "second"])


def test_adding_a_content_module_requires_touching_no_existing_file(tmp_path: Path) -> None:
    """The whole point of ``process_content``: a brand-new module, written to
    a package this test builds from scratch, is picked up by
    ``collect_content`` without editing that package's ``__init__.py`` or any
    other module in it."""
    name, path = _build_package(tmp_path, "fixture_growable_package", {})
    try:
        assert collect_content(package_name=name, package_path=path) == {}

        pkg_dir = Path(path[0])
        (pkg_dir / "new_area.py").write_text(
            textwrap.dedent(
                """\
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {"4.1": ProcessContent(plain_summary="added after the fact")}
                """
            )
        )
        content = collect_content(package_name=name, package_path=path)
        assert content["4.1"].plain_summary == "added after the fact"
    finally:
        _teardown_package(tmp_path, name, ["new_area"])


def test_a_non_processcontent_value_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_bad_value_type",
        {
            "bad": """\
                AREA = "integration"
                CONTENT = {"4.1": "not a ProcessContent"}
                """
        },
    )
    try:
        with pytest.raises(TypeError, match="must be a ProcessContent"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_missing_area_or_content_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_missing_area",
        {"bad": "CONTENT = {}\n"},
    )
    try:
        with pytest.raises(TypeError, match="must define AREA"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_with_an_unknown_area_name_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_unknown_area",
        {"bad": 'AREA = "not_a_real_area"\nCONTENT = {}\n'},
    )
    try:
        with pytest.raises(ValueError, match="is not one of KnowledgeArea's values"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])


def test_a_module_missing_content_raises(tmp_path: Path) -> None:
    name, path = _build_package(
        tmp_path,
        "fixture_missing_content",
        {"bad": 'AREA = "integration"\n'},
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
                from driftless.pmbok.process_content import ProcessContent

                AREA = "integration"
                CONTENT = {1: ProcessContent(plain_summary="bad key type")}
                """
        },
    )
    try:
        with pytest.raises(TypeError, match="non-string key"):
            collect_content(package_name=name, package_path=path)
    finally:
        _teardown_package(tmp_path, name, ["bad"])
