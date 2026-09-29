"""Scope records: requirements, their traces, the WBS/deliverable tree and its
acceptance ledger — the Scope Management knowledge area's own rows, none of
which the flat Task/Baseline shape carries today.

``Requirement`` is one stated need, filed against a project and (optionally) the
stakeholder it came from. It is current state, like ``Risk``/``Issue``
(``docs/temporal-model.md``'s record classification): mutable, not as-of tracked,
because a requirement's status moves forward in place rather than being
superseded by a new row.

``RequirementTrace`` is one line of the traceability matrix: a requirement points
at exactly one of a deliverable, a task or a backlog item — never zero, never
more than one — because a trace names WHERE a requirement is satisfied, and a row
that named two things would not say which one actually carries it. The CASE-WHEN
CHECK is the only way a CHECK can count "exactly one of three columns", the same
tier ``ck_budget_line_one_scope`` reaches for two.

``Deliverable`` IS the WBS node: a deliverable at the leaf of a decomposition is
a WBS work package, and a deliverable with children is a summary node — one tree,
addressed by ``wbs_code`` and ``parent_id``, never two tables that would drift
apart over the same decomposition. Its own docstring below is where "WbsEntry is
the same table as Deliverable" is said once, rather than in every module that
reads it.

``AcceptanceRecord`` is append-only, like ``SignOff``: verifying, then accepting,
a deliverable is a sequence of dated facts, and re-running Validate Scope on the
same deliverable files a NEW record rather than editing the old one — the
append-and-supersede shape every other decision ledger in this schema uses, so
prior acceptance history can never be rewritten by a later verification pass.

Vocabularies are CHECK constraints, matching every other model module — no write
path, including a manual ``psql`` session, can store a value outside them.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

if TYPE_CHECKING:  # names for the annotations only — never imported at runtime
    from driftless.models.agile import BacklogItem
    from driftless.models.hierarchy import Task
    from driftless.models.records import Stakeholder
    from driftless.models.team import ResponsibilityAssignment

REQUIREMENT_CATEGORIES = (
    "business",
    "stakeholder",
    "functional",
    "nonfunctional",
    "quality",
    "transition",
)
REQUIREMENT_PRIORITIES = ("must_have", "should_have", "could_have", "wont_have")
REQUIREMENT_STATUSES = ("proposed", "approved", "traced", "verified", "withdrawn")
DELIVERABLE_STATUSES = ("planned", "in_progress", "verified", "accepted", "rejected")


class Requirement(Base):
    """One stated need, filed against a project and — optionally — the
    stakeholder it came from."""

    __tablename__ = "requirement"
    __table_args__ = (
        one_of("category", REQUIREMENT_CATEGORIES),
        one_of("priority", REQUIREMENT_PRIORITIES),
        one_of("status", REQUIREMENT_STATUSES),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    statement: Mapped[str] = mapped_column(String(2000))
    category: Mapped[str] = mapped_column(String(20), default="functional")
    priority: Mapped[str] = mapped_column(String(20), default="should_have")
    source_stakeholder_id: Mapped[int | None] = mapped_column(
        ForeignKey("stakeholder.id"), default=None, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    actor: Mapped[str] = mapped_column(String(200))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # A stakeholder is a link, not a parent — the same shape ``Issue.risk_id``
    # already uses — because a requirement may name no source stakeholder at all.
    source_stakeholder: Mapped["Stakeholder | None"] = relationship("Stakeholder")
    # Read-only from the requirement side, same reason ``Risk.risk_responses`` is:
    # the writable side of each trace is its own ``requirement``, and declaring
    # the collection here is what lets the delete guard name "still has traces"
    # instead of an opaque constraint 409.
    traces: Mapped[list["RequirementTrace"]] = relationship(
        "RequirementTrace", back_populates="requirement"
    )


class RequirementTrace(Base):
    """One line of the traceability matrix: a requirement, and exactly one of a
    deliverable, a task or a backlog item that satisfies it."""

    __tablename__ = "requirement_trace"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN deliverable_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN backlog_item_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_requirement_trace_one_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirement.id"), index=True)
    deliverable_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliverable.id"), default=None, index=True
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("task.id"), default=None, index=True)
    backlog_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("backlog_item.id"), default=None, index=True
    )
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    requirement: Mapped[Requirement] = relationship(back_populates="traces")
    # The writable side of each target link; ``Deliverable.traces_as_target``,
    # ``Task.traces_as_target`` and ``BacklogItem.traces_as_target`` are separate,
    # read-only collections declared on those models purely so the delete guard
    # sees and names them — the same "no back_populates pairing" shape
    # ``EstimateScenario.subject_task``/``Task.subject_of_estimates`` already use.
    deliverable: Mapped["Deliverable | None"] = relationship("Deliverable")
    task: Mapped["Task | None"] = relationship("Task")
    backlog_item: Mapped["BacklogItem | None"] = relationship("BacklogItem")


class Deliverable(Base):
    """One node of the WBS/decomposition tree — a summary node with children, or
    a leaf work package. ``WbsEntry`` is not a separate table: a deliverable IS a
    WBS entry, addressed by ``wbs_code`` and ``parent_id``, and a reader that wants
    "the WBS" reads this table's tree rather than a twin of it (module docstring).
    """

    __tablename__ = "deliverable"
    __table_args__ = (
        one_of("status", DELIVERABLE_STATUSES),
        CheckConstraint("parent_id != id", name="ck_deliverable_not_own_parent"),
        UniqueConstraint("project_id", "wbs_code", name="uq_deliverable_project_wbs_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    wbs_code: Mapped[str] = mapped_column(String(50))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliverable.id"), default=None, index=True
    )
    description: Mapped[str] = mapped_column(String(2000), default="")
    acceptance_criteria: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(20), default="planned")
    accepted_on: Mapped[date | None] = mapped_column(default=None)
    accepted_by: Mapped[str | None] = mapped_column(String(200), default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    parent: Mapped["Deliverable | None"] = relationship(
        "Deliverable", remote_side="Deliverable.id", back_populates="children"
    )
    children: Mapped[list["Deliverable"]] = relationship("Deliverable", back_populates="parent")
    # Read-only from the deliverable side, same reason as ``Requirement.traces``:
    # the writable side is each trace's own ``deliverable``, and declaring the
    # collection here lets the delete guard name "still has traces_as_target".
    traces_as_target: Mapped[list["RequirementTrace"]] = relationship(
        "RequirementTrace", viewonly=True
    )
    # Read-only from the deliverable side, same reason as above: the writable
    # side of an acceptance record is its own ``deliverable``, and declaring the
    # collection here lets the delete guard name "still has acceptance_records".
    acceptance_records: Mapped[list["AcceptanceRecord"]] = relationship(
        "AcceptanceRecord", viewonly=True
    )
    # Same reason as traces_as_target above: the writable side of a responsibility
    # assignment naming this deliverable is its own ``deliverable``, so this stays
    # read-only and exists only so the delete guard names it.
    responsibility_assignments_as_target: Mapped[list["ResponsibilityAssignment"]] = relationship(
        "ResponsibilityAssignment", viewonly=True
    )


class AcceptanceRecord(Base):
    """One append-only entry in a deliverable's verify/accept ledger — a new
    row per pass, never an edit to a prior one (module docstring)."""

    __tablename__ = "acceptance_record"
    __table_args__ = (
        CheckConstraint(
            "verified_on IS NOT NULL OR accepted_on IS NOT NULL",
            name="ck_acceptance_record_has_date",
        ),
        CheckConstraint(
            "accepted_on IS NULL OR verified_on IS NULL OR accepted_on >= verified_on",
            name="ck_acceptance_record_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deliverable_id: Mapped[int] = mapped_column(ForeignKey("deliverable.id"), index=True)
    verified_on: Mapped[date | None] = mapped_column(default=None)
    accepted_on: Mapped[date | None] = mapped_column(default=None)
    actor: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(2000), default=None)

    deliverable: Mapped[Deliverable] = relationship()


#: A deliverable IS a WBS entry (module docstring) — one name for readers who
#: come to this module looking for "the WBS node type" rather than "the
#: deliverable table", so the two never drift into looking like separate things.
WbsEntry = Deliverable
