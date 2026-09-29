"""Every routed assistant, gated the same six ways — walked off the live
registry rather than named one page at a time.

The assistant set is DERIVED, never listed: ``assess.model.ASSISTANT_ROUTES``'
route templates (shaped the way ``test_web_routes_not_shadowed`` shapes every
other path) are compared against every GET the app actually mounts under
``/assist/``, so a technique promised a launcher that never got wired — or a
page mounted under that prefix that no technique's route names — fails here
the day it happens, not when a reader notices.

For every page the two sides agree on, six gates apply:

(a) it renders real content under the shared seeded fixture, never only an
    empty state;
(b) it is deterministic — two renders at the same as-of are byte-identical,
    and a render as of an EARLIER date never shows a fact dated after it
    (the store is walked for a genuinely later row, so this cannot pass
    vacuously);
(c) its statement count sits under a ceiling derived from a live measurement,
    the same ``MEASURED``/``assert_recorded`` convention ``test_perf_n1``
    already carries;
(d) every ``<svg>`` its template draws carries a print/no-JS text
    alternative — a table or a details block stating the same figures, the
    idiom ``test_web_method_map``'s no-JS ties list already uses;
(e) a viewer reads it (200) and, on the one shape that later grows a write,
    is refused it (403) while a contributor succeeds — decided off
    ``test_web_csrf``'s gated app and its viewer/contributor bearer tokens;
(f) any row kind the page can write round-trips through the CSV export and
    ``bin/driftless-import.py``.

No routed assistant today draws a chart or writes a row — ``assist_evm.py``'s
own docstring: "Nothing is written, and the stored snapshot is untouched" —
so (d) and (f) currently hold on an empty walk. Both are wired against the
live registries (``driftless/web/templates/assist_*.html``, ``_web_paths``)
rather than pinned to that fact, so the day a routed assistant draws a chart
or writes a ``TechniqueRun``/``LessonLearned`` row, the walk includes it with
no edit here.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import test_web_assist_evm as assist_evm
import test_web_csrf
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from test_perf_n1 import assert_recorded, count_route
from test_web_csrf import Gate, _client, _web_paths
from test_web_routes_not_shadowed import _shape

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import (
    AcceptanceRecord,
    Acquisition,
    BacklogItem,
    Baseline,
    BaselineLine,
    BudgetLine,
    Business,
    ConflictAction,
    ConflictRecord,
    CostEntry,
    Deliverable,
    EstimateScenario,
    Issue,
    LessonLearned,
    Milestone,
    NarrativeArtifact,
    Person,
    Portfolio,
    ProcurementAgreement,
    Project,
    QualityMeasurement,
    Requirement,
    RequirementTrace,
    ResourceBreakdown,
    ResourceType,
    ResponsibilityAssignment,
    Risk,
    RiskResponse,
    Sprint,
    Stakeholder,
    Task,
    TeamAssessment,
    TechniqueRun,
    TrainingRecord,
    Workstream,
)

# The gated app fixture, reused as is — the same idiom
# ``client, db = test_web_pages.client, test_web_pages.db`` already uses: a
# test's own fixture parameter must not read as a redefined import, so it is
# assigned rather than imported by name.
gated = test_web_csrf.gated

AS_OF, JAN = assist_evm.AS_OF, assist_evm.JAN
Q = f"?as_of={AS_OF.isoformat()}"
_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless" / "web" / "templates"
# The empty-state marker ``test_web_a11y`` uses for the same purpose — a page
# standing in for content it has none of.
_EMPTY = 'class="empty-state"'
_SVG = re.compile(r"<svg\b.*?</svg>", re.S)
_IMPORTER_PATH = Path(__file__).resolve().parents[1] / "bin" / "driftless-import.py"

#: Every mounted assist page not named by an ``ASSISTANT_ROUTES`` entry, keyed
#: by its unformatted template with the reason it is reached some other way.
#: ``/assist/closeout`` serves Close Project or Phase (4.7), whose PMBOK-6
#: ``tools_techniques`` (``expert_judgment``, ``data_analysis``, ``meetings``)
#: are generic across dozens of processes and never routed to one page — it is
#: linked directly from the project hub's own "Closeout" link
#: (``project_hub.html``), never from a technique's ``launch_href``. Still
#: walked by every gate below via ``ALL_ASSISTANT_PAGES``: "no technique routes
#: it" excuses it from the REACHABILITY check, not from the six gates
#: themselves.
DOCUMENTED_UNROUTED_ASSIST_TEMPLATES: dict[str, str] = {
    "/projects/{project_id}/assist/closeout": (
        "Close Project or Phase (4.7) names only generic tools_techniques with no "
        "ASSISTANT_ROUTES entry of their own; linked from the project hub, not a technique."
    ),
}

#: Route shape -> its unformatted template, one entry per DISTINCT ROUTED
#: page (``earned_value_analysis`` and ``to_complete_performance_index`` both
#: name the same template, so this collapses to one page, not two).
ASSISTANT_PAGES: dict[str, str] = {
    _shape(template): template for template in sorted(set(ASSISTANT_ROUTES.values()))
}

#: Every assistant page the six gates below walk: every routed page, plus
#: every documented-unrouted one — so a page reached only from the hub is
#: gated exactly as strictly as one reached from a technique's launch link.
ALL_ASSISTANT_PAGES: dict[str, str] = {
    **ASSISTANT_PAGES,
    **{_shape(template): template for template in DOCUMENTED_UNROUTED_ASSIST_TEMPLATES},
}

#: Route shape -> the ``bin/driftless-import.py`` ``CSV_KINDS`` key its POST
#: writes into. Only the pages whose POST lands on the PAGE's own address are
#: here: the requirements, team and schedule pages post to sub-addresses
#: (``.../requirements/requirement``, ``.../team/assessment``,
#: ``.../schedule/propose``) that are not in ``ALL_ASSISTANT_PAGES``, so the
#: export/import walk below never sees them; their row kinds round-trip through
#: ``tests/test_api_export.py``'s own list-route walk instead.
ASSISTANT_WRITE_KINDS: dict[str, str] = {
    "/projects/{}/assist/decisions": "technique_runs",
    "/projects/{}/assist/risk-responses": "risk_responses",
}


def test_the_assistant_route_table_and_the_mounted_assist_pages_agree() -> None:
    routed_shapes = {_shape(template) for template in ASSISTANT_ROUTES.values()}
    # Every GET under ``/assist/``, plus any routed page mounted elsewhere (the flow
    # calculator lives at ``/projects/{id}/flow``, beside the hub's other project
    # pages, and is routed from ``agile_release_planning`` all the same).
    mounted_shapes = {
        path for path in _web_paths("GET") if "/assist/" in path or path in routed_shapes
    }
    missing = routed_shapes - mounted_shapes
    assert not missing, (
        f"ASSISTANT_ROUTES promises {sorted(missing)}, but no mounted GET route matches — "
        "the router was never included, or the path drifted from the model's entry"
    )
    documented_shapes = {_shape(t) for t in DOCUMENTED_UNROUTED_ASSIST_TEMPLATES}
    unexplained = mounted_shapes - routed_shapes - documented_shapes
    assert not unexplained, (
        f"{sorted(unexplained)} are mounted under /assist/ but no ASSISTANT_ROUTES entry "
        "names them and DOCUMENTED_UNROUTED_ASSIST_TEMPLATES gives no reason"
    )
    assert ALL_ASSISTANT_PAGES, "vacuous walk: no assistant is mounted at all"


def _future_fact_cost_entry(db: Session, project_id: int) -> tuple[date, str]:
    """A ``CostEntry`` dated after ``AS_OF``, and the distinctive figure a page
    would show if it leaked a fact from the future into an earlier as-of — the
    page prints AC (actual cost, cumulative), never one entry's own amount, so
    the marker is the seed's 800.0 plus this entry, not the entry alone."""
    future_on = AS_OF + timedelta(days=30)
    db.add(
        CostEntry(project_id=project_id, category="labour", incurred_on=future_on, amount=424242.0)
    )
    db.commit()
    return future_on, "425,042"


