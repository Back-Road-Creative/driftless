"""Contract tests for the department web surface: ``GET /org/departments`` (list)
and ``GET /org/departments/{id}`` (drill). Both call the SAME
``department_rows`` the Department report document renders from, so a figure
on screen and the same figure in the generated document cannot disagree
(agreement test). Per-person capacity rows on the drill page reuse the
resource evaluator's remaining-hours definition rather than inventing a
second one.

The statement-ceiling tests below guard the same two routes against the
Project -> Baseline -> Line -> Task and per-person N+1 cascades that
``tests/test_perf_n1.py`` guards on the dashboard: with the model
relationships left at the default ``lazy="select"``, ``department_rows``
walks each department's projects and each project's baseline hierarchy with
one round trip per row, and the drill page's per-person capacity rows cost
one ``Task`` select per person shown. The ceilings sit just above a
batched/eager-loaded implementation and well below the pre-fix count, using
the same ``before_cursor_execute`` idiom."""

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import TypeVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.report.documents import department
from driftless.report.documents.department import department_rows
from driftless.web import create_departments_router

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 1)

# The HTML surface lives under /org, not on the bare entity path: the API
# module registers the Department CRUD at GET /departments before mount_web
# includes this router, and FastAPI matches in registration order.
_LIST = "/org/departments"

_T = TypeVar("_T")

# A store large enough for a per-row N+1 to dominate but small enough to stay
# fast: 8 departments x 6 projects each (with a baseline of 2 lines apiece),
# and 4 people in the drilled department. 6 projects/department (48 total)
# so a per-project cost-entry query — flat in ``department_rows``'s own
# department/line counts but linear in project count — blows the list ceiling
# on its own; 8 departments (up from 3) so the DRILL page's cheapest defect —
# rebuilding the whole org's ``department_rows`` to show one department — costs
# a statement count that scales with departments the page never renders and
# lands far above the drill ceiling, instead of hiding a statement below it
# the way it did at 3 departments (23 measured vs a 24 ceiling).
_N_DEPT = 8
_N_PROJ_PER_DEPT = 6
_N_LINES_PER_PROJ = 2
_N_PEOPLE_DRILLED = 4

