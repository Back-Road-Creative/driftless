"""The PR-7 documents: Department (business-scoped), Assessment and Process Map.

Each renders from the live store and the as-of date and regenerates
byte-identically. The Department report proves the org models finally drive a
document; the Assessment and Process Map surface the assessment engine and the
process-state engine as prose.
"""

import re
from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import state
from driftless.report import engine
from driftless.report.documents import assessment, department, process_map

AS_OF = date(2026, 3, 31)

_ROW = re.compile(
    r"^\| (?P<id>[\d.]+) \| (?P<name>[^|]+?) \| (?P<group>\w+) \| (?P<area>\w+) \| (?P<state>\w+) \|$",
    re.M,
)


def _rendered_rows(text: str) -> list[tuple[str, str, str, str, str]]:
    """The grid read back off the rendered document, one tuple per table row."""
    return [(r["id"], r["name"], r["group"], r["area"], r["state"]) for r in _ROW.finditer(text)]


@pytest.fixture
def project(db: Session) -> m.Project:
    """A project owned by a department, with a person and an overspend to assess."""
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    dept = m.Department(business=business, name="Delivery")
    dept.people.append(m.Person(name="Sam", role="editor", cost_rate=90.0))
    project = m.Project(
        name="GMS", portfolio=portfolio, delivery_mode="predictive", responsible_department=dept
    )
    stream = m.Workstream(name="Post", project=project)
    task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(
        baseline=baseline,
        task=task,
        planned_cost=1000.0,
        planned_start=date(2026, 1, 1),
        planned_finish=AS_OF,
    )
    db.add(line)
    db.add(
        m.CostEntry(project=project, category="labour", incurred_on=date(2026, 1, 1), amount=800.0)
    )
    db.commit()
    return project


def test_department_report_rolls_projects_up_by_department(db: Session, project: m.Project) -> None:
    # a second department with its own project: each project may appear under the
    # department accountable for it and nowhere else
    rival_dept = m.Department(business=project.responsible_department.business, name="Rival Ops")
    db.add(
        m.Project(
            name="RivalProj",
            portfolio=project.portfolio,
            delivery_mode="predictive",
            responsible_department=rival_dept,
        )
    )
    db.commit()
    text = department.render(db, AS_OF)
    assert "# Department Report" in text
    assert "Delivery" in text and "Rival Ops" in text
    assert "Headcount" in text and "1" in text
    assert text.count("GMS") == 1, "a project appears only under its own department"
    assert text.count("RivalProj") == 1, "a project appears only under its own department"
    assert text.index("GMS") < text.index("Rival Ops") < text.index("RivalProj")
    assert department.render(db, AS_OF) == text  # byte-identical


def test_assessment_report_covers_every_knowledge_area(db: Session, project: m.Project) -> None:
    text = assessment.render(db, project, AS_OF)
    assert "Assessment Report — GMS" in text
    for kind in ("cost", "schedule", "integration", "risk"):
        assert kind in text
    assert "cost" in text.lower()
    assert "reference only" in text  # no technique has a launchable assistant yet
    assert assessment.render(db, project, AS_OF) == text  # byte-identical


def test_process_map_lists_all_49_with_completeness(db: Session, project: m.Project) -> None:
    """Every printed figure is compared to the engine's own answer rather than to a
    literal, so the document's own wiring is what is under test: a dropped ``* 100``,
    a renamed template variable (Jinja renders an undefined name as empty, it does not
    raise) or a spurious ``n/a`` fallback all have to fail here."""
    expected = [
        (process.id, process.name, process.group.value, process.area.value, process_state.value)
        for process, process_state in state.project_process_states(project, db, AS_OF)
    ]
    completeness = state.completeness(project, db, AS_OF)
    assert len(expected) == 49 and len({row[-1] for row in expected}) > 1, (
        "the fixture must cover the whole grid and make the states disagree — otherwise "
        "one flat state, or a short grid, would pass"
    )
    assert completeness is not None and 0.0 < completeness < 1.0, (
        "the fixture must leave real work part-done — otherwise 0%, or a blank, would pass"
    )
    text = process_map.render(db, project, AS_OF)
    assert "# Process Map — GMS" in text
    assert f"**Completeness:** {completeness * 100:.0f}%" in text
    assert _rendered_rows(text) == expected
    assert process_map.render(db, project, AS_OF) == text  # byte-identical


def test_the_new_documents_are_discovered_by_the_engine() -> None:
    slugs = {doc.SLUG for doc in engine.iter_documents()}
    assert {"department", "assessment", "process-map"} <= slugs
