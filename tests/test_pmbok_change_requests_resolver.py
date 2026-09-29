"""Tier A resolver: ``change_requests`` now resolves against the store, dropped from
``mapping.UNTRACKED_DISPOSITIONS`` into ``mapping.RESOLVERS``. It reads the same dated
``ChangeRequest`` rows ``change_log`` already surfaces, under the catalog's own kind
name for the raw list — every process that names it (11.5-11.7) lists it as an
``optional_outputs`` entry, so this never blocks a process short a filed change.

``risk_report`` (the plan's other Tier A resolver) is a resolver too now, added in
``tests/test_pmbok_risk_report_resolver.py`` — see that module for how the risk area's
``optional_outputs`` needed to change alongside it.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import mapping

AS_OF = date(2026, 3, 31)


def test_change_requests_is_a_resolver_not_a_disposition() -> None:
    assert "change_requests" in mapping.RESOLVERS
    assert "change_requests" not in mapping.UNTRACKED_DISPOSITIONS
    # untouched by this unit
    assert "approved_change_requests" in mapping.UNTRACKED_DISPOSITIONS


def test_change_requests_waits_for_raised_on(project: m.Project, db: Session) -> None:
    raised = AS_OF - timedelta(days=10)
    db.add(m.ChangeRequest(project=project, description="scope trim", raised_on=raised))
    db.commit()
    assert not mapping.resolve("change_requests", project, db, raised - timedelta(days=1)).present
    assert mapping.resolve("change_requests", project, db, raised).present
