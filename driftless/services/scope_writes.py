"""Filing a requirement, a trace or an acceptance record, for whichever surface asks.

The web assist page's three POSTs call these directly, exactly the shape
``driftless.services.risk_writes`` already uses — each row lands through the same
validated schema and the same cross-row rule (``driftless.api.rules``) the JSON
routes run, so the two write paths are one.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import insert
from driftless.api.rules import deliverable_lands_valid, requirement_trace_lands_valid
from driftless.models import (
    AcceptanceRecord,
    BacklogItem,
    Deliverable,
    Project,
    Requirement,
    RequirementTrace,
    Stakeholder,
    Task,
)


def file_requirement(db: Session, payload: s.RequirementIn) -> Requirement:
    """Validate and file one requirement against a project."""
    return insert(
        db,
        Requirement,
        payload,
        project_id=Project,
        source_stakeholder_id=Stakeholder,
    )


def file_requirement_trace(db: Session, payload: s.RequirementTraceIn) -> RequirementTrace:
    """Validate and file one line of the traceability matrix."""
    requirement_trace_lands_valid(db, payload)
    return insert(
        db,
        RequirementTrace,
        payload,
        requirement_id=Requirement,
        deliverable_id=Deliverable,
        task_id=Task,
        backlog_item_id=BacklogItem,
    )


def file_deliverable(db: Session, payload: s.DeliverableIn) -> Deliverable:
    """Validate and file one WBS node (a deliverable)."""
    deliverable_lands_valid(db, payload)
    return insert(db, Deliverable, payload, project_id=Project, parent_id=Deliverable)


def record_acceptance(db: Session, payload: s.AcceptanceRecordIn) -> AcceptanceRecord:
    """Append one verify/accept entry to a deliverable's ledger — never an edit
    to a prior entry (``driftless.models.scope`` module docstring)."""
    return insert(db, AcceptanceRecord, payload, deliverable_id=Deliverable)