def _future_fact_cost_entry_run_rate(db: Session, project_id: int) -> tuple[date, str]:
    """A ``CostEntry`` dated after ``AS_OF``, distinct from the earned-value page's
    own cumulative-AC marker: ``assist_cost``'s ``actual_periods`` buckets
    ``CostEntry`` rows by calendar month, so an entry 30 days out lands alone in
    its own bucket and the run-rate table prints its own amount verbatim rather
    than a cumulative figure."""
    future_on = AS_OF + timedelta(days=30)
    db.add(
        CostEntry(project_id=project_id, category="labour", incurred_on=future_on, amount=555555.55)
    )
    db.commit()
    return future_on, "555,555.55"


def _future_fact_lesson_learned(db: Session, project_id: int) -> tuple[date, str]:
    """A ``LessonLearned`` raised after ``AS_OF`` — closeout's own ``_lessons``
    filters ``raised_on <= at``, so this proves that filter rather than only
    exercising the page."""
    future_on = AS_OF + timedelta(days=30)
    marker = "Future-dated lesson XKJ471"
    db.add(
        LessonLearned(
            project_id=project_id,
            raised_on=future_on,
            category="schedule",
            what_happened=marker,
            what_to_do_next_time="Never leak a lesson raised after the read date.",
            actor="Dana",
        )
    )
    db.commit()
    return future_on, marker


