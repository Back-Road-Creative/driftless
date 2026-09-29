"""End to end: every knowledge area and control, walked in predictive, agile and
hybrid projects — plus one department, walked through its own operations records.

One project per ``(KnowledgeArea, delivery_mode)`` pair, seeded through the public
surfaces only (the API resource registry over ``TestClient`` and the wizard's own
``produce`` — never ``session.add``): file the area's producible inputs in lifecycle
order, run the assistant page(s) its techniques route to, record one ``TechniqueRun``
where a page offers to run one, and — for the two areas that own the project's
``Baseline`` row (Scope, Schedule) — raise and approve a ``ChangeRequest`` through the
one boundary that produces a new version.

Every process in the area is then read back three ways that must agree: the
computed state (``pmbok.state``), the process-map drill page
(``/pmbok/{id}?project=``) and the business-wide rollup cell
(``pmbok.rollup.business_process_cells``) — one state rule, seen from three
surfaces. The Process Map and Assessment report documents must show the identical
figures. A produce-category process must read PRODUCED or SIGNED_OFF; a
derived-category one has no producer of its own, so its derivation — whatever the
store actually computes — is what the drill page must show honestly, never forced.

Every area has at least one producible process (verified once, up front): none of
the 49 catalog processes is a bare reference step, so the "derived" branch below is
exercised but "reference" is dead code kept for honesty should a future catalog
change add one — ``pytest.fail`` rather than a silent pass if it ever does.
"""

from __future__ import annotations

import csv
import io
import itertools
import re
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess import engine as assess_engine
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import ChangeRequest, Project
from driftless.pmbok import catalog, mapping
from driftless.pmbok import rollup as pmbok_rollup
from driftless.pmbok import state as st
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup
from driftless.pmbok.provenance import MethodContext
from driftless.report.documents import department as department_report
from driftless.report.engine import render_document
from driftless.services.technique_runs import record_run
from driftless.services.wizard_writes import produce, producible_kinds, seed_fields
from tests.test_api_export import _importer

LATE = date(2026, 3, 31)
EARLY = LATE - timedelta(days=30)
DAY_BEFORE_LATE = LATE - timedelta(days=1)

_GROUP_ORDER = (
    ProcessGroup.INITIATING,
    ProcessGroup.PLANNING,
    ProcessGroup.EXECUTING,
    ProcessGroup.MONITORING,
    ProcessGroup.CLOSING,
)

#: The two areas whose baseline-owning process resolves through the shared
#: ``Baseline`` table (``pmbok.mapping._scope_baseline`` / ``_schedule_baseline``)
#: — the only areas the ChangeRequest -> Baseline boundary applies to.
_BASELINE_OWNING_AREAS: dict[KnowledgeArea, str] = {
    KnowledgeArea.SCOPE: "5.4",
    KnowledgeArea.SCHEDULE: "6.5",
}

#: The wizard producers that write rows one of ``bin/driftless-import.py``'s four CSV
#: kinds can also create — the only areas an export/import round trip applies to.
_CSV_ROUND_TRIP: dict[KnowledgeArea, tuple[str, str]] = {
    KnowledgeArea.RISK: ("risks", "/risks"),
    KnowledgeArea.SCHEDULE: ("milestones", "/milestones"),
}

#: Producible kinds ``pmbok.mapping`` resolves with no date filter at all -- present
#: forever once a row exists, by design (a risk, a stakeholder, a milestone/schedule,
#: a budget line, an agreement are current-state rows, not dated events). Never a
#: candidate for the as-of-diff anchor below.
_UNDATED_KINDS = frozenset(
    {
        "risk_register",
        "stakeholder_register",
        "cost_baseline",
        "milestone_list",
        "project_schedule",
        "agreements",
    }
)

