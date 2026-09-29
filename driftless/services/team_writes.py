"""Filing an assignment, an acquisition, a training record, a team assessment or a
conflict/action, for whichever surface asks.

The web assist page's POSTs call these directly, exactly the shape
``driftless.services.scope_writes`` already uses — each row lands through the same
validated schema and the same cross-row rule (``driftless.api.rules``) the JSON
routes run, so the two write paths are one.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import insert
from driftless.api.rules import responsibility_assignment_lands_valid
from driftless.models import (
    Acquisition,
    ConflictAction,
    ConflictRecord,
    Deliverable,
    Person,
    Project,
    ResourceType,
    ResponsibilityAssignment,
    Task,
    TeamAssessment,
    TrainingRecord,
)


def file_assignment(db: Session, payload: s.ResponsibilityAssignmentIn) -> ResponsibilityAssignment:
    """Validate and file one RACI line."""
    responsibility_assignment_lands_valid(db, payload)
    return insert(
        db,
        ResponsibilityAssignment,
        payload,
        project_id=Project,
        deliverable_id=Deliverable,
        task_id=Task,
        person_id=Person,
    )


def file_acquisition(db: Session, payload: s.AcquisitionIn) -> Acquisition:
    """Validate and file one acquisition event against a resource type."""
    return insert(db, Acquisition, payload, project_id=Project, resource_type_id=ResourceType)


def file_training_record(db: Session, payload: s.TrainingRecordIn) -> TrainingRecord:
    """Validate and file one training record against a person."""
    return insert(db, TrainingRecord, payload, person_id=Person)


def record_assessment(db: Session, payload: s.TeamAssessmentIn) -> TeamAssessment:
    """Append one team-assessment entry — never an edit to a prior one
    (``driftless.models.team`` module docstring)."""
    return insert(db, TeamAssessment, payload, project_id=Project)


def file_conflict(db: Session, payload: s.ConflictRecordIn) -> ConflictRecord:
    """Validate and file one conflict record."""
    return insert(db, ConflictRecord, payload, project_id=Project)


def file_conflict_action(db: Session, payload: s.ConflictActionIn) -> ConflictAction:
    """Validate and file one follow-up action against a filed conflict."""
    return insert(db, ConflictAction, payload, conflict_id=ConflictRecord, owner_id=Person)
