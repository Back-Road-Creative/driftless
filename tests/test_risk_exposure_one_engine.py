"""Exposure, contingency held and top risk come from ONE engine. Two guards, not
redundant: the agreement test pins that the surfaces match TODAY, the structural
tests that they cannot stop matching, only one implementation existing to differ."""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
from typing import NamedTuple

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import exposure
from driftless.assess.evaluators import risk as risk_evaluator
from driftless.db import Base, new_engine, new_session_factory
from driftless.report import render_document

SERVICE = Path(__file__).resolve().parents[1]
PACKAGE = SERVICE / "driftless"
ENGINE = PACKAGE / "assess" / "exposure.py"
CALC = PACKAGE / "calc" / "forecast.py"
SURFACES = (
    PACKAGE / "report" / "documents" / "forecast.py",
    PACKAGE / "assess" / "evaluators" / "risk.py",
)
JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)

# Hand-computed below: 0.5 x 1,000 for the OPEN risk, no `contingency` line, top by name.
EXPECTED = (500.0, 0.0, "open-vendor-slip")


class Figures(NamedTuple):
    """The three figures every surface prints, parsed back off that surface."""

    exposure: float
    contingency: float
    top_risk: str


@pytest.fixture
def session() -> Session:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    return new_session_factory(engine)()


@pytest.fixture
def project(session: Session) -> m.Project:
    """BAC 10,000 over Jan-Mar, 2,000 spent, one open risk and one closed one."""
    portfolio = m.Portfolio(name="PF", business=m.Business(name="BRC"))
    proj = m.Project(name="Repro", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="WS", project=proj)
    task = m.Task(name="T", workstream=stream, estimate_unit="hours", percent_complete=50)
    session.add(
        m.BaselineLine(
            baseline=m.Baseline(project=proj, version=1, status="approved"),
            task=task,
            planned_start=JAN,
            planned_finish=AS_OF,
            planned_cost=10_000.0,
        )
    )
    session.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=2_000.0))
    for description, status in (("open-vendor-slip", "open"), ("closed-weather", "closed")):
        session.add(
            m.Risk(
                project=proj,
                description=description,
                probability=0.5,
                impact=1_000.0,
                status=status,
            )
        )
    session.commit()
    return proj


def _document_figures(session: Session, project: m.Project) -> Figures:
    """The Forecast Report's Contingency table, read back out of the Markdown."""
    doc = render_document("forecast", session, project, AS_OF)
    values = dict(re.findall(r"\| (Risk exposure|Contingency held) \| ([\d.]+) \|", doc))
    top = re.search(r"^Top risk: (.+)\.$", doc, re.M)
    assert top is not None, f"the document names no top risk:\n{doc}"
    return Figures(float(values["Risk exposure"]), float(values["Contingency held"]), top.group(1))


def _evaluator_figures(session: Session, project: m.Project) -> Figures:
    """The evaluator's threat string — what board, Assessment Report and RAG render."""
    threats = risk_evaluator.evaluate(session, project, AS_OF).threats
    assert threats, "the seeded exposure is uncovered, so a threat must be raised"
    found = re.fullmatch(
        r"Open-risk exposure ([\d,]+) against contingency ([\d,]+) \(top risk: (.+)\)\.",
        threats[0].description,
    )
    assert found is not None, f"unparsable threat: {threats[0].description!r}"
    numbers = [float(found.group(i).replace(",", "")) for i in (1, 2)]
    return Figures(numbers[0], numbers[1], found.group(3))


def test_every_surface_prints_the_same_exposure_contingency_and_top_risk(
    session: Session, project: m.Project
) -> None:
    """One store, one as-of: every surface equal, and equal to the hand-computed figures."""
    document, evaluator = _document_figures(session, project), _evaluator_figures(session, project)
    assert document == Figures(*EXPECTED), f"the Forecast Report disagrees: {document}"
    assert evaluator == Figures(*EXPECTED), f"the risk evaluator disagrees: {evaluator}"
    assert document == evaluator
    doc = render_document("forecast", session, project, AS_OF)
    assert "closed-weather" not in doc
    assert "| Remaining budget | 8000.00 |" in doc  # the figure beside them must not move