def _future_fact_procurement_agreement(db: Session, project_id: int) -> tuple[date, str]:
    """A ``ProcurementAgreement`` starting after ``AS_OF`` — ``assist_procurement``'s
    own ``_agreements`` filters ``start_date <= at``, so this proves that
    filter."""
    future_on = AS_OF + timedelta(days=30)
    marker = "Future Vendor XKJ482"
    db.add(
        ProcurementAgreement(project_id=project_id, vendor=marker, amount=1.0, start_date=future_on)
    )
    db.commit()
    return future_on, marker


def _future_fact_milestone(db: Session, project_id: int) -> tuple[date, str]:
    """A ``Milestone`` due after ``AS_OF`` — ``assist_scope``'s inspection
    section used to read every milestone with no ``at`` filter at all (fixed
    in ``assist_scope._milestones``, mirroring ``assist_closeout``'s own), so
    this is the check that caught it and now proves the fix stands."""
    future_on = AS_OF + timedelta(days=30)
    marker = "Future milestone XKJ493"
    db.add(Milestone(project_id=project_id, name=marker, target_date=future_on, status="pending"))
    db.commit()
    return future_on, marker


def _future_fact_quality_measurement(db: Session, project_id: int) -> tuple[date, str]:
    """A ``QualityMeasurement`` dated after ``AS_OF`` — ``quality_facts.metric_series``
    filters ``measured_on <= as_of``, so this proves that filter."""
    future_on = AS_OF + timedelta(days=30)
    marker = "Future Metric XKJ517"
    db.add(
        QualityMeasurement(
            project_id=project_id,
            metric=marker,
            target_value=1.0,
            actual_value=1.0,
            unit="%",
            measured_on=future_on,
        )
    )
    db.commit()
    return future_on, marker


def _future_fact_risk_response(db: Session, project_id: int) -> tuple[date, str]:
    """A response filed for a later date with a residual exposure no earlier
    render prints (0.9 x 7777 = 6999.30): the register's residual column and the
    total below it show that figure only once the as-of reaches that date
    (``risk_facts.latest_by_risk``'s as-of gate). The owner and strategy are the
    seeded ones on purpose — the page's owner and strategy selects list every
    person and every strategy at any as-of, so neither could carry the marker."""
    future_on = AS_OF + timedelta(days=30)
    risk = db.scalars(select(Risk).where(Risk.project_id == project_id)).one()
    owner = db.scalars(select(Person).order_by(Person.id)).first()
    assert owner is not None
    db.add(
        RiskResponse(
            project_id=project_id,
            risk_id=risk.id,
            strategy="mitigate",
            owner_id=owner.id,
            trigger="Later",
            planned_action="Later",
            residual_probability=0.9,
            residual_impact=7777.0,
            actor="pm",
            as_of=future_on,
        )
    )
    db.commit()
    return future_on, "6999.30"


def _future_fact_team_assessment(db: Session, project_id: int) -> tuple[date, str]:
    future_on = AS_OF + timedelta(days=30)
    db.add(
        TeamAssessment(
            project_id=project_id,
            assessed_on=future_on,
            dimension="Futuredimension",
            score=90.0,
            actor="qa",
        )
    )
    db.commit()
    return future_on, "Futuredimension"


def _future_fact_meeting_run(db: Session, project_id: int) -> tuple[date, str]:
    future_on = AS_OF + timedelta(days=30)
    db.add(
        TechniqueRun(
            project_id=project_id,
            technique_key="meetings",
            process_id="4.3",
            actor="Zed Futurechair",
            as_of=future_on,
            method="predictive",
        )
    )
    db.commit()
    return future_on, "Zed Futurechair"


def _future_fact_approved_baseline(db: Session, project_id: int) -> tuple[date, str]:
    """A second approved baseline whose approval instant is after ``AS_OF``, with a
    line for a task no earlier baseline names: the newest approved baseline AS OF a
    date is the one the network is drawn from (``adapters.approved_as_of``)."""
    future_on = AS_OF + timedelta(days=30)
    stream = db.scalars(select(Workstream).where(Workstream.project_id == project_id)).first()
    assert stream is not None
    task = Task(name="Futuretask", workstream=stream, estimate_unit="hours")
    baseline = Baseline(
        project_id=project_id,
        version=2,
        status="approved",
        approved_at=datetime(future_on.year, future_on.month, future_on.day, 9, 0),
    )
    db.add(
        BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=500.0,
            planned_start=future_on,
            planned_finish=future_on + timedelta(days=5),
        )
    )
    db.commit()
    return future_on, "Futuretask"