# Ceilings the lazy code blows past and a batched/eager implementation clears.
# Both figures below were re-measured on this seed rather than carried forward,
# and each records what its page costs today AND what the regression it names
# costs — the discipline ``tests/test_perf_n1.py`` states, so the next reader
# re-derives nothing. Headroom follows that file's rule: about one statement per
# unit the call walks, and never as much as the cheapest defect the ceiling
# names, because a ceiling above its own defect cannot fail and a test that
# cannot fail is decoration.
#
# List page (measures 51 at 8 departments x 6 projects). Deleting
# ``adapters.eager_project()`` from ``department_rows``'s project query — "the
# baseline hierarchy loading lazily again" — costs 51 -> 211; swapping the
# batched ``gather.project_costs`` for a per-project
# ``adapters.project_snapshot`` costs 51 -> 147. Both are priced across all
# _N_DEPT x _N_PROJ_PER_DEPT = 48 projects, so measured + 6 sits well below
# the cheaper of them and still absorbs honest drift.
#
# Drill page (measures 18 — was 53 while it rebuilt the whole org's
# ``department_rows`` to render ONE department, the store-wide read a 24
# ceiling could not catch at 3 departments, where the same walk cost 23).
# Scoped, its cost is flat in _N_DEPT; every defect it names is dearer:
# replacing the batched ``person_task_loads`` with one ``person_task_load``
# per person shown costs 18 -> 21 (_N_PEOPLE_DRILLED = 4); un-batching the
# department's cost read into one query per project costs 18 -> 23; and the
# org-wide walk costs 53, scaling with departments the page never renders. The
# seven department operations collections ``_operations_rows`` reads (services,
# work requests, recurring work, service levels, controls, incidents,
# improvements) are what moved the base from 10 to 18 — one statement per
# collection, flat in how many rows each holds, since a linked service/control
# NAME is read out of a dict built from that same collection rather than
# through its own relationship (``web.departments`` module docstring).
# Re-derived at measured + 2 so the cheapest of them (21) still trips it.
_MAX_LIST_STMTS = 57  # measures 51; the cheapest regression it names costs 147
_MAX_DETAIL_STMTS = 20  # measures 18; the cheapest defect it names costs 21


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """A session on a throwaway SQLite *file*: an in-memory URL would give each
    connection its own empty database."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(create_departments_router(AS_OF))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as test_client:
        yield test_client


def _one_department(
    db: Session, portfolio: m.Portfolio, dept_name: str, person_name: str, project_name: str
) -> m.Department:
    """One department with one person owning one project (a baseline line, an open
    20-hour task assigned to the person, and a cost entry), so the project row and
    the per-person capacity row both have something real to show."""
    dept = m.Department(business=portfolio.business, name=dept_name)
    person = m.Person(name=person_name, role="editor", cost_rate=90.0, capacity_hours=40.0)
    dept.people.append(person)
    project = m.Project(
        name=project_name,
        portfolio=portfolio,
        delivery_mode="predictive",
        responsible_department=dept,
    )
    stream = m.Workstream(name=f"{project_name} WS", project=project)
    task = m.Task(
        name="Grade",
        workstream=stream,
        estimate_unit="hours",
        estimate=20.0,
        status="in_progress",
        percent_complete=20,
        assignee=person,
    )
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    db.add(line)
    db.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    return dept


def _seed(db: Session) -> m.Department:
    """TWO departments, each with its own person and project — so a drill page
    that reads beyond its own department (a dropped scope clause, a roster or
    project list off the whole org) fails loudly on the second department's
    rows instead of passing against a store with nothing to bleed."""
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    dept = _one_department(db, portfolio, "Delivery", "Sam", "GMS")
    _one_department(db, portfolio, "Ops", "Casey", "HMD")
    db.commit()
    return dept


def test_the_list_page_agrees_with_the_department_report(client: TestClient, db: Session) -> None:
    _seed(db)
    row = department_rows(db, AS_OF)[0]
    page = client.get(_LIST)
    doc = department.render(db, AS_OF)

    assert page.status_code == 200, page.text
    for value in (row["name"], row["business"], str(row["headcount"]), row["capacity_hours"]):
        assert value in page.text, f"{value!r} missing from {_LIST}"
        assert value in doc, f"{value!r} missing from the department report doc"


def test_the_list_page_ends_with_a_totals_row_summed_from_the_same_rows(
    client: TestClient, db: Session
) -> None:
    """The list's last row totals headcount and weekly capacity across every
    department, summed in code from the SAME rows the table shows — never a
    second query the report could disagree with."""
    _seed(db)
    rows = department_rows(db, AS_OF)
    headcount = sum(row["headcount"] for row in rows)
    capacity = sum(row["capacity_hours_value"] for row in rows)
    page = client.get(_LIST)

    assert page.status_code == 200, page.text
    foot = page.text.split("<tfoot", 1)
    assert len(foot) == 2, "the department list has no totals row"
    assert f"{len(rows)} departments" in foot[1]
    assert f"<td>{headcount}</td>" in foot[1]
    assert f"<td>{capacity:,.0f}</td>" in foot[1]


def test_the_list_page_links_each_department_to_its_drill_page(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    assert f'href="{_LIST}/{dept.id}"' in client.get(_LIST).text


def test_the_drill_page_shows_projects_and_per_person_capacity_rows(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    row = department_rows(db, AS_OF)[0]
    page = client.get(f"{_LIST}/{dept.id}")
    doc = department.render(db, AS_OF)

    assert page.status_code == 200, page.text
    # The project row's figures agree with the same document's figures — no
    # second maths path for budget/actual/CPI.
    project_row = row["projects"][0]
    for value in (project_row["name"], project_row["budget"], project_row["actual"]):
        assert value in page.text
        assert value in doc
    # The per-person row asserted as the RENDERED row, not bare substrings:
    # "40" also appears in the header ("Capacity: 40 hrs/wk"), so a People
    # table of zeros used to pass. Capacity from Person; the open-task count
    # and remaining hours from the resource evaluator's own definition (one
    # open, hour-estimated task of 20 estimated hours, assigned to Sam).
    assert '<tr class="person"><td>Sam</td><td>40</td><td>1</td><td>20</td></tr>' in page.text
    # And ONLY this department's rows: the seeded second department's person
    # and project must not bleed into this drill.
    assert page.text.count('<tr class="person">') == 1
    assert "Casey" not in page.text, "another department's person leaked into the roster"
    assert "HMD" not in page.text, "another department's project leaked into the table"


def test_the_drill_page_shows_and_follows_a_linked_artifact(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    db.add(
        m.ArtifactLink(
            record_kind="department",
            record_id=str(dept.id),
            uri=_LIST,  # a page this same test client can actually follow
            title="Handbook",
            actor="sam",
            as_of=AS_OF,
        )
    )
    db.commit()

    page = client.get(f"{_LIST}/{dept.id}")
    assert page.status_code == 200, page.text
    assert f'<a href="{_LIST}">' in page.text

    followed = client.get(_LIST)  # the web test actually follows the rendered href
    assert followed.status_code == 200


def test_the_drill_page_shows_a_note(client: TestClient, db: Session) -> None:
    dept = _seed(db)
    db.add(
        m.Note(
            record_kind="department",
            record_id=str(dept.id),
            body="Handbook is out of date.",
            actor="sam",
            as_of=AS_OF,
        )
    )
    db.commit()

    page = client.get(f"{_LIST}/{dept.id}")
    assert page.status_code == 200, page.text
    assert "Handbook is out of date." in page.text


def test_an_unknown_department_id_is_404(client: TestClient) -> None:
    assert client.get(f"{_LIST}/999").status_code == 404


def test_a_pinned_as_of_renders_byte_identically(client: TestClient, db: Session) -> None:
    dept = _seed(db)
    assert client.get(_LIST).text == client.get(_LIST).text
    first = client.get(f"{_LIST}/{dept.id}").text
    second = client.get(f"{_LIST}/{dept.id}").text
    assert first == second


def test_the_department_pages_are_reachable_on_the_real_app(db: Session) -> None:
    """The nav link resolves to the rendered HTML page on the app the server
    actually runs — not to the JSON CRUD sharing the same path prefix.

    A bare ``status_code == 200`` cannot tell a page from a JSON list, which is
    how this surface shipped shadowed by ``GET /departments``: assert the
    content type and a marker from the seeded row instead.
    """
    dept = _seed(db)
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as client:
            page = client.get("/")
            assert page.status_code == 200, page.text
            assert f'href="{_LIST}"' in page.text
            for path in (_LIST, f"{_LIST}/{dept.id}"):
                got = client.get(path)
                assert got.status_code == 200, got.text
                assert got.headers["content-type"].startswith("text/html"), (
                    f"{path} served {got.headers['content-type']} — a CRUD route is shadowing it"
                )
                assert "Delivery" in got.text, path
    finally:
        real_app.dependency_overrides.clear()


@pytest.fixture
def n1_store(tmp_path: Path) -> Iterator[tuple[Engine, sessionmaker[Session], list[int]]]:
    """``_N_DEPT`` departments each owning ``_N_PROJ_PER_DEPT`` projects with a
    baseline of ``_N_LINES_PER_PROJ`` lines, so ``department_rows`` walks the
    Project -> Baseline -> Line -> Task hierarchy on real rows rather than
    empty collections. The first department carries ``_N_PEOPLE_DRILLED``
    people (the rest one each) so drilling into it exercises the per-person
    task-load read at a headcount that would show an N+1 as a stmt-count
    blowout. A file-backed SQLite (not ``sqlite://``): the statement-ceiling
    tests hit the store through ``TestClient``, which runs each request in a
    worker thread, and an in-memory URL gives every thread its own empty db.
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'n1_departments.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        business = m.Business(name="BRC")
        portfolio = m.Portfolio(name="Content Brands", business=business)
        for d in range(_N_DEPT):
            dept = m.Department(business=business, name=f"Dept {d:02d}")
            db.add(dept)
            people = [
                m.Person(
                    name=f"Person {d}.{p}", department=dept, cost_rate=90.0, capacity_hours=40.0
                )
                for p in range(_N_PEOPLE_DRILLED if d == 0 else 1)
            ]
            db.add_all(people)
            for j in range(_N_PROJ_PER_DEPT):
                project = m.Project(
                    name=f"Project {d}.{j}",
                    portfolio=portfolio,
                    delivery_mode="predictive",
                    responsible_department=dept,
                )
                stream = m.Workstream(name=f"WS{d}.{j}", project=project)
                baseline = m.Baseline(project=project, version=1, status="approved")
                for line_i in range(_N_LINES_PER_PROJ):
                    task = m.Task(
                        name=f"T{d}.{j}.{line_i}",
                        workstream=stream,
                        estimate_unit="hours",
                        estimate=10.0,
                        status="in_progress",
                        percent_complete=20,
                        assignee=people[line_i % len(people)],
                    )
                    db.add(
                        m.BaselineLine(
                            baseline=baseline,
                            task=task,
                            planned_start=JAN,
                            planned_finish=AS_OF,
                            planned_cost=1000.0,
                        )
                    )
                db.add(
                    m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=300.0)
                )
        db.commit()
        dept_ids = list(db.scalars(select(m.Department.id).order_by(m.Department.name)))
    yield engine, factory, dept_ids