@pytest.mark.parametrize(
    ("pattern", "allowed", "complaint"),
    (
        (
            "assess_contingency",
            (ENGINE, CALC),
            "build their own contingency assessment; shared MATHS was never a shared "
            "engine — each caller fed it a different register and rate",
        ),
        (
            r'category\s*==\s*"contingency"',
            (ENGINE,),
            "read the contingency budget line themselves; whoever reads the reserve "
            "decides what 'contingency held' means, and exactly one module may",
        ),
    ),
    ids=("primitive", "budget-line"),
)
def test_only_the_engine_derives_the_figures(
    pattern: str, allowed: tuple[Path, ...], complaint: str
) -> None:
    """One derivation in the package: a surface that re-derived would trip one of these."""
    found = re.compile(pattern)
    assert found.search(ENGINE.read_text(encoding="utf-8")), f"{pattern} no longer describes a read"
    culprits = sorted(
        str(path.relative_to(SERVICE))
        for path in PACKAGE.rglob("*.py")
        if path not in allowed and found.search(path.read_text(encoding="utf-8"))
    )
    assert not culprits, (
        f"{culprits} {complaint}. Import driftless.assess.exposure.contingency_assessment instead."
    )


def _register_builds(source: str) -> int:
    """How many times ``source`` builds a ``driftless.calc.forecast.Risk`` — i.e. decides
    for itself which stored rows ARE the open register, and what each one is called.

    Import-form aware on purpose. The pattern tests above cannot see a second register:
    ``adapters.open_risk_register`` lived for a release naming risks by primary key while
    the engine named them by description, and it tripped neither, because it never called
    ``assess_contingency`` nor read the contingency budget line — it only built the list.
    Building that list is the tell, so every way of reaching the class counts: the module
    (``forecast.Risk(...)``), an alias for it (``fc.Risk(...)``), and the class imported
    directly (``Risk(...)``), which no plain-text search for "forecast.Risk" would catch.
    """
    tree = ast.parse(source)
    modules: set[str] = set()  # names bound to the forecast MODULE
    classes: set[str] = set()  # names bound to the Risk CLASS itself
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "driftless.calc":
            modules |= {a.asname or a.name for a in node.names if a.name == "forecast"}
        elif isinstance(node, ast.ImportFrom) and node.module == "driftless.calc.forecast":
            classes |= {a.asname or a.name for a in node.names if a.name == "Risk"}
        elif isinstance(node, ast.Import):
            modules |= {
                a.asname
                for a in node.names
                if a.name == "driftless.calc.forecast" and a.asname is not None
            }
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "Risk"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in modules
            )
            or (isinstance(node.func, ast.Name) and node.func.id in classes)
        )
    )


#: Every import form a reintroduced register could use. The detector must see all three,
#: so a blind detector fails loudly here instead of passing the package check vacuously.
DECOYS = (
    "from driftless.calc import forecast\nforecast.Risk('a', 0.5, 1.0)\n",
    "from driftless.calc import forecast as fc\nfc.Risk('b', 0.5, 1.0)\n",
    "from driftless.calc.forecast import Risk\nRisk('c', 0.5, 1.0)\n",
    "import driftless.calc.forecast as f\nf.Risk('d', 0.5, 1.0)\n",
)


def test_only_the_engine_decides_which_rows_are_the_open_register() -> None:
    """One module turns stored Risk rows into the register every surface then weighs.

    The exact set is ``exposure.py`` — no site legitimately differs, because a second
    builder is exactly the bug: it re-picks the rows AND re-picks the name, so the
    Forecast Report and the threat board can name different top risks off one store.
    """
    for decoy in DECOYS:  # anti-vacuity: prove the detector can see, before trusting a 0
        assert _register_builds(decoy) == 1, f"the detector is blind to this form:\n{decoy}"
    builders = {
        path: _register_builds(path.read_text(encoding="utf-8")) for path in PACKAGE.rglob("*.py")
    }
    assert builders.get(ENGINE), (  # anti-vacuity against the real tree, not a fixture
        f"{ENGINE.relative_to(SERVICE)} no longer builds the register; this guard is "
        "pinning an empty set and would pass however many rival registers existed"
    )
    culprits = sorted(str(p.relative_to(SERVICE)) for p, n in builders.items() if n and p != ENGINE)
    assert not culprits, (
        f"{culprits} build a second open-risk register. Whoever picks the rows also picks "
        "what each risk is CALLED, so a rival builder makes surfaces name different top "
        "risks off one store. Call driftless.assess.exposure.open_register instead."
    )


@pytest.mark.parametrize("surface", SURFACES, ids=lambda p: p.name)
def test_each_surface_imports_the_engine_by_name(surface: Path) -> None:
    """A named import at each call site makes an engine rename an ImportError, not a fork."""
    imported = {
        alias.name
        for node in ast.walk(ast.parse(surface.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module == "driftless.assess.exposure"
        for alias in node.names
    }
    assert "contingency_assessment" in imported, (
        f"{surface.relative_to(SERVICE)} does not import the engine's entry point; it is "
        "deriving exposure/contingency/top-risk itself"
    )
    for name in imported:
        assert hasattr(exposure, name), f"{surface.relative_to(SERVICE)} imports a stale {name}"