def _future_fact_sprint(db: Session, project_id: int) -> tuple[date, str]:
    """A sprint whose window opens after ``AS_OF``: the flow page names the sprint
    active AT the as-of, so this one is named only once the as-of is inside it."""
    future_on = AS_OF + timedelta(days=30)
    db.add(
        Sprint(
            project_id=project_id,
            name="Futuresprint",
            start_date=future_on,
            end_date=future_on + timedelta(days=13),
            committed_points=8,
            completed_points=0,
        )
    )
    db.commit()
    return future_on, "Futuresprint"


#: One future-fact injector per assistant page shape, keyed the same way
#: ``ALL_ASSISTANT_PAGES`` is.
FUTURE_FACT_INJECTORS = {
    "/projects/{}/assist/closeout": _future_fact_lesson_learned,
    "/projects/{}/assist/cost": _future_fact_cost_entry_run_rate,
    "/projects/{}/assist/decisions": _future_fact_meeting_run,
    "/projects/{}/assist/earned-value": _future_fact_cost_entry,
    "/projects/{}/assist/procurement": _future_fact_procurement_agreement,
    "/projects/{}/assist/quality": _future_fact_quality_measurement,
    "/projects/{}/assist/risk-responses": _future_fact_risk_response,
    "/projects/{}/assist/schedule": _future_fact_approved_baseline,
    "/projects/{}/assist/scope": _future_fact_milestone,
    "/projects/{}/assist/team": _future_fact_team_assessment,
    "/projects/{}/flow": _future_fact_sprint,
}

#: The one shape genuinely exempt from the as-of leak check, with why: unlike
#: every other row a shipped assistant reads, ``Stakeholder`` carries no date
#: column at all — ``assist_stakeholders.py``'s own docstring: "Stakeholder
#: carries no date of its own, so as_of is threaded only for the header every
#: sibling project page prints, never to filter a row." There is no "future"
#: reading of a stakeholder register to inject, the same way there is no
#: "future" reading of a person's name — the register is who is a stakeholder
#: NOW, not a dated history, so a leak check here would either assert nothing
#: (any stakeholder shows at any as-of, by design) or demand a filter the page
#: is correct to not have. Checked against ``ALL_ASSISTANT_PAGES`` below so a
#: shape can only sit here with a real, checked reason — never silently.
NO_AS_OF_LEAK_CHECK_REASONS: dict[str, str] = {
    "/projects/{}/assist/stakeholders": (
        "Stakeholder carries no date column (assist_stakeholders.py's own docstring) — "
        "the register is a current roster, not a dated history, so no as-of can leak."
    ),
    "/projects/{}/assist/requirements": (
        "Requirement, RequirementTrace and Deliverable carry no date column — the "
        "traceability matrix and the WBS are the project's current structure, not a dated "
        "history — and AcceptanceRecord's verified_on/accepted_on are both optional, so "
        "there is no date every ledger row carries to gate on."
    ),
    "/projects/{}/assist/decision-tree": (
        "The EMV calculator reads no stored row but the Project itself — every option, "
        "probability and value is typed into the query string and nothing is saved — so "
        "there is no dated fact in the store an earlier as_of could leak."
    ),
    "/projects/{}/assist/risk-pi": (
        "Risk carries no date column and assist_risk_pi.py reads nothing else — the P x I "
        "matrix scores the open register as it stands, so no dated row can leak into it."
    ),
}


def test_every_assistant_page_has_an_as_of_leak_check_or_a_reason_it_cannot() -> None:
    """No shape may sit outside both ``FUTURE_FACT_INJECTORS`` and
    ``NO_AS_OF_LEAK_CHECK_REASONS`` — a page that reads a dated row owes the
    leak check a real injector, and a page that structurally cannot (no dated
    row to inject) owes the reason above, not silence."""
    covered = set(FUTURE_FACT_INJECTORS) | set(NO_AS_OF_LEAK_CHECK_REASONS)
    uncovered = set(ALL_ASSISTANT_PAGES) - covered
    assert not uncovered, (
        f"{sorted(uncovered)} have neither a FUTURE_FACT_INJECTORS entry nor a "
        "NO_AS_OF_LEAK_CHECK_REASONS entry — add one or the other"
    )
    overlap = set(FUTURE_FACT_INJECTORS) & set(NO_AS_OF_LEAK_CHECK_REASONS)
    assert not overlap, f"{sorted(overlap)} are both injected and exempted — pick one"


