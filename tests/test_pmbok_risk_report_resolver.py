"""Tier A resolver: ``risk_report`` now resolves against the store, dropped from
``mapping.UNTRACKED_DISPOSITIONS`` into ``mapping.RESOLVERS``. It reads the same
``Risk`` rows :func:`mapping._risk_register` already reads, plus a probability-
weighted exposure total computed on read — never stored.

Every risk-area process (11.2-11.7) lists ``risk_report`` as a REQUIRED output
beside ``risk_register`` in ``driftless/pmbok/areas/risk.py``. Adding the resolver
with no producer of its own would flip those processes from "produce" to "derived"
in ``tests/test_e2e_knowledge_areas.py``'s categorisation and starve the risk-area
wizard walk of any ``Risk`` row to seed, so ``risk_report`` is also marked
``optional_outputs`` everywhere it appears in that module, mirroring how
``change_requests`` is already optional there.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import mapping
from tests.conftest import AS_OF


def test_risk_report_is_a_resolver_not_a_disposition() -> None:
    assert "risk_report" in mapping.RESOLVERS
    assert "risk_report" not in mapping.UNTRACKED_DISPOSITIONS


def test_risk_report_absent_with_no_risks(project: m.Project, db: Session) -> None:
    status = mapping.resolve("risk_report", project, db, AS_OF)
    assert not status.present
    assert not status.healthy


def test_risk_report_present_reads_the_register_and_derives_exposure(
    project: m.Project, db: Session
) -> None:
    db.add(
        m.Risk(
            project=project,
            description="vendor slips",
            probability=0.5,
            impact=1000.0,
        )
    )
    db.commit()
    status = mapping.resolve("risk_report", project, db, AS_OF)
    assert status.present
    assert status.healthy
    assert "500.00" in status.detail  # 0.5 * 1000.0, derived on read


def test_risk_report_unhealthy_when_a_risk_has_realised(project: m.Project, db: Session) -> None:
    db.add(
        m.Risk(
            project=project,
            description="vendor slipped",
            probability=1.0,
            impact=1000.0,
            status="realised",
        )
    )
    db.commit()
    status = mapping.resolve("risk_report", project, db, AS_OF)
    assert status.present
    assert not status.healthy
