"""Guard rails on the wizard-apply and weekly-status form POSTs (audit R1):
re-baselining an approved project is refused with nothing written; a refused
apply re-renders the form with the typed prose still in its textarea; and the
weekly-status POST validates through ``StatusSnapshotIn`` at the boundary."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless import models as m
from driftless.web import csrf

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
PROSE = "Vendor lead times hold at six weeks; the drone crew is weather-bound in March."


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        # One project whose plan baseline is APPROVED — what re-baselining destroys.
        project = m.Project(
            name="GMS",
            portfolio=m.Portfolio(name="Content", business=m.Business(name="BRC")),
            delivery_mode="predictive",
        )
        stream = m.Workstream(name="Post", project=project)
        task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
        baseline = m.Baseline(project=project, version=1, status="approved")
        session.add(
            m.BaselineLine(
                baseline=baseline,
                task=task,
                planned_cost=1000.0,
                planned_start=JAN,
                planned_finish=AS_OF,
            )
        )
        session.commit()
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    # https, as production serves: the CSRF cookie is Secure, an http jar drops it.
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def _pair(client: TestClient) -> dict[str, str]:
    return {csrf.FIELD: client.cookies[csrf.COOKIE]}


@pytest.mark.parametrize("kind", ["scope_baseline", "schedule_baseline"])
def test_wizard_apply_refuses_to_rebaseline_an_approved_project(
    client: TestClient, db: Session, kind: str
) -> None:
    """The form posts ``kind`` alone, so one direct POST naming a baseline kind used
    to file version N+1 as approved — rewriting BAC with no confirm and no undo."""
    client.get(f"/projects/1/wizard{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": kind, "as_of": AS_OF.isoformat()} | _pair(client),
    )
    assert resp.status_code == 409
    versions = db.scalars(select(m.Baseline.version).where(m.Baseline.project_id == 1)).all()
    assert versions == [1], "one click re-baselined an approved project"


def test_a_project_without_an_approved_plan_can_still_baseline(
    client: TestClient, db: Session
) -> None:
    """The guard refuses RE-baselining only: first baselines still go through."""
    bare = m.Project(name="Bare", portfolio_id=1, delivery_mode="predictive")
    db.add(bare)
    db.commit()
    client.get(f"/projects/{bare.id}/wizard{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/{bare.id}/wizard/apply{Q}",
        # planned_cost is posted because it IS BAC — the producer invents no figure.
        data={"kind": "scope_baseline", "as_of": AS_OF.isoformat(), "planned_cost": "4200"}
        | _pair(client),
        follow_redirects=False,
    )
    assert resp.status_code == 303
    versions = db.scalars(select(m.Baseline.version).where(m.Baseline.project_id == bare.id)).all()
    assert versions == [1]


def test_a_refused_apply_rerenders_the_form_with_the_typed_prose(
    client: TestClient, db: Session
) -> None:
    """An oversize body is refused 422 — handing the prose back in a textarea, not
    destroying it behind an error shell with no form at all."""
    from driftless.web.wizard_form import BODY_MAX

    oversize = PROSE + "x" * BODY_MAX
    client.get(f"/projects/1/wizard{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "assumption_log", "as_of": AS_OF.isoformat(), "body": oversize}
        | _pair(client),
    )
    assert resp.status_code == 422
    assert 'name="body"' in resp.text, "the 422 page lost the form"
    assert f">{oversize}</textarea>" in resp.text, "the typed prose was destroyed"
    assert not db.scalars(select(m.NarrativeArtifact)).all(), "the refusal still wrote a row"


def test_a_producer_refusal_renders_the_form_not_a_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``produce`` refuses by raising ``ValueError``s (``MissingBody`` today,
    producer guards tomorrow) — all must render the form, never escape as a 500."""
    from driftless.wizard import cli as wizard_cli

    def raiser(*args: object, **kwargs: object) -> int:
        raise ValueError("refused by the producer")

    monkeypatch.setattr(wizard_cli, "produce", raiser)
    client.get(f"/projects/1/wizard{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "stakeholder_register", "as_of": AS_OF.isoformat()} | _pair(client),
    )
    assert resp.status_code == 422
    assert "refused by the producer" in resp.text


def test_a_bad_rag_status_is_refused_422_at_the_boundary(client: TestClient, db: Session) -> None:
    client.get(f"/projects/1/status{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/status{Q}",
        data={"rag_status": "purple", "as_of": AS_OF.isoformat()} | _pair(client),
    )
    assert resp.status_code == 422, "an invalid RAG reached the ORM instead of the schema"
    assert not db.scalars(select(m.StatusSnapshot)).all()


def test_an_oversize_note_is_refused_422_at_the_boundary(client: TestClient, db: Session) -> None:
    """SQLite never enforces VARCHAR(2000): without the schema, an oversize note
    was silently STORED — the boundary is the only place the limit is real."""
    client.get(f"/projects/1/status{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/status{Q}",
        data={"rag_status": "green", "note": "n" * 2001, "as_of": AS_OF.isoformat()}
        | _pair(client),
    )
    assert resp.status_code == 422
    assert not db.scalars(select(m.StatusSnapshot)).all()