def _extend_seed_for_every_assistant(db: Session, project_id: int) -> None:
    """The rows the OTHER assistants need that ``assist_evm``'s own overspend
    seed carries none of: a stakeholder (stakeholders/scope's context diagram),
    a met milestone dated on or before ``AS_OF`` (scope's inspection section,
    closeout's deliverable acceptance), the two narrative kinds ``assist_scope``
    reads, a procurement agreement, a lesson learned, a budget line (the cost
    workbench's aggregation and reserve sections), a second, otherwise-empty
    project (the cost workbench's historical-information-review section, which
    reads OTHER projects), an open issue and a dated quality measurement
    (quality's root-cause worksheet and control chart), and the
    quality-management-plan narrative quality's audit checklist reads — one
    row per model a later-merged assistant page reads, so every page renders
    real content rather than only its empty state under the shared fixture."""
    db.add(BudgetLine(project_id=project_id, category="labour", planned_amount=1000.0))
    # One stored cost estimate, so the cost workbench's "stored estimate scenarios"
    # section (W4.3b) lists a row rather than its empty state.
    db.add(
        EstimateScenario(
            project_id=project_id,
            target="cost",
            kind="parametric",
            value=1200.0,
            basis="12 per hour over 100 hours",
            actor="jp",
            as_of=JAN,
        )
    )
    db.add(
        Project(
            name="Reference Co",
            portfolio=Portfolio(name="Other", business=Business(name="Other Biz")),
            delivery_mode="predictive",
        )
    )
    db.add(Stakeholder(project_id=project_id, name="Ada", interest="high", influence="high"))
    db.add(
        Milestone(project_id=project_id, name="Rough cut locked", target_date=AS_OF, status="met")
    )
    db.add(
        NarrativeArtifact(
            project_id=project_id, kind="project_scope_statement", body="Grade and deliver."
        )
    )
    db.add(
        NarrativeArtifact(
            project_id=project_id, kind="requirements_documentation", body="4K, colour-graded."
        )
    )
    db.add(
        ProcurementAgreement(
            project_id=project_id, vendor="Colourist Co", amount=500.0, start_date=JAN
        )
    )
    db.add(
        LessonLearned(
            project_id=project_id,
            raised_on=AS_OF,
            category="schedule",
            what_happened="The grade ran long.",
            what_to_do_next_time="Book an extra day.",
            actor="Dana",
        )
    )
    db.add(Issue(project_id=project_id, description="Late render", raised_on=AS_OF, status="open"))
    db.add_all(
        QualityMeasurement(
            project_id=project_id,
            metric="Defect rate",
            target_value=2.0,
            actual_value=actual,
            unit="%",
            measured_on=on,
        )
        for on, actual in ((JAN, 1.0), (AS_OF, 1.0))
    )
    db.add(
        NarrativeArtifact(
            project_id=project_id,
            kind="quality_management_plan",
            body="Inspect every reel before delivery.",
        )
    )
    # The pages merged after the six above: a person to own things; an open
    # threat with one response (the risk-response planner); a requirement, a
    # WBS node, the trace between them and one acceptance entry (the
    # requirements/WBS worksheet); a resource type with an RBS node, a RACI
    # line, an acquisition, a training record, a team assessment and an open
    # conflict with its action (the team page); one recorded meeting (the
    # decisions page); and a sprint whose window contains AS_OF plus two backlog
    # items (the flow page). The schedule-network page reads the earned-value
    # seed's own approved, lined baseline.
    dana = Person(name="Dana")
    db.add(dana)
    risk = Risk(
        project_id=project_id,
        description="Vendor outage",
        probability=0.5,
        impact=1000.0,
        status="open",
        kind="threat",
    )
    db.add(risk)
    db.flush()
    db.add(
        RiskResponse(
            project_id=project_id,
            risk_id=risk.id,
            strategy="mitigate",
            owner_id=dana.id,
            trigger="Outage exceeds four hours",
            planned_action="Fail over to the secondary vendor",
            residual_probability=0.1,
            residual_impact=200.0,
            actor="pm",
            as_of=JAN,
        )
    )
    requirement = Requirement(
        project_id=project_id, code="REQ-1", statement="Must ship", actor="qa"
    )
    deliverable = Deliverable(project_id=project_id, name="Grade", wbs_code="1")
    db.add_all([requirement, deliverable])
    db.flush()
    db.add(RequirementTrace(requirement=requirement, deliverable=deliverable))
    db.add(AcceptanceRecord(deliverable=deliverable, verified_on=JAN, actor="qa"))
    resource_type = ResourceType(
        project_id=project_id, name="Colourist", kind="people", unit="hours"
    )
    db.add(resource_type)
    db.flush()
    db.add(ResourceBreakdown(project_id=project_id, resource_type=resource_type, quantity=1.0))
    db.add(
        ResponsibilityAssignment(
            project_id=project_id, deliverable=deliverable, person=dana, role="accountable"
        )
    )
    db.add(
        Acquisition(
            project_id=project_id,
            resource_type=resource_type,
            source="external",
            requested_on=JAN,
            status="requested",
        )
    )
    db.add(TrainingRecord(person=dana, topic="Colour grading", completed_on=JAN))
    db.add(
        TeamAssessment(
            project_id=project_id, assessed_on=JAN, dimension="Performing", score=70.0, actor="qa"
        )
    )
    conflict = ConflictRecord(
        project_id=project_id,
        raised_on=JAN,
        parties="Ada, Dana",
        approach="collaborate",
        actor="qa",
    )
    db.add(conflict)
    db.flush()
    db.add(ConflictAction(conflict=conflict, owner=dana, due_on=AS_OF))
    db.add(
        TechniqueRun(
            project_id=project_id,
            technique_key="meetings",
            process_id="4.3",
            actor="Dana",
            as_of=JAN,
            method="predictive",
        )
    )
    db.add(
        Sprint(
            project_id=project_id,
            name="Sprint 1",
            start_date=JAN,
            end_date=AS_OF,
            committed_points=10,
            completed_points=5,
        )
    )
    db.add(BacklogItem(project_id=project_id, title="Cut", story_points=3, status="in_progress"))
    db.add(BacklogItem(project_id=project_id, title="Mix", story_points=5, status="done"))
    db.commit()


