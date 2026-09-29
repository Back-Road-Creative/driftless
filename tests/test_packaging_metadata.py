"""What ``pyproject.toml`` promises about the built distribution, checked against the repo.

Three claims that were each false while every other test stayed green:

* the coverage floor. ``--cov-fail-under=80`` against a suite that measures 99.6% is not a
  floor, it is a formality: ~950 statements could go dark — every test touching
  ``api/app.py``, ``web/pages.py`` (since split up) and ``api/secure.py`` deleted landed at
  82%, still green.
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
* the Python floor. ``requires-python = ">=3.12"`` had no ceiling, so the package promised
  3.13, 3.14 and every release after it though no CI job here has ever run a line of it on
  any of them. The declared range is checked against every ``python-version:`` CI actually
  pins, so an interpreter nothing tests can't sit inside the promise.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
ENTRYPOINT = ROOT / "deploy" / "entrypoint.sh"
CI_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "pip-audit.yml",
)

# The driver half of a SQLAlchemy URL: `postgresql+psycopg://` -> `psycopg`.
DRIVER = re.compile(r"\b[a-z0-9]+\+([a-z0-9_]+)://")
# The coarse guard on the pinned value: tightening the floor toward the measurement never
# trips it, dropping it back to a number that no longer describes the suite does. No measured
# figures are restated here — they rot. The suite grew ~2.4x since the last set was written
# in, and a reader trusting them read a gate with one statement of slack as a roomy one. Take
# the current numbers from the run's own TOTAL line.
MINIMUM_FLOOR = 99.0


def canonical(name: str) -> str:
    """PEP 503 normalisation of a requirement specifier: `psycopg[binary]>=3.1` -> `psycopg`."""
    return re.sub(r"[-_.]+", "-", re.split(r"[\[<>=!~;\s]", name, maxsplit=1)[0]).lower()


def test_every_importable_subpackage_is_one_the_wheel_ships() -> None:
    """``packages`` is hand-listed, so a new subpackage is shipped only if someone says so.

    Nothing else notices when they don't. An omitted subpackage builds a wheel that imports
    fine from a checkout and dies on the installed copy — and only at the moment a module
    already in the wheel imports the missing one, which is a container that will not start
    rather than a test that goes red. ``driftless.services`` was added and left off this
    list; the failure surfaced in the sample-report stage, after a full suite and an
    install, reading ``No module named 'driftless.services'``.

    Checked both directions: an unlisted package is unshipped, and a listed one that no
    longer exists is a stale promise. The list stays explicit — the point is that adding a
    directory under ``driftless/`` is a packaging decision, not that it is automatic.
    """
    on_disk = {
        ".".join(init.relative_to(ROOT).parent.parts)
        for init in (ROOT / "driftless").rglob("__init__.py")
    }
    declared = set(PYPROJECT["tool"]["setuptools"]["packages"])
    assert declared == on_disk, (
        f"unshipped: {sorted(on_disk - declared)}; listed but gone: {sorted(declared - on_disk)}"
    )


def test_the_coverage_floor_describes_the_suite_it_guards() -> None:
    addopts = PYPROJECT["tool"]["pytest"]["ini_options"]["addopts"]
    found = re.search(r"--cov-fail-under[= ]([\d.]+)", addopts)
    assert found, f"addopts is {addopts!r} — nothing fails the run on a coverage drop at all"
    floor = float(found.group(1))
    assert floor >= MINIMUM_FLOOR, (
        f"--cov-fail-under={floor:g} is below {MINIMUM_FLOOR:g}, which leaves whole "
        "swathes of the suite free to go dark with CI still green. Pin the floor just "
        "under the total the run actually reports; if that total genuinely fell, the "
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


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _parse_bounds(specifier: str) -> tuple[tuple[int, ...], tuple[int, ...] | None]:
    """A minimal ``>=X.Y,<X.Y``-style reader — no dependency on the ``packaging`` package,
    which is only ever present here as a transitive lock entry, not something
    ``[project]``/``[project.optional-dependencies]`` declares."""
    floor: tuple[int, ...] | None = None
    ceiling: tuple[int, ...] | None = None
    for clause in specifier.split(","):
        clause = clause.strip()
        if clause.startswith(">="):
            floor = _version_tuple(clause.removeprefix(">="))
        elif clause.startswith("<"):
            ceiling = _version_tuple(clause.removeprefix("<"))
    assert floor is not None, f"requires-python={specifier!r} declares no floor at all"
    return floor, ceiling


def _ci_python_versions() -> set[str]:
    found: set[str] = set()
    pattern = re.compile(r"^\s*python-version:\s*'([\d.]+)'\s*$")
    for workflow in CI_WORKFLOWS:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if match := pattern.match(line):
                found.add(match.group(1))
    return found


def test_requires_python_is_bounded_to_what_ci_actually_runs() -> None:
    """``requires-python`` is a promise about which interpreters this package supports. Left
    unbounded (``>=3.12``), it promised 3.13, 3.14 and every release after it, though no CI
    job in ``.github/workflows/`` has ever run a line of driftless on any of them — every one
    of them pins ``python-version: '3.12'``. The declared range must have a ceiling, and every
    version CI pins must land inside it."""
    declared = PYPROJECT["project"]["requires-python"]
    floor, ceiling = _parse_bounds(declared)
    assert ceiling is not None, (
        f"requires-python={declared!r} has no upper bound — it promises every future Python "
        "release though nothing in .github/workflows/ has tested any of them"
    )
    tested = _ci_python_versions()
    assert tested, "no `python-version:` line found under .github/workflows/ — nothing to check"
    for version in sorted(tested):
        parts = _version_tuple(version)
        assert floor <= parts < ceiling, (
            f"CI pins python-version: {version!r}, which requires-python={declared!r} does not "
            "cover"
        )


LOCK = ROOT / "requirements.lock"


def _locked_version(name: str) -> str:
    pattern = re.compile(rf"^{re.escape(name)}==([\d.]+)", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(LOCK.read_text(encoding="utf-8"))
    assert match, f"{LOCK.name} pins no version of {name}"
    return match.group(1)


def test_sqlalchemy_is_bounded_to_the_line_the_lock_proves() -> None:
    """``sqlalchemy>=2.0`` promised every future SQLAlchemy line while the lock — the only
    version set the Tests, Migrations and audit jobs ever run — sat on 2.0.x. On 2026-09-24
    SQLAlchemy 2.1.0 reached PyPI, the one CI job that installs without the lock (the strict
    mypy check) resolved it, and staging went red on annotations that 2.0 had inferred. The
    declared range must have a ceiling, and the locked version must sit inside it, so a new
    major line arrives here by a deliberate lock bump rather than by a release date."""
    specs = {canonical(spec): spec for spec in PYPROJECT["project"]["dependencies"]}
    declared = specs["sqlalchemy"]
    floor, ceiling = _parse_bounds(declared.removeprefix("sqlalchemy"))
    assert ceiling is not None, (
        f"{declared!r} has no upper bound — it promises every future SQLAlchemy line though "
        f"{LOCK.name} has only ever proved one of them"
    )
    locked = _version_tuple(_locked_version("sqlalchemy"))
    assert floor <= locked < ceiling, (
        f"{LOCK.name} pins sqlalchemy=={'.'.join(map(str, locked))}, which {declared!r} does "
        "not cover — the lock and the declared range name different version sets"
    )
