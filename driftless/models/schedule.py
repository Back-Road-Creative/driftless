"""Schedule records: typed task dependencies, project calendars and estimate
scenarios — the network and duration-estimation layer PMBOK's Schedule
Management knowledge area asks for, none of which the flat Task/Baseline
shape carries today.

``TaskDependency`` is a *typed* precedence edge between two tasks:
``kind`` is one of the four PMBOK precedence relationship types
(finish-to-start, start-to-start, finish-to-finish, start-to-finish) and
``lag_days`` is a signed offset where a negative value is a lead. The CHECK
below keeps a task from depending on itself; a cycle across several edges is
not expressible as a CHECK — it needs a graph walk — so that refusal lives at
the write boundary instead (``driftless.services.schedule_writes``), the
next-best tier once "robust by construction" is out of reach.

``ProjectCalendar`` names a working pattern for a project — ``working_days``
is a Monday-first bitmask of which weekdays are working days, 31 (Mon-Fri)
by default — and ``CalendarException`` lists the dated exceptions (a holiday
that is normally a working day, a Saturday shift that is not), so a duration
read can walk the true working-day count for a window instead of assuming
every day between two dates worked.

``EstimateScenario`` is the stored form of
``driftless.calc.estimating.EstimateScenario`` (#330, a sibling PR): one row
per estimate a PM ran, carrying its method, its value/low/high figures and
the actor/as-of provenance ``TechniqueRun`` already carries elsewhere. Field
names mirror that module's dataclass so a later import needs no renaming;
it is not imported here, since that module lives on a sibling branch.

Vocabularies are CHECK constraints, matching every other model module — no
write path, including a manual ``psql`` session, can store a value outside
them.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, Task, one_of

DEPENDENCY_KINDS = ("FS", "SS", "FF", "SF")
ESTIMATE_TARGETS = ("duration", "cost", "resource")
ESTIMATE_KINDS = ("analogous", "parametric", "three_point", "bottom_up")


class TaskDependency(Base):
    """A typed precedence edge: ``successor`` runs relative to ``predecessor``.

    Project scoping — both tasks must belong to the same project — and cycle
    refusal are cross-row rules a CHECK cannot express, so they live at the
    API boundary (``driftless.api.rules``) and the write-boundary service
    (``driftless.services.schedule_writes``), never here.
    """

    __tablename__ = "task_dependency"
    __table_args__ = (
        one_of("kind", DEPENDENCY_KINDS),
        CheckConstraint(
            "predecessor_task_id != successor_task_id", name="ck_task_dependency_not_self"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    predecessor_task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    successor_task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    kind: Mapped[str] = mapped_column(String(2), default="FS")
    lag_days: Mapped[int] = mapped_column(default=0)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    predecessor: Mapped[Task] = relationship("Task", foreign_keys=[predecessor_task_id])
    successor: Mapped[Task] = relationship("Task", foreign_keys=[successor_task_id])


class ProjectCalendar(Base):
    """A project's default working pattern: which weekdays it runs on."""

    __tablename__ = "project_calendar"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Bit 0 = Monday .. bit 6 = Sunday; 31 (0b0011111) is Mon-Fri, the default.
    working_days: Mapped[int] = mapped_column(default=31)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    exceptions: Mapped[list["CalendarException"]] = relationship(back_populates="calendar")


class CalendarException(Base):
    """One dated exception to its calendar's default working pattern."""

    __tablename__ = "calendar_exception"
    __table_args__ = (
        UniqueConstraint("calendar_id", "on_date", name="uq_calendar_exception_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("project_calendar.id"), index=True)
    on_date: Mapped[date]
    working: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str | None] = mapped_column(String(2000), default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    calendar: Mapped[ProjectCalendar] = relationship(back_populates="exceptions")


class EstimateScenario(Base):
    """One estimate a PM ran: its method, its figures, and who produced it when.

    ``subject_task_id`` is a nullable link, not a parent — an estimate may
    target the whole project (``target="cost"`` with no single task) or one
    task's duration/cost/resource figure. ``inputs`` is JSON text, matching
    ``TechniqueRun.inputs_snapshot`` and ``ChangeLog.detail``, so the table
    stays portable between SQLite and Postgres.
    """

    __tablename__ = "estimate_scenario"
    __table_args__ = (
        one_of("target", ESTIMATE_TARGETS),
        one_of("kind", ESTIMATE_KINDS),
        CheckConstraint("low IS NULL OR low <= value", name="ck_estimate_scenario_low"),
        CheckConstraint("high IS NULL OR high >= value", name="ck_estimate_scenario_high"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    target: Mapped[str] = mapped_column(String(20))
    subject_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("task.id"), default=None, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    inputs: Mapped[str] = mapped_column(Text, default="{}")
    value: Mapped[float]
    low: Mapped[float | None] = mapped_column(default=None)
    high: Mapped[float | None] = mapped_column(default=None)
    basis: Mapped[str] = mapped_column(String(2000), default="")
    actor: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date]
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    subject_task: Mapped["Task | None"] = relationship("Task")
