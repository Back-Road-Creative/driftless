"""Business-wide process rollup: counts are the exact hand-computable tally of
``state.project_process_states`` (§10 acceptance); applicable/share follow
``state.completeness``'s waived/not-assessable exclusion, pooled."""

from collections import Counter
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, NarrativeArtifact, Portfolio, Project, Risk, SignOff
from driftless.pmbok import catalog, mapping
from driftless.pmbok import state as st
from driftless.pmbok.model import KnowledgeArea, Process
from driftless.pmbok.rollup import (
    business_area_shares,
    business_completeness,
    business_process_cells,
)

AS_OF = date(2026, 3, 31)
IDENTIFY_RISKS = catalog.get("11.2")  # assessable: risk_register, risk_report, assumption_log
MANAGE_COMMS = catalog.get("10.2")  # never-assessable, via the ``untracked`` fixture below


@pytest.fixture
def untracked(monkeypatch: pytest.MonkeyPatch) -> Process:
    """A process the store tracks no output of. All 49 are tracked now, so the condition is
    created — its outputs' resolvers taken away — and the pool's exclusion stays under test."""
    for kind in MANAGE_COMMS.outputs:
        monkeypatch.delitem(mapping.RESOLVERS, kind, raising=False)
    assert not st.is_assessable(MANAGE_COMMS), "still assessable — the exclusion is untested"
    return MANAGE_COMMS


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


def _project(session: Session, name: str) -> Project:
    project = Project(
        name=name, portfolio=Portfolio(name=f"{name} port", business=Business(name=f"{name} biz"))
    )
    session.add(project)
    session.commit()
    return project


def _sign_off(session: Session, project: Project, process: Process, decision: str) -> None:
    session.add(
        SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(process, project),
            decision=decision,
        )
    )