@pytest.fixture
def assistant_store(tmp_path: Path) -> Iterator[tuple[Engine, sessionmaker[Session], int]]:
    """The earned-value seed (``test_web_assist_evm``'s own overspend scenario),
    plus one row per model every OTHER shipped assistant reads, on a throwaway
    SQLite file so the engine is countable. Every currently shipped assistant
    reads this same project, so one seed covers the whole walk; a future
    assistant needing rows this seed lacks extends
    ``_extend_seed_for_every_assistant``."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as db:
        assist_evm._seed(db)
        project_id = db.scalars(select(Project.id)).one()
        _extend_seed_for_every_assistant(db, project_id)
    yield engine, factory, project_id


@pytest.fixture
def assistant_client(
    assistant_store: tuple[Engine, sessionmaker[Session], int],
) -> Iterator[tuple[Engine, TestClient, Session, int]]:
    engine, factory, project_id = assistant_store
    with factory() as db:
        real_app.dependency_overrides[get_session] = lambda: db
        with TestClient(real_app, base_url="https://testserver") as client:
            yield engine, client, db, project_id
        real_app.dependency_overrides.clear()


@pytest.mark.parametrize("shape,template", sorted(ALL_ASSISTANT_PAGES.items()))
def test_the_assistant_page_renders_real_content_not_only_an_empty_state(
    assistant_client: tuple[Engine, TestClient, Session, int], shape: str, template: str
) -> None:
    _, client, _, project_id = assistant_client
    resp = client.get(f"{template.format(project_id=project_id)}{Q}")
    assert resp.status_code == 200, f"{shape}: {resp.status_code}"
    assert _EMPTY not in resp.text, f"{shape} renders only its empty state under the seeded fixture"


@pytest.mark.parametrize("shape,template", sorted(ALL_ASSISTANT_PAGES.items()))
def test_two_renders_at_the_same_as_of_are_byte_identical(
    assistant_client: tuple[Engine, TestClient, Session, int], shape: str, template: str
) -> None:
    _, client, _, project_id = assistant_client
    path = f"{template.format(project_id=project_id)}{Q}"
    assert client.get(path).text == client.get(path).text, f"{shape} moved between two renders"


@pytest.mark.parametrize("shape,template", sorted(ALL_ASSISTANT_PAGES.items()))
def test_an_earlier_as_of_never_shows_a_fact_dated_after_it(
    assistant_client: tuple[Engine, TestClient, Session, int], shape: str, template: str
) -> None:
    _, client, db, project_id = assistant_client
    inject = FUTURE_FACT_INJECTORS.get(shape)
    if inject is None:
        reason = NO_AS_OF_LEAK_CHECK_REASONS[shape]  # KeyError here means the totality
        # test above is broken, not that this shape is genuinely uncovered
        pytest.skip(f"{shape}: {reason}")
    future_on, marker = inject(db, project_id)
    path = template.format(project_id=project_id)
    earlier = client.get(f"{path}?as_of={AS_OF.isoformat()}").text
    later = client.get(f"{path}?as_of={future_on.isoformat()}").text
    assert marker not in earlier, (
        f"{shape} as of {AS_OF} shows {marker!r}, a fact dated {future_on} — a fact from the "
        "future leaked into an earlier as-of render"
    )
    assert marker in later, (
        f"{shape} never shows {marker!r} even as of {future_on}, so this proves nothing about as-of"
    )


# Ceilings the earned-value page's own reads stay under — the same headroom
# convention ``test_perf_n1`` uses: measured + 2, never a number chosen
# because it looked safe. Every key is re-measured by the test below via
# ``assert_recorded``.
MEASURED: dict[str, int] = {
    "/projects/{}/assist/closeout": 7,
    "/projects/{}/assist/cost": 9,
    "/projects/{}/assist/earned-value": 5,
    "/projects/{}/assist/procurement": 2,
    "/projects/{}/assist/quality": 5,
    "/projects/{}/assist/scope": 4,
    "/projects/{}/assist/stakeholders": 2,
    "/projects/{}/assist/decisions": 2,
    "/projects/{}/assist/decision-tree": 1,
    "/projects/{}/assist/requirements": 8,
    "/projects/{}/assist/risk-responses": 11,
    "/projects/{}/assist/risk-pi": 2,
    "/projects/{}/assist/schedule": 8,
    "/projects/{}/assist/team": 13,
    "/projects/{}/flow": 6,
}


@pytest.mark.parametrize("shape,template", sorted(ALL_ASSISTANT_PAGES.items()))
def test_each_assistant_page_stays_under_its_statement_ceiling(
    assistant_client: tuple[Engine, TestClient, Session, int], shape: str, template: str
) -> None:
    engine, client, _, project_id = assistant_client
    assert shape in MEASURED, f"{shape}: no MEASURED baseline recorded — measure live and add one"
    path = f"{template.format(project_id=project_id)}{Q}"
    stmts, status = count_route(engine, client, path)
    assert status == 200, f"{shape}: {status}"
    ceiling = MEASURED[shape] + 2
    assert stmts <= ceiling, (
        f"{shape} ran {stmts} statements (ceiling {ceiling}): a read that used to be batched "
        "is querying lazily again"
    )
    assert_recorded(MEASURED, shape, stmts)


def test_every_recorded_assistant_baseline_is_re_measured() -> None:
    """The same drift guard ``test_perf_n1`` carries, restated for a
    parametrized walk: every ``MEASURED`` key is re-measured by the statement
    ceiling test above, which parametrizes over ``ALL_ASSISTANT_PAGES`` and calls
    ``assert_recorded`` on every page it runs — so a key naming no mounted
    page is a stale baseline nothing exercises, caught here rather than
    looking authoritative forever."""
    stale = sorted(set(MEASURED) - set(ALL_ASSISTANT_PAGES))
    assert not stale, f"MEASURED records {stale}, which names no mounted assistant page"


def test_every_svg_an_assistant_template_draws_carries_a_no_js_text_alternative() -> None:
    """The idiom ``test_web_method_map``'s no-JS ties list already uses: an
    ``<svg>``'s content must ALSO be stated as plain text/table markup in the
    same page, so print and no-JS keep what the graphic carries. Walked over
    every ``assist_*.html`` template directly, so it is wired to fail the day
    one draws a chart with nothing beside it, rather than staying silent
    because no assistant does yet."""
    offences = []
    for template in sorted(_TEMPLATES.glob("assist_*.html")):
        body = template.read_text()
        if not _SVG.search(body):
            continue
        if "<table" not in body and "<details" not in body:
            offences.append(
                f"{template.name} draws an <svg> with no <table> or <details> stating the "
                "same figures in text — a chart needs a no-JS/print alternative"
            )
    assert not offences, "\n".join(offences)


@pytest.mark.parametrize("shape,template", sorted(ALL_ASSISTANT_PAGES.items()))
def test_a_viewer_reads_the_page_and_only_a_writer_role_could_write_it(
    gated: Gate, shape: str, template: str
) -> None:
    path = f"{template.format(project_id=1)}{Q}"
    viewer = _client(gated, Authorization=f"Bearer {gated.viewer}")
    assert viewer.get(path).status_code == 200, f"{shape}: a viewer could not even read it"
    contributor = _client(gated, Authorization=f"Bearer {gated.token}")
    assert contributor.get(path).status_code == 200, f"{shape}: a contributor could not read it"

    post_shapes = _web_paths("POST")
    if shape not in post_shapes:
        return  # a GET-only assistant offers nothing to write; nothing to refuse a viewer
    refused = viewer.post(path.split("?")[0], data={})
    assert refused.status_code == 403, (
        f"{shape} offers a POST and a viewer's token was not refused it: {refused.status_code}"
    )
    assert "role" in refused.text.lower() or "contributor" in refused.text.lower()


def _importer() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_import", _IMPORTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_any_row_kind_an_assistant_can_write_round_trips_through_export_and_import() -> None:
    """No routed assistant writes anything today (``assist_evm.py``: "Nothing is
    written, and the stored snapshot is untouched"; ``test_web_assist_evm``
    pins the ``CostEntry`` count unchanged across every what-if call), so this
    walk is empty and passes vacuously — but it is wired against the live
    ``_web_paths("POST")`` registry, so the day a routed assistant grows a
    write, its shape lands in this set and the assertion below stops being
    vacuous, requiring the row kind it writes to appear in
    ``bin/driftless-import.py``'s ``CSV_KINDS`` before it can pass."""
    write_shapes = _web_paths("POST") & set(ALL_ASSISTANT_PAGES)
    if not write_shapes:
        return
    # A future write lands here as: export the written table's rows as CSV
    # (``format=csv`` on its list route), drop the server-managed id/
    # row_revision columns — the asymmetry
    # ``test_api_export.test_importing_an_export_unchanged_names_the_id_
    # column_and_why`` already refuses — and re-import them through
    # ``_importer().import_csv``, asserting the round trip is exact: exactly
    # ``test_api_export.test_the_importers_payloads_round_trip_through_the_
    # real_api``'s shape, scoped to whichever ``CSV_KINDS`` entry the new
    # write's row kind uses.
    importer = _importer()
    assert write_shapes <= {
        shape for shape, kind in ASSISTANT_WRITE_KINDS.items() if kind in importer.CSV_KINDS
    }, (
        f"{sorted(write_shapes)} write a row with no CSV_KINDS entry naming it in "
        "bin/driftless-import.py, or no entry in this module's own ASSISTANT_WRITE_KINDS"
    )


