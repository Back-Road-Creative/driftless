"""Agile execution records: roles, backlog items, releases, definition-of-done
and impediments — everything an agile team keeps that is not a Sprint.

An "iteration" **is** a Sprint (``models/delivery.py``): it already carries the
window and the velocity, so this module never builds a parallel timebox table.
What Sprint lacks — a stated goal, a ``release`` it belongs to, and the
review/retrospective evidence that closes it out — is added to ``Sprint``
itself instead, exactly the way this module's docstring in ``delivery.py``
would have to if it grew a second "sprint-shaped" table beside the first. A
``Release`` groups sprints (a quarter, a season, a version) and is the one new
timebox concept, sitting one level above the iteration rather than beside it.

``ProjectRole.holder`` is a plain name, not a foreign key to ``Person``: the
same "who, in words" choice ``Risk.owner`` and ``SignOff.signed_by`` already
make, because a product owner or Scrum Master is frequently someone outside
the resourced team ``Person`` models (a client, a rotating facilitator), and
forcing a ``Person`` row for every role holder would be a fiction the
Resource knowledge area's capacity maths never asked for.

``BacklogItem``, ``DefinitionOfDoneItem`` and ``Impediment`` are current state,
like ``Risk`` and ``Issue`` (see ``docs/temporal-model.md``'s record
classification): mutable, and undated but for ``BacklogItem``'s three flow dates.
Those carry effective time — when the work MOVED — because ``pmbok.flow_facts``
used to replay them out of the ``ChangeLog``, which dates an item by when its row
was WRITTEN, leaving a store seeded or restored today with no history to read at
an earlier anchor; the replay is now only the fallback for rows predating the
columns. ``Impediment`` carries effective-time
dates (``raised_on``/``resolved_on``) for the same reason ``Issue`` does — an
as-of report over the current numbers, not a versioned history.

Vocabularies are CHECK constraints, matching every other model module — no
write path, including a manual ``psql`` session, can store a value outside
them.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

if TYPE_CHECKING:  # annotations only — ``delivery`` imports this module too, so a
    from driftless.models.delivery import Sprint  # runtime import back would be a cycle
    from driftless.models.scope import RequirementTrace

AGILE_ROLES = ("product_owner", "scrum_master", "developer", "stakeholder_proxy")
BACKLOG_ITEM_STATUSES = ("proposed", "ready", "in_progress", "done")
#: created -> started -> done, or absent: ``calc.flow.WorkItem`` refuses an inverted set.
FLOW_DATES_IN_ORDER = (
    "(started_on IS NULL OR created_on IS NULL OR started_on >= created_on)"
    " AND (done_on IS NULL OR created_on IS NULL OR done_on >= created_on)"
    " AND (done_on IS NULL OR started_on IS NULL OR done_on >= started_on)"
)
BACKLOG_ITEM_PRIORITIES = ("must_have", "should_have", "could_have", "wont_have")
RELEASE_STATUSES = ("planned", "released", "cancelled")
IMPEDIMENT_STATUSES = ("open", "in_progress", "resolved", "closed")


class ProjectRole(Base):
    """One agile role held on a project — who is the product owner, who runs standup."""

    __tablename__ = "project_role"
    __table_args__ = (one_of("role", AGILE_ROLES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    holder: Mapped[str] = mapped_column(String(200))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()


class BacklogItem(Base):
    """One unit of agile demand: not yet a ``Task``, and never becomes one by edit.

    A backlog item is the story the team estimates and orders; a ``Task`` is
    the work a project executes once accepted into a plan. Keeping them
    separate tables is what lets ``estimate``/``estimate_unit`` stay Task's
    execution-side numbers (hours for predictive, points for agile per-task)
    while ``story_points`` here is the whole-item estimate a backlog is
    ordered and forecast by, before it has been broken into tasks at all.
    """

    __tablename__ = "backlog_item"
    __table_args__ = (
        one_of("status", BACKLOG_ITEM_STATUSES),
        one_of("priority", BACKLOG_ITEM_PRIORITIES),
        CheckConstraint("story_points IS NULL OR story_points >= 0", name="ck_backlog_item_points"),
        CheckConstraint(FLOW_DATES_IN_ORDER, name="ck_backlog_item_flow_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    priority: Mapped[str] = mapped_column(String(20), default="should_have")
    story_points: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    # Nullable: a row predating these has a null ``created_on``, ``flow_facts``'s cue to replay.
    created_on: Mapped[date | None] = mapped_column(default=None)
    started_on: Mapped[date | None] = mapped_column(default=None)
    done_on: Mapped[date | None] = mapped_column(default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # Read-only from the backlog item side, same reason ``Task.subject_of_estimates``
    # is: the writable side of a requirement trace naming this item is its own
    # ``backlog_item``, so this stays read-only and exists only so the delete guard
    # names "still has traces_as_target".
    traces_as_target: Mapped[list["RequirementTrace"]] = relationship(
        "RequirementTrace", viewonly=True
    )


class Release(Base):
    """A named grouping of sprints — a version, a quarter, a season."""

    __tablename__ = "release"
    __table_args__ = (one_of("status", RELEASE_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_date: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # Read-only from the release side: the writable side of ``sprint.release_id``
    # is the sprint's own ``release``, and one column keeps one owner. Declared
    # so the delete guard names a release's sprints rather than 409ing opaquely.
    sprints: Mapped[list["Sprint"]] = relationship("Sprint", viewonly=True)


class DefinitionOfDoneItem(Base):
    """One project-wide "done means" criterion every backlog item is held to."""

    __tablename__ = "definition_of_done_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()


class Impediment(Base):
    """A blocker raised against the team's progress. ``raised_by`` is a name, not an FK."""

    __tablename__ = "impediment"
    __table_args__ = (
        one_of("status", IMPEDIMENT_STATUSES),
        CheckConstraint(
            "resolved_on IS NULL OR resolved_on >= raised_on", name="ck_impediment_dates"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    raised_by: Mapped[str] = mapped_column(String(200))
    raised_on: Mapped[date]
    resolved_on: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
