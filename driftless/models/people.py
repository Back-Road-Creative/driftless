"""Org model: departments and the people who staff the work.

These are the rows the Resource knowledge area is computed from. A task points
at the ``Person`` doing it (``hierarchy.Task.assignee_id``) and a project at the
``Department`` accountable for it (``hierarchy.Project.responsible_department_id``),
so labour cost and over-allocation are group-bys over live rows rather than a
second, hand-kept ledger.

``Person.capacity_hours`` is what makes "over-allocated" a number rather than a
guess: the Resource evaluator weighs the remaining hours a person is on the hook
for against this capacity, so a >100% reading is derived, never stored. It is
carried here — the smallest field that lets that ratio exist — alongside the
``cost_rate`` the labour-cost rollup multiplies by. ``cost_rate`` is a rate per
hour in the project's currency.

A department belongs to a business (the store is business-rooted throughout), so
the Department report can roll a business's projects up by the department
accountable for each. ``Person.department_id`` is nullable because a contractor
or an as-yet-unplaced hire has no home department, and forcing one would be a
fiction. Vocabularies — none here beyond the numeric CHECKs — follow the CHECK
posture of ``hierarchy``: no write path, ``psql`` included, can store a negative
rate or a non-positive capacity.
"""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Business

if TYPE_CHECKING:  # annotations only — Task and Project resolve off the class registry
    from driftless.models.hierarchy import Project, Task


class Department(Base):
    """A unit a business staffs and holds accountable for projects."""

    __tablename__ = "department"
    __table_args__ = (UniqueConstraint("business_id", "name", name="uq_department_business_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    name: Mapped[str] = mapped_column(String(200))

    business: Mapped[Business] = relationship()
    people: Mapped[list["Person"]] = relationship(back_populates="department")
    # The projects this department is accountable for — accountability, not ownership:
    # a project lives in its portfolio and merely names a department answerable for it.
    # Read-only, so the writable side of ``project.responsible_department_id`` stays the
    # project's own ``responsible_department`` and one column keeps one owner; declared
    # so the delete guard names these rather than 409ing opaquely.
    accountable_projects: Mapped[list["Project"]] = relationship("Project", viewonly=True)


class Person(Base):
    """Someone who does the work. ``capacity_hours`` is what allocation is measured against."""

    __tablename__ = "person"
    __table_args__ = (
        CheckConstraint("cost_rate >= 0", name="ck_person_cost_rate"),
        CheckConstraint("capacity_hours > 0", name="ck_person_capacity_hours"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("department.id"), default=None, index=True
    )
    role: Mapped[str | None] = mapped_column(String(100), default=None)
    cost_rate: Mapped[float] = mapped_column(default=0.0)
    capacity_hours: Mapped[float] = mapped_column(default=40.0)

    department: Mapped[Department | None] = relationship(back_populates="people")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="assignee", viewonly=True)