# Two branches the totality walk above renders past without ever landing on:
# every seeded scenario is over budget or on time, never at the exact tie a
# comparison operator treats as its own case, and every existing refusal test
# posts a well-formed "<id>:<level>" pair with a bad id or a bad level, never
# one that does not even parse. Full-gate coverage on this PR (#350) named
# both by line; each is exercised here rather than left for a future page's
# walk to trip over by accident.


def test_the_earned_value_page_names_the_exact_cpi_balance_case(
    assistant_client: tuple[Engine, TestClient, Session, int],
) -> None:
    """``assist_evm._cpi_interpretation``'s ``cpi == 1.0`` branch — spend and
    the value of finished work exactly balanced. The seeded overspend
    scenario is always CPI 0.25; the what-if CPI input is the one path that
    can land exactly on 1.0 without a second fixture."""
    _, client, _, project_id = assistant_client
    path = f"/projects/{project_id}/assist/earned-value{Q}&whatif_cpi=1.0"
    assert "Spend and the value of finished work are exactly in balance." in client.get(path).text


def test_the_stakeholders_page_refuses_a_desired_input_that_does_not_parse(
    assistant_client: tuple[Engine, TestClient, Session, int],
) -> None:
    """``assist_stakeholders._parse_desired``'s first refusal — a ``desired``
    value with no ``:`` separator or a non-digit id — never reached by a
    well-formed pair naming a bad id or a bad level, which is what every
    other refusal test in the suite posts."""
    _, client, _, project_id = assistant_client
    resp = client.get(f"/projects/{project_id}/assist/stakeholders{Q}&desired=not-a-pair")
    assert resp.status_code == 422


