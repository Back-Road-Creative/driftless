"""What ``pyproject.toml`` promises about the built distribution, checked against the repo.

Three claims that were each false while every other test stayed green:

* the coverage floor. ``--cov-fail-under=80`` against a suite that measures 99.6% is not a
  floor, it is a formality: ~950 statements could go dark — every test touching
  ``api/app.py``, ``web/pages.py`` and ``api/secure.py`` deleted lands at 82%, still green.
  The floor is pinned just under the measured total instead, so a whole module losing its
  tests is what CI is looking for rather than what it tolerates.
* the type marker. ``[tool.mypy] strict = true`` types this package to the letter, and then
  the wheel shipped no ``py.typed``, so PEP 561 tells a downstream importer to ignore every
  annotation in it. The marker is a file, and a file only reaches the wheel if
  ``package-data`` names it — both halves are asserted, because either alone ships nothing.
* the database driver. ``deploy/entrypoint.sh`` builds a ``postgresql+psycopg://`` URL, while
  ``psycopg`` was declared only in the ``[dev]`` extra — so an install of the runtime set
  produced a container that could not reach its own database. The driver is read out of the
  shipped entrypoint rather than named here, so adding a second backend cannot forget this.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
ENTRYPOINT = ROOT / "deploy" / "entrypoint.sh"

# The driver half of a SQLAlchemy URL: `postgresql+psycopg://` -> `psycopg`.
DRIVER = re.compile(r"\b[a-z0-9]+\+([a-z0-9_]+)://")
# The measured total is 99.64% (1164 tests, 4935 statements, 18 missed). This is the coarse
# guard on the pinned value: tightening the floor toward the measurement never trips it,
# dropping it back to a number that no longer describes the suite does.
MINIMUM_FLOOR = 99.0


def canonical(name: str) -> str:
    """PEP 503 normalisation of a requirement specifier: `psycopg[binary]>=3.1` -> `psycopg`."""
    return re.sub(r"[-_.]+", "-", re.split(r"[\[<>=!~;\s]", name, maxsplit=1)[0]).lower()


def test_the_coverage_floor_describes_the_suite_it_guards() -> None:
    addopts = PYPROJECT["tool"]["pytest"]["ini_options"]["addopts"]
    found = re.search(r"--cov-fail-under[= ]([\d.]+)", addopts)
    assert found, f"addopts is {addopts!r} — nothing fails the run on a coverage drop at all"
    floor = float(found.group(1))
    assert floor >= MINIMUM_FLOOR, (
        f"--cov-fail-under={floor:g} against a suite that measures 99.64% leaves "
        f"{(99.64 - floor) / 100 * 4935:.0f} statements free to go dark with CI still green. "
        "Pin the floor just under the measured total; if the total genuinely fell, the "
        "tests that stopped covering it are the thing to restore."
    )


def test_the_package_ships_the_marker_that_makes_its_types_visible() -> None:
    marker = ROOT / "driftless" / "py.typed"
    assert marker.exists(), (
        "driftless/py.typed is missing, so PEP 561 makes a downstream importer of the wheel "
        "treat this strictly-typed package as untyped and every annotation in it is discarded"
    )
    shipped = PYPROJECT["tool"]["setuptools"]["package-data"].get("driftless", [])
    assert any(re.fullmatch(pattern.replace("*", ".*"), "py.typed") for pattern in shipped), (
        f"[tool.setuptools.package-data] gives driftless {shipped}, which does not include "
        "py.typed: the marker sits in the checkout and never reaches the built distribution, "
        "which is the only place it means anything"
    )


def test_every_driver_the_deployment_names_is_a_runtime_dependency() -> None:
    """The extra is optional by definition; what the entrypoint requires is not optional."""
    drivers = {match.group(1) for match in DRIVER.finditer(ENTRYPOINT.read_text(encoding="utf-8"))}
    assert drivers, f"no `dialect+driver://` URL was parsed out of {ENTRYPOINT.name}"
    runtime = {canonical(spec) for spec in PYPROJECT["project"]["dependencies"]}
    missing = sorted(driver for driver in drivers if canonical(driver) not in runtime)
    assert not missing, (
        f"{ENTRYPOINT.name} builds a URL for {missing}, which [project.dependencies] does not "
        "declare — so `pip install .` ships a container that raises NoSuchModuleError on its "
        "first query. A driver the deployment cannot start without is not an optional extra."
    )
