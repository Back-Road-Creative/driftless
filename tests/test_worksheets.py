"""Pins ``worksheets``: discovery finds a sibling module unmodified, a
duplicate key fails loudly, every real key names a real technique."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
from driftless.pmbok.tt import FAMILIES, TT_CATALOG
from driftless.pmbok.worksheets import WORKSHEETS, Worksheet, WorksheetSection, _discover

_WS = 'from driftless.pmbok.worksheets import Worksheet\nENTRIES = (Worksheet(key={key!r}, title={title!r}, purpose="", sections=(), outputs=()),)\n'


def test_a_sibling_module_is_discovered_and_a_duplicate_key_raises(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "fixture_worksheets"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "worksheets_fixture.py").write_text(_WS.format(key="meetings", title="Fixture"))
    (pkg_dir / "not_worksheets_module.py").write_text(
        "ENTRIES = ('ignored: no worksheets_ prefix',)"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        entries = _discover(package_name="fixture_worksheets", package_path=[str(pkg_dir)])
        assert set(entries) == {"meetings"}
        assert entries["meetings"].title == "Fixture"

        (pkg_dir / "worksheets_second.py").write_text(_WS.format(key="meetings", title="B"))
        importlib.invalidate_caches()
        with pytest.raises(ValueError, match="claimed by both"):
            _discover(package_name="fixture_worksheets", package_path=[str(pkg_dir)])
    finally:
        sys.path.remove(str(tmp_path))
        for mod in ["worksheets_fixture", "not_worksheets_module", "worksheets_second"]:
            sys.modules.pop(f"fixture_worksheets.{mod}", None)
        sys.modules.pop("fixture_worksheets", None)


def test_the_real_registry_holds_only_real_technique_keys_with_full_shapes() -> None:
    assert WORKSHEETS
    unknown = sorted(set(WORKSHEETS) - TT_CATALOG)
    assert not unknown, f"WORKSHEETS holds keys outside TT_CATALOG: {unknown}"
    sheet = WORKSHEETS["rolling_wave_planning"]
    assert isinstance(sheet, Worksheet)
    assert sheet.title and sheet.purpose and sheet.sections and sheet.outputs
    for section in sheet.sections:
        assert isinstance(section, WorksheetSection)
        assert section.kind in ("check", "text")
        assert section.prompts


#: The families this change covers. The catalogue-wide form of the check below
#: -- ``set(WORKSHEETS) >= set(GUIDE_ONLY_REASONS)``, every guide-only technique
#: carrying a worksheet -- is the last step of the series and would fail today on
#: the schedule, quality and resource slices, which other changes own. It is
#: deliberately not written yet rather than written and weakened.
COVERED_FAMILIES = ("general", "procurement", "risk", "stakeholder")


def test_every_guide_only_technique_in_the_covered_families_has_a_worksheet() -> None:
    """Totality over the families this change covers, derived from the registries
    rather than a typed key list, so a technique added to one of them later is
    required to carry a worksheet without anyone editing this test."""
    wanted = set().union(*(FAMILIES[family] for family in COVERED_FAMILIES)) & set(
        GUIDE_ONLY_REASONS
    )
    assert wanted, "the derivation yielded nothing, so the check below would pass vacuously"
    missing = sorted(wanted - set(WORKSHEETS))
    assert not missing, f"guide-only techniques with no worksheet: {missing}"


def test_every_guide_only_procurement_technique_has_a_worksheet() -> None:
    """The procurement family's slice, kept as its own named check now that the
    covered set has grown past it, so a regression there names itself."""
    wanted = FAMILIES["procurement"] & set(GUIDE_ONLY_REASONS)
    missing = sorted(wanted - set(WORKSHEETS))
    assert not missing, f"guide-only procurement techniques with no worksheet: {missing}"


def test_every_general_family_guide_only_technique_has_a_worksheet() -> None:
    """The general family's slice, kept as its own named check now that the
    covered set has grown past it, so a regression there names itself."""
    wanted = FAMILIES["general"] & set(GUIDE_ONLY_REASONS)
    missing = sorted(wanted - set(WORKSHEETS))
    assert not missing, f"guide-only general techniques with no worksheet: {missing}"


def test_every_worksheet_is_filled_in_not_a_stub() -> None:
    """Walks the whole registry, so a later family cannot land a titled shell."""
    for key, sheet in sorted(WORKSHEETS.items()):
        assert sheet.title and sheet.purpose and sheet.sections and sheet.outputs, key
        for section in sheet.sections:
            assert section.heading and section.prompts, f"{key}/{section.heading}"
            assert section.kind in ("check", "text"), key
            assert all(prompt.strip() for prompt in section.prompts), key


def test_a_worksheet_claiming_an_unknown_technique_key_raises(tmp_path: Path) -> None:
    """Discovery, not a CI-only assertion, is what rejects a typo'd key —
    the guarantee the three sibling registries already make at import."""
    pkg_dir = tmp_path / "fixture_unknown_worksheets"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "worksheets_bad.py").write_text(_WS.format(key="not_a_real_technique", title="Nope"))
    sys.path.insert(0, str(tmp_path))
    try:
        importlib.invalidate_caches()
        with pytest.raises(ValueError, match="unknown technique key"):
            _discover(package_name="fixture_unknown_worksheets", package_path=[str(pkg_dir)])
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fixture_unknown_worksheets.worksheets_bad", None)
        sys.modules.pop("fixture_unknown_worksheets", None)