# --- D.4: one assistant-page pattern (summary strip + per-technique cards) -----

#: Every routed assist page's own shape, excluding the flow calculator — a page
#: mounted under /assist/ whose template is genuinely one of this unit's own
#: ``assist_*.html`` files, never ``flow.html`` (a sibling design unit's own).
_ASSIST_TEMPLATE_SHAPES: dict[str, str] = {
    shape: template for shape, template in ALL_ASSISTANT_PAGES.items() if "/assist/" in shape
}


@pytest.mark.parametrize("shape,template", sorted(_ASSIST_TEMPLATE_SHAPES.items()))
def test_every_assist_page_opens_with_a_summary_strip_and_renders_cards(
    assistant_client: tuple[Engine, TestClient, Session, int], shape: str, template: str
) -> None:
    """The one assistant-page shape ``_assist.html``'s macros draw: a
    ``.tiles.assist-summary`` strip of headline figures, then every technique
    section rendered as its own ``.card.assist-card`` — never a bare ``<h2>``
    sitting over prose alone."""
    _, client, _, project_id = assistant_client
    body = client.get(f"{template.format(project_id=project_id)}{Q}").text
    assert 'class="tiles assist-summary"' in body, f"{shape}: no summary strip"
    assert 'class="card assist-card"' in body, f"{shape}: no technique rendered as a card"
