"""``TechniqueRun``: the append-only provenance ledger and its one write path.

``record_run`` refuses a run with no actor, or naming a technique/process the
catalogs do not recognize, before either becomes a stored row.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless.models import Project, TechniqueRun
from driftless.pmbok.provenance import MethodContext, Provenance
from driftless.services.technique_runs import (
    MissingActorError,
    UnknownProcessError,
    UnknownTechniqueError,
    record_run,
    runs_for_project,
)

AS_OF = date(2026, 3, 31)


def _run(project: Project, **overrides: object) -> dict[str, object]:
    return {
        "project_id": project.id,
        "technique_key": "earned_value_analysis",
        "process_id": "7.4",
        "actor": "jp",
        "as_of": AS_OF,
        "method": MethodContext.PREDICTIVE,
        "source_version": "PMBOK-6",
        **overrides,
    }


def test_a_valid_run_is_recorded_and_read_back(db: Session, project: Project) -> None:
    run = record_run(
        db,
        **_run(
            project,
            inputs_snapshot={"baseline": [1]},
            outputs_produced={"work_performance_information": [7]},
        ),
    )
    stored = db.get(TechniqueRun, run.id)
    assert stored is not None
    assert (stored.technique_key, stored.process_id, stored.actor) == (
        "earned_value_analysis",
        "7.4",
        "jp",
    )
    assert stored.method == "predictive"
    assert '"baseline"' in stored.inputs_snapshot
    assert '"work_performance_information"' in stored.outputs_produced


def test_a_provenance_dataclass_carries_the_same_five_fields() -> None:
    prov = Provenance("earned_value_analysis", "7.4", "jp", AS_OF, "PMBOK-6")
    assert prov.technique_key == "earned_value_analysis" and prov.as_of == AS_OF
    with pytest.raises(AttributeError):
        prov.actor = "someone-else"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"actor": None}, MissingActorError),
        ({"technique_key": "not-a-real-technique"}, UnknownTechniqueError),
        ({"process_id": "99.9"}, UnknownProcessError),
    ],
)
def test_an_invalid_run_is_refused(
    db: Session, project: Project, overrides: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        record_run(db, **_run(project, **overrides))


def test_runs_are_found_by_project_and_as_of(db: Session, project: Project) -> None:
    for when in (date(2026, 1, 1), date(2026, 3, 1), date(2026, 6, 1)):
        record_run(db, **_run(project, as_of=when))
    # The run dated after AS_OF must not appear.
    found = runs_for_project(db, project.id, AS_OF)
    assert [r.as_of for r in found] == [date(2026, 3, 1), date(2026, 1, 1)]
