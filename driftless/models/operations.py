"""Department operations records: what a department runs day to day, distinct
from the projects it is merely accountable for (``Project.responsible_department_id``
— see ``models/people.py``).

``DepartmentService`` is the department's own service catalog: what it
provides, and who owns each one. ``WorkRequest`` is the demand queue against
that catalog, and deliberately carries the same three-date shape
``driftless.calc.flow.WorkItem`` reads — ``raised_on`` stands for
``created_on``, and ``started_on``/``done_on`` name themselves — so a caller
adapting a ``WorkRequest`` into a ``WorkItem`` renames nothing but that one
field; flow metrics (WIP, throughput, cycle and lead time) then apply to a
department's queue exactly as they would to a project's backlog, with no
second definition of any of them. The three CHECKs on ``WorkRequest`` are
``WorkItem.__post_init__``'s own ordering rules, enforced here too so no
write path — including a manual ``psql`` session — can store a request a
flow-metric read would refuse to adapt.

``RecurringWork`` and ``ServiceLevel`` share one cadence vocabulary
(``CADENCES``): a recurring task's cadence and an SLA's measurement window are
the same kind of fact — how often something repeats — so one vocabulary
serves both rather than two that could drift apart.

``OperatingControl`` and ``Incident`` are current state, like ``Risk`` and
``Issue`` (see ``docs/temporal-model.md``'s record classification): mutable,
not as-of tracked. ``Incident.control_id`` is a nullable LINK, not a parent —
the same shape ``Issue.risk_id`` and ``QualityMeasurement.quality_metric_id``
already use — because an incident can be raised with no pre-existing control
named as its cause. ``WorkRequest.service_id`` and ``ServiceLevel.service_id``
are the same shape again, against ``DepartmentService``.

Every row's real parent is its ``department_id``, not the link: a department
is what the delete guard and every rollup scope these records by, matching
the way ``project_id`` scopes every per-project record in ``records.py`` and
``agile.py``.

Vocabularies are CHECK constraints, matching every other model module — no
write path can store a value outside them.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import one_of
from driftless.models.people import Department

WORK_REQUEST_STATUSES = ("requested", "queued", "in_progress", "done", "cancelled")
WORK_REQUEST_PRIORITIES = ("low", "medium", "high", "urgent")
#: Shared by ``RecurringWork.cadence`` and ``ServiceLevel.window`` — module docstring.
CADENCES = ("weekly", "fortnightly", "monthly", "quarterly", "annual")
INCIDENT_SEVERITIES = ("low", "medium", "high", "critical")
INCIDENT_STATUSES = ("open", "investigating", "resolved", "closed")
IMPROVEMENT_STATUSES = ("proposed", "in_progress", "done", "abandoned")


class DepartmentService(Base):
    """One service a department provides, and who owns it."""

    __tablename__ = "department_service"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    owner: Mapped[str] = mapped_column(String(200))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()
    # Read-only from the service side, same reason ``OperatingControl.incidents`` is:
    # the writable side of each link is the linking row's own ``service``, and
    # declaring the collection here is what lets the delete guard name "still has
    # work_requests"/"still has service_levels" instead of an opaque constraint 409.
    work_requests: Mapped[list["WorkRequest"]] = relationship("WorkRequest", viewonly=True)
    service_levels: Mapped[list["ServiceLevel"]] = relationship("ServiceLevel", viewonly=True)


class WorkRequest(Base):
    """One item of demand against a department's services — the work queue."""

    __tablename__ = "work_request"
    __table_args__ = (
        one_of("status", WORK_REQUEST_STATUSES),
        one_of("priority", WORK_REQUEST_PRIORITIES),
        CheckConstraint(
            "started_on IS NULL OR started_on >= raised_on", name="ck_work_request_started"
        ),
        CheckConstraint(
            "done_on IS NULL OR done_on >= raised_on", name="ck_work_request_done_after_raised"
        ),
        CheckConstraint(
            "done_on IS NULL OR started_on IS NULL OR done_on >= started_on",
            name="ck_work_request_done_after_started",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("department_service.id"), default=None, index=True
    )
    requester: Mapped[str] = mapped_column(String(200))
    raised_on: Mapped[date]
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="requested")
    started_on: Mapped[date | None] = mapped_column(default=None)
    done_on: Mapped[date | None] = mapped_column(default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()
    service: Mapped[DepartmentService | None] = relationship()


class RecurringWork(Base):
    """A cadence a department runs on its own initiative, not raised by demand."""

    __tablename__ = "recurring_work"
    __table_args__ = (
        one_of("cadence", CADENCES),
        CheckConstraint(
            "next_due_on IS NULL OR last_completed_on IS NULL OR next_due_on >= last_completed_on",
            name="ck_recurring_work_dates",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    cadence: Mapped[str] = mapped_column(String(20), default="monthly")
    owner: Mapped[str] = mapped_column(String(200))
    last_completed_on: Mapped[date | None] = mapped_column(default=None)
    next_due_on: Mapped[date | None] = mapped_column(default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()


class ServiceLevel(Base):
    """A target a department (or one of its services) is held to, and how it is measured."""

    __tablename__ = "service_level"
    __table_args__ = (
        # "window" is a reserved word in PostgreSQL; the identifier must be quoted.
        CheckConstraint(
            '"window" IN ({})'.format(", ".join(f"'{c}'" for c in CADENCES)), name="ck_window"
        ),
        CheckConstraint("target >= 0", name="ck_service_level_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("department_service.id"), default=None, index=True
    )
    measure: Mapped[str] = mapped_column(String(200))
    target: Mapped[float]
    window: Mapped[str] = mapped_column(String(20), default="monthly")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()
    service: Mapped[DepartmentService | None] = relationship()


class OperatingControl(Base):
    """A mechanism a department runs to keep its operating risk in check."""

    __tablename__ = "operating_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    owner: Mapped[str] = mapped_column(String(200))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()
    # Read-only from the control side, same reason ``Release.sprints`` is: the
    # writable side of ``incident.control_id`` is the incident's own ``control``,
    # and declaring it here is what lets the delete guard name "still has
    # incidents" instead of an opaque constraint 409.
    incidents: Mapped[list["Incident"]] = relationship("Incident", viewonly=True)


class Incident(Base):
    """An operating-risk event, dated like ``Issue``. ``control_id`` is a link, not a parent."""

    __tablename__ = "incident"
    __table_args__ = (
        one_of("severity", INCIDENT_SEVERITIES),
        one_of("status", INCIDENT_STATUSES),
        CheckConstraint(
            "resolved_on IS NULL OR resolved_on >= raised_on", name="ck_incident_dates"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    control_id: Mapped[int | None] = mapped_column(
        ForeignKey("operating_control.id"), default=None, index=True
    )
    description: Mapped[str] = mapped_column(String(2000))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    raised_on: Mapped[date]
    resolved_on: Mapped[date | None] = mapped_column(default=None)
    root_cause: Mapped[str | None] = mapped_column(String(2000), default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()
    control: Mapped[OperatingControl | None] = relationship()


class Improvement(Base):
    """A proposed operating change: what, why, who owns it, and its status."""

    __tablename__ = "improvement"
    __table_args__ = (one_of("status", IMPROVEMENT_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    what: Mapped[str] = mapped_column(String(2000))
    why: Mapped[str] = mapped_column(String(2000))
    owner: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    department: Mapped[Department] = relationship()