_METHOD_FOR_MODE: dict[str, MethodContext] = {
    "predictive": MethodContext.PREDICTIVE,
    "agile": MethodContext.SCRUM,
    "hybrid": MethodContext.PREDICTIVE,
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A throwaway SQLite file, shared by the HTTP client and every direct read
    this test makes -- both hit the same session, the way ``tests/test_demo_web.py``
    already wires it."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        real_app.dependency_overrides[get_session] = lambda: db
        try:
            with TestClient(real_app) as test_client:
                test_client.db = db
                yield test_client
        finally:
            real_app.dependency_overrides.clear()


def _db(client: TestClient) -> Session:
    return client.db  # type: ignore[no-any-return]


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, f"{path} {body}: {response.text}"
    return int(response.json()["id"])


def _patch(client: TestClient, path: str, **body: Any) -> None:
    response = client.patch(path, json=body)
    assert response.status_code == 200, f"{path} {body}: {response.text}"


def _category(process: Process, producible: frozenset[str]) -> tuple[str, tuple[str, ...]]:
    """``("produce" | "derived" | "reference", required_tracked_kinds)``."""
    required = tuple(
        kind
        for kind in process.outputs
        if mapping.is_tracked(kind) and kind not in process.optional_outputs
    )
    if not required:
        return "reference", required
    if set(required) <= producible:
        return "produce", required
    return "derived", required


def test_every_area_has_at_least_one_producible_process() -> None:
    """Sanity the walk below relies on: a "reference" category never fires today,
    so it stays covered by construction rather than skipped silently."""
    producible = frozenset(producible_kinds())
    for area in KnowledgeArea:
        categories = {_category(process, producible)[0] for process in catalog.by_area(area)}
        assert "produce" in categories, f"{area.value}: no process the wizard can produce"


def _seed_project(client: TestClient, area: KnowledgeArea, mode: str) -> int:
    business = _create(client, "/businesses", name=f"E2E {area.value} {mode}")
    portfolio = _create(client, "/portfolios", name="E2E Portfolio", business_id=business)
    return _create(
        client, "/projects", name=f"{area.value}-{mode}", portfolio_id=portfolio, delivery_mode=mode
    )


def _raise_and_approve_change(
    client: TestClient, db: Session, project: Project, area: KnowledgeArea
) -> None:
    """Raise a ``ChangeRequest`` and approve it through the one boundary that
    produces a new ``Baseline`` version: a draft baseline with a line, approved by
    PATCH (writes to an approved baseline are refused), then the change request
    linked to it -- the check constraint requires both set together."""
    db.refresh(project)
    workstream = project.workstreams[0]
    task = workstream.tasks[0]
    next_version = max(b.version for b in project.baselines) + 1
    draft = _create(
        client, "/baselines", project_id=project.id, version=next_version, status="draft"
    )
    _create(
        client,
        "/baseline-lines",
        baseline_id=draft,
        task_id=task.id,
        planned_start=LATE.isoformat(),
        planned_finish=LATE.isoformat(),
        planned_cost=1500,
    )
    _patch(
        client, f"/baselines/{draft}", status="approved", approved_at=f"{LATE.isoformat()}T00:00:00"
    )
    request = _create(
        client,
        "/change-requests",
        project_id=project.id,
        description=f"Re-baseline {area.value} via the e2e walk",
        raised_on=LATE.isoformat(),
        origin_process_id=_BASELINE_OWNING_AREAS[area],
    )
    _patch(client, f"/change-requests/{request}", status="approved", resulting_baseline_id=draft)
    db.expire_all()
    row = db.get(ChangeRequest, request)
    assert row is not None and row.status == "approved" and row.resulting_baseline_id == draft, (
        f"{area.value}: the ChangeRequest -> Baseline boundary did not land"
    )


def _run_assistants_and_record_one(
    client: TestClient,
    db: Session,
    project_id: int,
    area: KnowledgeArea,
    mode: str,
    processes: tuple[Process, ...],
) -> None:
    techniques = dict.fromkeys(tt for process in processes for tt in process.tools_techniques)
    routed = sorted({ASSISTANT_ROUTES[tt] for tt in techniques if tt in ASSISTANT_ROUTES})
    for template in routed:
        page = client.get(template.format(project_id=project_id))
        assert page.status_code == 200, (
            f"{area.value}/{mode}: assistant page {template} -> {page.status_code}"
        )
    for tt in techniques:
        if tt in ASSISTANT_ROUTES:
            owning = next(p for p in processes if tt in p.tools_techniques)
            record_run(
                db,
                project_id=project_id,
                technique_key=tt,
                process_id=owning.id,
                actor="e2e",
                as_of=LATE,
                method=_METHOD_FOR_MODE[mode],
                source_version="e2e-walk",
            )
            return


def _round_trip_export(client: TestClient, area: KnowledgeArea, project_id: int) -> None:
    kind_name, resource_path = _CSV_ROUND_TRIP[area]
    exported = client.get(resource_path, params={"format": "csv"}).text
    originals = list(csv.DictReader(io.StringIO(exported)))
    ours = [row for row in originals if int(row["project_id"]) == project_id]
    assert ours, f"{area.value}: nothing to export from {resource_path}"
    rows = [{k: v for k, v in row.items() if k not in ("id", "row_revision")} for row in ours]

    def post(path: str, payload: dict[str, Any]) -> int:
        response = client.post(path, json=payload)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    landed = _importer().import_csv(post, kind_name, rows)
    assert landed[kind_name] == len(rows), f"{area.value}: the importer did not create every row"

    reexported = list(
        csv.DictReader(io.StringIO(client.get(resource_path, params={"format": "csv"}).text))
    )
    doubled = [row for row in reexported if int(row["project_id"]) == project_id]
    assert len(doubled) == 2 * len(ours), (
        f"{area.value}: the round trip did not add exactly {len(ours)} rows"
    )


def _state_on_the_page(page_text: str) -> str | None:
    match = re.search(r'reads\s*\n?\s*<span class="badge st-\w+">([^<]+)</span>', page_text)
    return match.group(1).strip().lower() if match else None


@pytest.mark.parametrize(
    ("area", "mode"),
    list(itertools.product(KnowledgeArea, ("predictive", "agile", "hybrid"))),
    ids=lambda v: v.value if isinstance(v, KnowledgeArea) else v,
)
def test_knowledge_area_walked_end_to_end(
    client: TestClient, area: KnowledgeArea, mode: str
) -> None:
    db = _db(client)
    producible = frozenset(producible_kinds())
    processes = tuple(sorted(catalog.by_area(area), key=lambda p: _GROUP_ORDER.index(p.group)))
    categorized = [(process, *_category(process, producible)) for process in processes]
    produce_processes = [
        process for process, category, _required in categorized if category == "produce"
    ]
    assert produce_processes, (
        f"{area.value}/{mode}: no producible process (see the sanity test above)"
    )
    required_of = {
        process: required for process, category, required in categorized if category == "produce"
    }
    # The last process (lifecycle order) that first introduces a kind BOTH new to this
    # walk AND read with an as-of filter -- writing IT last is what makes the as-of read
    # actually move. Some producible kinds are current-state rows with no date column at
    # all by design (a risk, a stakeholder, a milestone, a budget line, an agreement) --
    # ``mapping`` reads no field to gate them by as-of, so a process whose every required
    # kind is one of these reads identically on any two as-of dates, however late it is
    # written; picking one of those would make the assertion below fail for a reason that
    # has nothing to do with the write it is meant to prove.
    seen: set[str] = set()
    last_process: Process | None = None
    for process in produce_processes:
        new_kinds = set(required_of[process]) - seen
        if new_kinds - _UNDATED_KINDS:
            last_process = process
        seen |= set(required_of[process])
    assert last_process is not None, (
        f"{area.value}: every produce process's required kinds are as-of-insensitive by "
        "design -- no write here can move the as-of read"
    )

    project_id = _seed_project(client, area, mode)
    project = db.get(Project, project_id)
    assert project is not None

    produced: set[str] = set()
    for process, category, required in categorized:
        if category != "produce":
            continue
        as_of = LATE if process is last_process else EARLY
        for kind in required:
            if kind in produced or mapping.resolve(kind, project, db, as_of).present:
                produced.add(kind)
                continue
            produce(db, project, kind, seed_fields(kind, as_of), as_of, "e2e")
            produced.add(kind)

    _run_assistants_and_record_one(client, db, project_id, area, mode, processes)

    if area in _BASELINE_OWNING_AREAS:
        _raise_and_approve_change(client, db, project, area)

    # Three surfaces read the same state, and a derived/reference process shows an
    # honest derivation instead of a forced PRODUCED.
    with st.prefetched(db, [project]):
        cells = pmbok_rollup.business_process_cells(db, LATE)
    cell_by_id = {cell.process_id: cell for cell in cells}
    for process, category, _required in categorized:
        actual = st.process_state(process, project, db, LATE)
        page = client.get(
            f"/pmbok/{process.id}", params={"project": project_id, "as_of": LATE.isoformat()}
        )
        assert page.status_code == 200, f"{area.value}/{mode}/{process.id}: page {page.status_code}"

        our_cell = next(pc for pc in cell_by_id[process.id].projects if pc.project_id == project_id)
        assert our_cell.state == actual, (
            f"{area.value}/{mode}/{process.id}: the business rollup cell disagrees with the "
            f"process state ({our_cell.state.value} != {actual.value})"
        )

        if category == "produce":
            assert actual in (st.ProcessState.PRODUCED, st.ProcessState.SIGNED_OFF), (
                f"{area.value}/{mode}/{process.id}: expected produced/signed_off, read {actual.value}"
            )
        elif category == "derived":
            assert st.is_assessable(process), (
                f"{area.value}/{mode}/{process.id}: derived must be assessable"
            )
            shown = _state_on_the_page(page.text)
            assert shown == actual.value.replace("_", " "), (
                f"{area.value}/{mode}/{process.id}: the drill page shows {shown!r}, "
                f"not the computed derivation {actual.value!r}"
            )
        else:  # pragma: no cover — no catalog process is reference-only today
            assert "no output of this process is a kind the store tracks" in page.text, (
                f"{area.value}/{mode}/{process.id}: a reference step must say so honestly"
            )

    # The assessment computes, and the Process Map / Assessment documents show the
    # same figures the pages do.
    assessments = assess_engine.assess_project(db, project, LATE)
    assessment = next(a for a in assessments if a.kind == area.value)
    assert assessment.status in ("green", "amber", "red")
    assert assessment.coverage in ("measured", "stale", "missing", "not_applicable")

    process_map_md = render_document("process-map", db, project, LATE)
    for process, _cat, _required in categorized:
        actual = st.process_state(process, project, db, LATE)
        row = re.search(
            rf"\| {re.escape(process.id)} \|[^|]*\|[^|]*\|[^|]*\| (\w+) \|", process_map_md
        )
        assert row is not None, (
            f"{area.value}/{mode}/{process.id}: missing from the Process Map document"
        )
        assert row.group(1) == actual.value, (
            f"{area.value}/{mode}/{process.id}: Process Map says {row.group(1)}, state engine says {actual.value}"
        )

    assessment_md = render_document("assessment", db, project, LATE)
    block = re.search(rf"### {re.escape(area.value)} — (\w+) \(risk ([\d.]+)\)", assessment_md)
    assert block is not None, f"{area.value}/{mode}: missing from the Assessment document"
    assert block.group(1) == assessment.status
    assert block.group(2) == f"{assessment.risk_score:.4f}"

    if area in _CSV_ROUND_TRIP:
        _round_trip_export(client, area, project_id)

    # The as-of reading a day before the last write differs from the reading after it.
    before = st.process_state(last_process, project, db, DAY_BEFORE_LATE)
    after = st.process_state(last_process, project, db, LATE)
    assert before != after, (
        f"{area.value}/{mode}: {last_process.id} reads the same on {DAY_BEFORE_LATE} as on {LATE} "
        "-- the last write left no as-of-visible trace"
    )


def test_department_operations_and_workspace_walked_end_to_end(client: TestClient) -> None:
    """One department, seeded through the API resource registry across every
    operations table it owns, then read back on its own workspace page and in the
    Department report -- both built off ``department_report.department_rows``."""
    db = _db(client)
    business = _create(client, "/businesses", name="E2E Operations Business")
    department = _create(client, "/departments", name="Post Production", business_id=business)
    service = _create(
        client, "/department-services", department_id=department, name="Colour desk", owner="Sam"
    )
    _create(
        client,
        "/work-requests",
        department_id=department,
        service_id=service,
        requester="Ada Lovelace",
        raised_on=LATE.isoformat(),
    )
    _create(
        client,
        "/recurring-work",
        department_id=department,
        name="Weekly archive export",
        owner="Ada Lovelace",
    )
    _create(
        client,
        "/service-levels",
        department_id=department,
        service_id=service,
        measure="Turnaround hours",
        target=48,
    )
    control = _create(
        client,
        "/operating-controls",
        department_id=department,
        name="Backup verification",
        owner="Sam",
    )
    _create(
        client,
        "/incidents",
        department_id=department,
        control_id=control,
        description="Scratch drive failed mid-render",
        raised_on=LATE.isoformat(),
    )
    _create(
        client,
        "/improvements",
        department_id=department,
        what="Automate the nightly backup check",
        why="the incident above was caught by a person, not a system",
        owner="Sam",
    )

    page = client.get(f"/org/departments/{department}", params={"as_of": LATE.isoformat()})
    assert page.status_code == 200
    for expected in (
        "Colour desk",
        "Ada Lovelace",
        "Weekly archive export",
        "Turnaround hours",
        "Backup verification",
        "Scratch drive failed mid-render",
        "Automate the nightly backup check",
    ):
        assert expected in page.text, f"the department workspace lost {expected!r}"

    rows = department_report.department_rows(db, LATE)
    row = next(r for r in rows if r["name"] == "Post Production")
    rendered = department_report.render(db, LATE)
    assert "Post Production" in rendered
    assert f"| {row['name']} |" not in rendered  # no project rolled up: nothing to earn yet
    assert "_No projects assigned to this department._" in rendered