def test_business_completeness_pools_produced_or_better_over_applicable(
    session: Session,
) -> None:
    """Produced-or-better over applicable pairs, agreeing with ``state``'s own
    tally pooled; an empty store is ``None``."""
    assert business_completeness(business_process_cells(session, AS_OF)) is None
    alpha = _project(session, "Alpha")
    session.add(NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
    session.commit()

    pairs = st.project_process_states(alpha, session, AS_OF)
    states = [s for p, s in pairs if s is not st.ProcessState.WAIVED and st.is_assessable(p)]
    done = sum(1 for s in states if s in (st.ProcessState.PRODUCED, st.ProcessState.SIGNED_OFF))
    share = business_completeness(business_process_cells(session, AS_OF))
    assert done and share == pytest.approx(done / len(states)), "seed must produce a real share"


def test_business_completeness_pools_the_hand_tally_of_per_project_completeness(
    session: Session,
) -> None:
    """``business_completeness``'s applicable/share pooling must be exactly the
    sum of each project's own counted/done tally — the same tally
    ``state.completeness`` produces for that project. Recomputed here from
    ``project_process_states`` and ``state.excluded_from_completeness`` directly
    (bypassing both target functions), so the per-project rule and its
    business-wide pooling can never silently drift apart — the gap the pages
    ring test already closes for ``area_completeness``, now closed here too."""
    a, b = _project(session, "Alpha"), _project(session, "Beta")
    session.add(Risk(project=a, description="r", probability=0.3, impact=1000.0))
    session.add(NarrativeArtifact(project=a, kind="assumption_log", body="drone weather"))
    _sign_off(session, b, IDENTIFY_RISKS, "waived")
    _sign_off(session, a, MANAGE_COMMS, "accepted")
    session.commit()

    counted_total = done_total = 0
    for project in (a, b):
        counted = done = 0
        for process, proc_state in st.project_process_states(project, session, AS_OF):
            if st.excluded_from_completeness(process, proc_state):
                continue
            counted += 1
            if proc_state in (st.ProcessState.PRODUCED, st.ProcessState.SIGNED_OFF):
                done += 1
        assert st.completeness(project, session, AS_OF) == pytest.approx(done / counted)
        counted_total += counted
        done_total += done

    share = business_completeness(business_process_cells(session, AS_OF))
    assert share == pytest.approx(done_total / counted_total)


def test_business_process_cells_hand_computed_and_completeness_exclusions(
    session: Session, untracked: Process
) -> None:
    """A bare store: 49 cells, catalog order, shareless. Then the §10
    acceptance (counts == hand tally, EVERY process) plus the exclusion pin:
    Beta waives an assessable process; Alpha signs off a NEVER-assessable one
    (still excluded). Also pins (name, id) roster order."""
    bare = business_process_cells(session, AS_OF)
    assert len(bare) == len(catalog.PROCESSES) == 49
    assert [c.process_id for c in bare] == [p.id for p in catalog.PROCESSES]
    assert all(c.applicable == 0 and c.share is None and c.projects == () for c in bare)

    a, b = _project(session, "Alpha"), _project(session, "Beta")
    session.add(Risk(project=a, description="r", probability=0.3, impact=1000.0))
    session.add(NarrativeArtifact(project=a, kind="assumption_log", body="drone weather"))
    _sign_off(session, b, IDENTIFY_RISKS, "waived")
    _sign_off(session, a, MANAGE_COMMS, "accepted")
    session.commit()

    expected: dict[str, Counter[st.ProcessState]] = {p.id: Counter() for p in catalog.PROCESSES}
    for project in (a, b):
        for process, proc_state in st.project_process_states(project, session, AS_OF):
            expected[process.id][proc_state] += 1

    cells = {c.process_id: c for c in business_process_cells(session, AS_OF)}
    for pid, cell in cells.items():
        expected_full = {s: expected[pid].get(s, 0) for s in st.ProcessState}
        assert dict(cell.counts) == expected_full, f"counts drift on {pid}"

    risks = cells["11.2"]
    assert risks.applicable == 1 and risks.share == 1.0
    assert [(pc.project_name, pc.state) for pc in risks.projects] == [
        ("Alpha", st.ProcessState.PRODUCED),
        ("Beta", st.ProcessState.WAIVED),
    ]
    comms = cells["10.2"]
    assert comms.counts[st.ProcessState.SIGNED_OFF] == 1 and comms.applicable == 0
    assert comms.share is None


def test_business_area_shares_pools_per_area_catalog_order_and_untracked_processes_stay_out(
    session: Session, untracked: Process
) -> None:
    """Catalog KA order, pinned; a bare store is ``None`` everywhere. Since the
    management-plan resolver wave every area holds at least one assessable process,
    so no area reads ``None`` by catalog fact any more — the exclusion shows at the
    process level instead: Communications pools 10.1 and 10.3 (10.2 stays untracked),
    so with neither project's communications plan written and neither carrying the
    plan-plus-actuals 10.3 derives its information from, it measures an honest 0.0 —
    and even an *accepted* sign-off on untracked 10.2 moves nothing.
    Risk pools the SAME produced-or-better/applicable rule ``business_completeness``
    pools, scoped to just that area's processes."""
    bare = business_area_shares(business_process_cells(session, AS_OF))
    assert [s.area for s in bare] == list(KnowledgeArea)
    assert all(s.share is None for s in bare)
    assessable = [
        p.id for p in catalog.by_area(KnowledgeArea.COMMUNICATIONS) if st.is_assessable(p)
    ]
    assert assessable == ["10.1", "10.3"], "exactly 10.1 and 10.3 assessable in Communications"

    a, b = _project(session, "Alpha"), _project(session, "Beta")
    session.add(Risk(project=a, description="r", probability=0.3, impact=1000.0))
    session.add(NarrativeArtifact(project=a, kind="assumption_log", body="drone weather"))
    _sign_off(session, b, IDENTIFY_RISKS, "waived")
    _sign_off(session, a, MANAGE_COMMS, "accepted")
    session.commit()

    shares = {s.area: s.share for s in business_area_shares(business_process_cells(session, AS_OF))}
    assert shares[KnowledgeArea.COMMUNICATIONS] == 0.0  # 10.1 applicable twice, produced never

    expected_applicable = expected_done = 0
    for project in (a, b):
        for process, proc_state in st.project_process_states(project, session, AS_OF):
            if process.area is not KnowledgeArea.RISK:
                continue
            if proc_state is st.ProcessState.WAIVED or not st.is_assessable(process):
                continue
            expected_applicable += 1
            if proc_state in (st.ProcessState.PRODUCED, st.ProcessState.SIGNED_OFF):
                expected_done += 1
    assert expected_applicable, "seed must touch the risk area"
    assert shares[KnowledgeArea.RISK] == pytest.approx(expected_done / expected_applicable)
