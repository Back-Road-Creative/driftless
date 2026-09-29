"""The onboarding wizard, including the self-onboarding capstone (§12).

The capstone: from an empty database, a loop drives ``next`` / ``apply`` — no
human, every write through the validated API boundary — until the wizard reports
every Initiating and Planning process complete, and the ChangeLog proves the
writes went through the boundary rather than straight into the tables.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import Business, Portfolio, Project
from driftless.pmbok import mapping
from driftless.pmbok import state as st
from driftless.pmbok.model import ProcessGroup
from driftless.wizard import engine
from driftless.wizard.cli import body_kinds, produce, seed_fields
from tests.conftest import AS_OF

ONBOARDING = (ProcessGroup.INITIATING, ProcessGroup.PLANNING)
PROSE = "Vendor lead times hold at six weeks; the drone crew is weather-bound in March."


@pytest.fixture
def factory(tmp_path: object) -> sessionmaker[Session]:
    engine_ = new_engine("sqlite://")
    Base.metadata.create_all(engine_)
    made = new_session_factory(engine_)
    register_changelog(made)  # wizard writes are audited, exactly like the API's
    return made


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
    )
    session.add(project)
    session.commit()
    return project


def test_next_step_points_at_the_first_initiating_process(
    session: Session, project: Project
) -> None:
    step = engine.next_step(session, project, AS_OF, ONBOARDING)
    assert step is not None
    assert step.group == "initiating"
    assert step.producible, "the wizard only offers processes it can help complete"
    assert not step.inputs_ready, "a bare project has none of its inputs yet"


def test_status_maps_every_process(session: Session, project: Project) -> None:
    m = dict(engine.status(session, project, AS_OF))
    assert len(m) == 49
    assert m["4.1"] == "not_started"


def test_self_onboarding_capstone(session: Session, project: Project) -> None:
    """Drive next/apply to completion over Initiating + Planning — no human clicks.

    Still unattended: the loop types nothing. What it no longer relies on is the
    *producer* inventing a value — every placeholder now comes from ``seed_fields``, the
    seeding side, which is exactly the caller that means them.

    ``next_step`` no longer skips a derived step (nothing of its own to produce): it
    is the step, honestly labelled, until the inputs it is waiting on land. Reaching
    it, the loop does what a reader following its "produced by" pointers would —
    produce whatever else in scope is still missing — the same escape a person or an
    agent has, without the wizard picking a different process for them.
    """
    from driftless.pmbok import catalog

    guard = 0
    while (step := engine.next_step(session, project, AS_OF, ONBOARDING)) is not None:
        made = False
        candidates = step.producible or tuple(
            kind
            for group in ONBOARDING
            for other in catalog.by_group(group)
            for kind in engine._producible(other)
        )
        for kind in candidates:
            if not mapping.resolve(kind, project, session, AS_OF).present:
                produce(session, project, kind, seed_fields(kind, AS_OF), AS_OF, "test")
                made = True
        assert made, f"stuck on {step.process_id} with no producible output anywhere in scope"
        guard += 1
        assert guard < 60, "onboarding should converge well within 60 steps"

    # Every assessable Initiating/Planning process is now done.
    remaining = engine.next_step(session, project, AS_OF, ONBOARDING)
    assert remaining is None
    states = dict(engine.status(session, project, AS_OF))
    for group in ONBOARDING:
        from driftless.pmbok import catalog

        for procss in catalog.by_group(group):
            if st.is_assessable(procss):
                assert states[procss.id] in ("produced", "signed_off", "waived")

    # The writes went through the boundary: the ChangeLog recorded each insert.
    logged = {
        row.table_name
        for row in session.scalars(select(ChangeLog).where(ChangeLog.operation == "insert"))
    }
    assert {"risk", "stakeholder", "budget_line", "baseline", "narrative_artifact"} <= logged


def test_produce_validates_through_the_schema(session: Session, project: Project) -> None:
    """A bad value is refused at the Pydantic boundary, not written to the row."""
    from pydantic import ValidationError

    supplied = {"description": PROSE, "impact": "1000", "probability": "5.0"}  # > 1
    with pytest.raises(ValidationError):
        produce(session, project, "risk_register", supplied, AS_OF, "test")


def test_produce_rejects_an_unproducible_kind(session: Session, project: Project) -> None:
    with pytest.raises(KeyError):
        produce(session, project, "project_management_plan", {}, AS_OF, "test")


def test_produce_refuses_a_narrative_kind_with_no_prose(session: Session, project: Project) -> None:
    """A narrative artifact IS its prose, so the producer invents none for a caller.

    It used to substitute a placeholder, which filed words no one wrote under the
    operator's name — and the row it filed reads *absent* to ``mapping.resolve``
    anyway, so the wizard reported an output every completeness figure still counted
    missing, behind a unique ``(project, kind)`` that turns the honest retry carrying
    the real text into a duplicate-key failure.
    """
    from driftless.models import NarrativeArtifact

    for fields in ({}, {"body": "   "}):  # blank is the same nothing as absent
        with pytest.raises(ValueError):
            produce(session, project, "assumption_log", fields, AS_OF, "test")
    assert not session.scalars(select(NarrativeArtifact)).all(), "a refused body wrote a row"
    assert not mapping.resolve("assumption_log", project, session, AS_OF).present


def test_wizard_cli_apply_refuses_a_narrative_kind_with_no_body(tmp_path: object) -> None:
    """``wizard apply --kind assumption_log`` with no ``--field body=`` refuses and
    writes nothing. The CLI is the surface that still fabricated after the browser
    form was fixed to answer 422 on exactly this input; both now refuse.
    """
    from pathlib import Path

    from driftless import cli
    from driftless.models import NarrativeArtifact

    assert isinstance(tmp_path, Path)
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    e = new_engine(url)
    Base.metadata.create_all(e)
    with new_session_factory(e)() as db:
        db.add(Project(name="GMS", portfolio=Portfolio(name="C", business=Business(name="BRC"))))
        db.commit()

    argv = ["wizard", "apply", "--project", "GMS", "--kind", "assumption_log",
            "--as-of", AS_OF.isoformat(), "--db-url", url]  # fmt: skip
    assert cli.main(argv) == 2, "a body-less apply exited 0 — it wrote something"
    with new_session_factory(e)() as db:
        assert not db.scalars(select(NarrativeArtifact)).all(), "the CLI fabricated a body"

    # The identical command carrying prose is accepted: the refusal is the missing body.
    assert cli.main([*argv, "--field", f"body={PROSE}"]) == 0
    with new_session_factory(e)() as db:
        assert db.scalars(select(NarrativeArtifact)).one().body == PROSE


@pytest.mark.parametrize(
    "kind",
    [
        "issue_log",
        "change_log",
        "agreements",
        "quality_report",
        "lessons_learned_register",
        "enterprise_environmental_factors",
        "organizational_process_assets",
        "status_report",
        "project_schedule",
    ],
)
def test_produce_each_remaining_kind_makes_it_present(
    session: Session, project: Project, kind: str
) -> None:
    """Every producible kind the capstone did not exercise still resolves present.

    Fields come from ``seed_fields`` for the same reason the capstone's do: three of
    these kinds are prose, and the producer no longer writes prose nobody supplied.
    """
    assert not mapping.resolve(kind, project, session, AS_OF).present
    produce(session, project, kind, seed_fields(kind, AS_OF), AS_OF, "test")
    assert mapping.resolve(kind, project, session, AS_OF).present


def test_seed_fields_carries_prose_for_every_narrative_kind() -> None:
    """The placeholder lives on the seeding side, derived from the producer table the
    form already reads — so a fifth narrative kind is seedable on the commit that makes
    it producible, and no other kind is handed a body it has no column for."""
    assert all(seed_fields(kind, AS_OF)["body"].strip() for kind in body_kinds())
    assert "body" not in seed_fields("risk_register", AS_OF), "a kind with no body column"


def test_wizard_cli_status_and_unknown_project(tmp_path: object) -> None:
    import io
    import json
    from contextlib import redirect_stdout
    from pathlib import Path

    from driftless import cli

    assert isinstance(tmp_path, Path)
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    e = new_engine(url)
    Base.metadata.create_all(e)
    with new_session_factory(e)() as db:
        db.add(Project(name="GMS", portfolio=Portfolio(name="C", business=Business(name="BRC"))))
        db.commit()

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = cli.main(["wizard", "status", "--project", "GMS", "--db-url", url])
    assert rc == 0
    assert len(json.loads(buffer.getvalue())) == 49

    assert cli.main(["wizard", "status", "--project", "Ghost", "--db-url", url]) == 2
    assert cli.main(["wizard", "next", "--project", "Ghost", "--db-url", url]) == 2
    assert (
        cli.main(
            ["wizard", "apply", "--project", "Ghost", "--kind", "risk_register", "--db-url", url]
        )
        == 2
    )


def test_wizard_cli_next_and_apply(tmp_path: object) -> None:
    """The CLI drives the same loop; `next` is JSON and `apply` writes."""
    import json
    from pathlib import Path

    from driftless import cli

    assert isinstance(tmp_path, Path)
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    e = new_engine(url)
    Base.metadata.create_all(e)
    with new_session_factory(e)() as db:
        db.add(Project(name="GMS", portfolio=Portfolio(name="C", business=Business(name="BRC"))))
        db.commit()

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert (
            cli.main(
                [
                    "wizard",
                    "next",
                    "--project",
                    "GMS",
                    "--as-of",
                    AS_OF.isoformat(),
                    "--db-url",
                    url,
                ]
            )
            == 0
        )
    step = json.loads(buffer.getvalue())
    assert step["group"] == "initiating"

    assert (
        cli.main(
            [
                "wizard",
                "apply",
                "--project",
                "GMS",
                "--kind",
                "stakeholder_register",
                "--field",  # named, not invented: the producer refuses a nameless one
                "name=Ada Lovelace",
                "--as-of",
                AS_OF.isoformat(),
                "--db-url",
                url,
            ]
        )
        == 0
    )
    with new_session_factory(e)() as db:
        project = db.scalars(select(Project)).one()
        assert mapping.resolve("stakeholder_register", project, db, AS_OF).present