def _cold_client(factory: sessionmaker[Session]) -> TestClient:
    """A ``TestClient`` whose ``get_session`` override mints a fresh session
    per request from ``factory`` — like the real ``get_session`` — so a
    statement count reflects one cold page load, not whatever a shared
    session already cached from an earlier call."""
    app = FastAPI()
    app.include_router(create_departments_router(AS_OF))

    def cold_session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = cold_session
    return TestClient(app)


def _count_statements(engine: Engine, call: Callable[[], _T]) -> tuple[_T, int]:
    """Run ``call``, counting SQL statements executed on ``engine`` meanwhile —
    the ``before_cursor_execute`` idiom from ``tests/test_perf_n1.py``."""
    counter = {"n": 0}

    def _bump(*_: object) -> None:
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _bump)
    try:
        result = call()
    finally:
        event.remove(engine, "before_cursor_execute", _bump)
    return result, counter["n"]


def test_the_list_page_stays_under_the_statement_ceiling(
    n1_store: tuple[Engine, sessionmaker[Session], list[int]],
) -> None:
    """``GET /departments`` renders every department's row from
    ``department_rows``, which — for each department — selects its projects
    and, per project, reads ``adapters.project_snapshot``'s baseline -> lines
    -> task walk. Left lazy, that walk costs one statement per baseline line
    across the whole store; batched/eager-loaded, it costs a fixed handful of
    statements per department regardless of project or line count."""
    engine, factory, _ = n1_store
    client = _cold_client(factory)
    response, stmts = _count_statements(engine, lambda: client.get(_LIST))
    assert response.status_code == 200, response.text
    assert stmts <= _MAX_LIST_STMTS, (
        f"{_LIST} ran {stmts} statements (ceiling {_MAX_LIST_STMTS}): "
        "the department -> project -> baseline -> line -> task walk is loading lazily again"
    )


def test_the_drill_page_stays_under_the_statement_ceiling(
    n1_store: tuple[Engine, sessionmaker[Session], list[int]],
) -> None:
    """``GET /org/departments/{id}`` computes its OWN department's row and reads
    every shown person's task load — scoped and batched, a fixed handful of
    statements however many departments or people the org holds. The ceiling
    trips on every defect priced above it: the org-wide ``department_rows``
    walk it used to run, a per-person task-load read, or a per-project cost
    read."""
    engine, factory, dept_ids = n1_store
    client = _cold_client(factory)
    response, stmts = _count_statements(engine, lambda: client.get(f"{_LIST}/{dept_ids[0]}"))
    assert response.status_code == 200, response.text
    assert stmts <= _MAX_DETAIL_STMTS, (
        f"{_LIST}/{{id}} ran {stmts} statements (ceiling {_MAX_DETAIL_STMTS}): "
        "the drill is reading beyond its own department again, or un-batching "
        "a per-person or per-project read"
    )
