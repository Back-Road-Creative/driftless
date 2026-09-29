"""Per-project delivery records: baselines, milestones and sprints.

A baseline is **time-phased**, not a total. ``Baseline`` is a header and
``BaselineLine`` carries one row per task with its planned window and planned
cost, because ``driftless.calc.evm`` recovers PV(t) by accruing each task across
that window — from a budget figure alone PV is mathematically undefined.

Re-baselining inserts a new version rather than editing the old one:
``(project_id, version)`` is unique, so plan history is additive by
construction. The schema holds the *approval fact* — ``approved_at`` plus that
constraint. It cannot hold immutability, since no CHECK can distinguish an
UPDATE of an approved row from an INSERT. Refusing writes to a baseline whose
``approved_at`` is set is the API layer's job, left there deliberately rather
than half-enforced by an ORM hook a later PR would have to fight.

Velocity is not stored on ``Sprint``: it is ``completed_points`` read back per
sprint, so it can never drift from the points it is derived from.

Vocabularies are CHECK constraints, matching ``hierarchy`` — no write path,
including a manual ``psql`` session, can produce an invalid row.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, Task, one_of

if TYPE_CHECKING:  # annotations only — ``records`` imports this module, so the name
    from driftless.models.agile import Release  # resolves off the class registry
    from driftless.models.records import ChangeRequest  # (``agile`` imports this module too)

BASELINE_STATUSES = ("draft", "approved", "superseded")
MILESTONE_STATUSES = ("pending", "at_risk", "met", "missed")


class Baseline(Base):
    """One versioned snapshot of a project's approved plan."""

    __tablename__ = "baseline"
    __table_args__ = (
        one_of("status", BASELINE_STATUSES),
        CheckConstraint("version > 0", name="ck_baseline_version"),
        UniqueConstraint("project_id", "version", name="uq_baseline_project_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    lines: Mapped[list["BaselineLine"]] = relationship(back_populates="baseline")
    # The change requests this version was produced by. Read-only: the writable side of
    # ``change_request.resulting_baseline_id`` is the request's own ``resulting_baseline``,
    # so one column keeps one owner. Declared so the delete guard names them — the link
    # from a change to the plan version it caused is the audit trail for approved scope.
    resulting_change_requests: Mapped[list["ChangeRequest"]] = relationship(
        "ChangeRequest", viewonly=True
    )


class BaselineLine(Base):
    """One task's slice of a baseline — when it was to run, and what it was to cost."""

    __tablename__ = "baseline_line"
    __table_args__ = (
        CheckConstraint("planned_finish >= planned_start", name="ck_planned_window"),
        CheckConstraint("planned_cost >= 0", name="ck_planned_cost"),
        UniqueConstraint("baseline_id", "task_id", name="uq_baseline_line_task"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    baseline_id: Mapped[int] = mapped_column(ForeignKey("baseline.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    planned_start: Mapped[date]
    planned_finish: Mapped[date]
    planned_cost: Mapped[float]
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    baseline: Mapped[Baseline] = relationship(back_populates="lines")
    task: Mapped[Task] = relationship()


class Milestone(Base):
    """A dated commitment: ``target_date`` is where it stands now, ``baseline_date`` where it was promised."""

    __tablename__ = "milestone"
    __table_args__ = (one_of("status", MILESTONE_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_date: Mapped[date]
    baseline_date: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()


class Sprint(Base):
    """An agile time-box. Velocity is derived from ``completed_points``, never stored.

    ``goal``, ``release_id`` and the review/retrospective columns are what an
    "iteration" needs beyond the plain time-box: a stated goal, the ``Release``
    it belongs to, and the evidence that the two closing ceremonies actually
    happened (``driftless.models.agile`` module docstring — added here rather
    than as a parallel table, because an iteration IS this row).
    """

    __tablename__ = "sprint"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_sprint_window"),
        CheckConstraint("committed_points >= 0", name="ck_committed_points"),
        CheckConstraint("completed_points >= 0", name="ck_completed_points"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date]
    end_date: Mapped[date]
    committed_points: Mapped[int] = mapped_column(default=0)
    completed_points: Mapped[int] = mapped_column(default=0)
    goal: Mapped[str | None] = mapped_column(String(2000), default=None)
    release_id: Mapped[int | None] = mapped_column(
        ForeignKey("release.id"), default=None, index=True
    )
    review_held_on: Mapped[date | None] = mapped_column(default=None)
    review_notes: Mapped[str | None] = mapped_column(String(2000), default=None)
    retrospective_held_on: Mapped[date | None] = mapped_column(default=None)
    retrospective_notes: Mapped[str | None] = mapped_column(String(2000), default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # Writable side of the release link: attach a sprint to a release by setting
    # ``sprint.release``; ``Release.sprints`` is the read-only mirror (its own
    # module docstring), so the FK has one owner.
    release: Mapped["Release | None"] = relationship("Release")
