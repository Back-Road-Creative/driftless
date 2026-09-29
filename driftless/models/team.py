"""Resource Management records: the resource catalog and its breakdown tree, the
stored RACI, acquisition, training, team assessment and conflict rows.

``ResourceType`` is the catalog a project draws from — people, equipment or
material, each with a unit and a rate — and ``ResourceBreakdown`` is the tree
built over it (the RBS), the same self-referential ``parent_id`` shape
``Deliverable``'s WBS tree already uses (``driftless.models.scope`` module
docstring): a summary node with children, or a leaf carrying a quantity.

``ResponsibilityAssignment`` is the stored RACI: one row names a person's role
against exactly one of a deliverable or a task — the same "exactly one target"
CASE-WHEN CHECK ``RequirementTrace`` already uses, narrowed to two columns the
way ``ck_budget_line_one_scope`` narrows the same tier. It replaces the
DERIVED RACI ``pmbok.mapping``'s ``team_charter`` resolver used to fall back
to: once a project has filed rows, the resolver reads them; a project with
none still reads the stored narrative.

``Acquisition`` is one resource-type's staffing/procurement event — internal
reassignment or an external source, requested and (once fulfilled) dated.
``TrainingRecord`` is a person's own ledger, not project-scoped: training
develops the person, who then carries it onto whichever project needs them.
``TeamAssessment`` is append-only, like ``AcceptanceRecord``: a dated reading
against one dimension, filed fresh each time rather than edited in place, so a
trend line never rewrites its own history.

``ConflictRecord`` is current state, like ``Risk``/``Issue`` (see
``docs/temporal-model.md``'s record classification): a conflict is raised,
handled by one Tuckman/Thomas-Kilmann approach, and optionally resolved in
place. ``ConflictAction`` is the follow-up ledger against it — who owns
closing it out and by when — the same "child record, own owner and dates"
shape ``RiskResponse`` already carries beside ``Risk``.

Vocabularies are CHECK constraints, matching every other model module — no
write path, including a manual ``psql`` session, can store a value outside
them.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

if TYPE_CHECKING:  # names for the annotations only — never imported at runtime
    from driftless.models.hierarchy import Task
    from driftless.models.people import Person
    from driftless.models.scope import Deliverable

RESOURCE_KINDS = ("people", "equipment", "material")
RACI_ROLES = ("responsible", "accountable", "consulted", "informed")
ACQUISITION_SOURCES = ("internal", "external")
ACQUISITION_STATUSES = ("requested", "approved", "fulfilled", "cancelled")
CONFLICT_APPROACHES = ("withdraw", "smooth", "compromise", "force", "collaborate")


class ResourceType(Base):
    """One catalog entry a project's RBS and acquisitions draw from."""

    __tablename__ = "resource_type"
    __table_args__ = (
        one_of("kind", RESOURCE_KINDS),
        CheckConstraint("rate >= 0", name="ck_resource_type_rate"),
        UniqueConstraint("project_id", "name", name="uq_resource_type_project_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    unit: Mapped[str] = mapped_column(String(50), default="each")
    rate: Mapped[float] = mapped_column(default=0.0)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # Read-only from the resource-type side, the same reason ``Requirement.traces``
    # is: the writable side is each row's own ``resource_type``, and declaring the
    # collection here lets the delete guard name what it still has.
    breakdown_nodes: Mapped[list["ResourceBreakdown"]] = relationship(
        "ResourceBreakdown", viewonly=True
    )
    acquisitions: Mapped[list["Acquisition"]] = relationship("Acquisition", viewonly=True)


class ResourceBreakdown(Base):
    """One node of the RBS tree — a summary node with children, or a leaf
    quantity of one ``ResourceType``. Self-referential ``parent_id``, the same
    shape ``Deliverable``'s WBS tree already uses."""

    __tablename__ = "resource_breakdown"
    __table_args__ = (
        CheckConstraint("parent_id != id", name="ck_resource_breakdown_not_own_parent"),
        CheckConstraint("quantity > 0", name="ck_resource_breakdown_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    resource_type_id: Mapped[int] = mapped_column(ForeignKey("resource_type.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_breakdown.id"), default=None, index=True
    )
    quantity: Mapped[float] = mapped_column(default=1.0)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    resource_type: Mapped[ResourceType] = relationship(back_populates="breakdown_nodes")
    parent: Mapped["ResourceBreakdown | None"] = relationship(
        "ResourceBreakdown", remote_side="ResourceBreakdown.id", back_populates="children"
    )
    children: Mapped[list["ResourceBreakdown"]] = relationship(
        "ResourceBreakdown", back_populates="parent"
    )


class ResponsibilityAssignment(Base):
    """One line of the stored RACI: a person's role against exactly one of a
    deliverable or a task."""

    __tablename__ = "responsibility_assignment"
    __table_args__ = (
        one_of("role", RACI_ROLES),
        CheckConstraint(
            "(CASE WHEN deliverable_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_responsibility_assignment_one_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    deliverable_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliverable.id"), default=None, index=True
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("task.id"), default=None, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    deliverable: Mapped["Deliverable | None"] = relationship("Deliverable")
    task: Mapped["Task | None"] = relationship("Task")
    # Writable side of the person link; the read-only reverse (``Person.responsibility_assignments``)
    # exists only so the delete guard sees it, the same shape ``RiskResponse.owner`` uses.
    person: Mapped["Person"] = relationship("Person", back_populates="responsibility_assignments")


class Acquisition(Base):
    """One staffing/procurement event against a resource type: internal
    reassignment or an external source, requested and (once fulfilled) dated."""

    __tablename__ = "acquisition"
    __table_args__ = (
        one_of("source", ACQUISITION_SOURCES),
        one_of("status", ACQUISITION_STATUSES),
        CheckConstraint(
            "fulfilled_on IS NULL OR fulfilled_on >= requested_on", name="ck_acquisition_dates"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    resource_type_id: Mapped[int] = mapped_column(ForeignKey("resource_type.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))
    requested_on: Mapped[date]
    fulfilled_on: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="requested")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    resource_type: Mapped[ResourceType] = relationship(back_populates="acquisitions")


class TrainingRecord(Base):
    """One person's completed training — the person's own ledger, not project-scoped:
    training develops the person, who then carries it onto whichever project needs them."""

    __tablename__ = "training_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    topic: Mapped[str] = mapped_column(String(200))
    completed_on: Mapped[date]
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    person: Mapped["Person"] = relationship("Person", back_populates="training_records")


class TeamAssessment(Base):
    """One append-only reading of the team on one dimension — a new row per
    assessment, never an edit to a prior one, the same shape ``AcceptanceRecord``
    already uses so a trend line never rewrites its own history."""

    __tablename__ = "team_assessment"
    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 100", name="ck_team_assessment_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    assessed_on: Mapped[date]
    dimension: Mapped[str] = mapped_column(String(100))
    score: Mapped[float]
    note: Mapped[str | None] = mapped_column(String(2000), default=None)
    actor: Mapped[str] = mapped_column(String(200))

    project: Mapped[Project] = relationship()


class ConflictRecord(Base):
    """One team conflict: who is involved, the approach taken and — once handled
    — the date it resolved. Current state, like ``Risk``/``Issue``."""

    __tablename__ = "conflict_record"
    __table_args__ = (
        one_of("approach", CONFLICT_APPROACHES),
        CheckConstraint(
            "resolved_on IS NULL OR resolved_on >= raised_on", name="ck_conflict_record_dates"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    raised_on: Mapped[date]
    parties: Mapped[str] = mapped_column(String(2000))
    approach: Mapped[str] = mapped_column(String(20), default="collaborate")
    resolved_on: Mapped[date | None] = mapped_column(default=None)
    actor: Mapped[str] = mapped_column(String(200))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # Read-only from the conflict side, same reason ``Requirement.traces`` is: the
    # writable side is each action's own ``conflict``, and declaring the collection
    # here lets the delete guard name "still has actions".
    actions: Mapped[list["ConflictAction"]] = relationship("ConflictAction", viewonly=True)


class ConflictAction(Base):
    """One follow-up against a filed conflict: who owns closing it out, and by when."""

    __tablename__ = "conflict_action"

    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_id: Mapped[int] = mapped_column(ForeignKey("conflict_record.id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    due_on: Mapped[date | None] = mapped_column(default=None)
    done_on: Mapped[date | None] = mapped_column(default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    conflict: Mapped[ConflictRecord] = relationship("ConflictRecord")
    # Writable side of the owner link; the read-only reverse (``Person.conflict_actions``)
    # exists only so the delete guard sees it, the same shape ``RiskResponse.owner`` uses.
    owner: Mapped["Person"] = relationship("Person", back_populates="conflict_actions")
