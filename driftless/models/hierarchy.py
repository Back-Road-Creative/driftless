"""The ownership hierarchy: Business -> Portfolio -> Program -> Project -> Workstream -> Task.

Every child carries exactly one non-null parent FK, with one deliberate
exception: ``Project.program_id`` is nullable because a Program is an *optional*
grouping of related projects. A project either sits in a program or hangs
directly off its portfolio, so the portfolio FK — not the program one — is the
mandatory link, and rollups can always walk to the top without a program row.

Vocabularies are CHECK constraints, not just application validation, so no
write path — including a manual ``psql`` session — can produce an invalid row.
``one_of`` builds them, and it is public because ``delivery``, ``records``,
``governance``, ``narrative`` and ``procurement`` all build theirs with it too:
this module is the bottom of the models layer, so a helper every model module
shares belongs here under a name they may say out loud.

``Project`` navigates down into ``driftless.models.delivery`` by *target name*, not
by import: ``delivery`` imports this module, so an import back the other way
would be a cycle. SQLAlchemy resolves those names off its class registry once
both modules have been imported, which ``driftless.models`` guarantees.
"""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base

if TYPE_CHECKING:  # names for the annotations only — never imported at runtime
    from driftless.models.delivery import Baseline, BaselineLine, Milestone, Sprint
    from driftless.models.governance import SignOff
    from driftless.models.narrative import NarrativeArtifact
    from driftless.models.people import Department, Person
    from driftless.models.procurement import ProcurementAgreement
    from driftless.models.quality import QualityMeasurement
    from driftless.models.records import (
        BudgetLine,
        ChangeRequest,
        CostEntry,
        Issue,
        Risk,
        Stakeholder,
        StatusSnapshot,
    )

DELIVERY_MODES = ("predictive", "agile", "hybrid")
ESTIMATE_UNITS = ("points", "hours")
TASK_STATUSES = ("todo", "in_progress", "blocked", "done")


def one_of(column: str, allowed: tuple[str, ...]) -> CheckConstraint:
    """A CHECK restricting ``column`` to ``allowed``. Shared by every model module."""
    values = ", ".join(f"'{value}'" for value in allowed)
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_{column}")


class Business(Base):
    """The company at the root of everything."""

    __tablename__ = "business"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)

    portfolios: Mapped[list["Portfolio"]] = relationship(back_populates="business")
    # Read-only from the business side: the writable side of ``department.business_id``
    # is the department's own ``business``, and a second writable path over one column
    # is how two in-memory collections come to disagree. Declared so the delete guard
    # sees a business's departments and names them.
    departments: Mapped[list["Department"]] = relationship("Department", viewonly=True)


class Portfolio(Base):
    """A grouping of programs and projects, e.g. "Content Brands"."""

    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"), index=True)

    business: Mapped[Business] = relationship(back_populates="portfolios")
    programs: Mapped[list["Program"]] = relationship(back_populates="portfolio")
    projects: Mapped[list["Project"]] = relationship(back_populates="portfolio")


class Program(Base):
    """An optional grouping of related projects inside a portfolio."""

    __tablename__ = "program"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio.id"), index=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="programs")
    projects: Mapped[list["Project"]] = relationship(back_populates="program")


class Project(Base):
    """A delivery effort. ``program_id`` is nullable — see the module docstring."""

    __tablename__ = "project"
    __table_args__ = (one_of("delivery_mode", DELIVERY_MODES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    delivery_mode: Mapped[str] = mapped_column(String(20), default="predictive")
    status_note: Mapped[str | None] = mapped_column(String(2000), default=None)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio.id"), index=True)
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("program.id"), default=None, index=True
    )
    # The department accountable for this project — nullable, and set by name off
    # the class registry rather than an import so ``people`` can point back here.
    responsible_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("department.id"), default=None, index=True
    )

    portfolio: Mapped[Portfolio] = relationship(back_populates="projects")
    program: Mapped[Program | None] = relationship(back_populates="projects")
    responsible_department: Mapped["Department | None"] = relationship("Department")
    workstreams: Mapped[list["Workstream"]] = relationship(back_populates="project")

    # Delivery records. Read-only on purpose: the writable side of each of these
    # foreign keys is already the child's own ``project`` relationship, and a
    # second writable path over the same column is how two in-memory collections
    # come to disagree about the same row. Attach a record by setting its
    # ``project``; read it back through here.
    baselines: Mapped[list["Baseline"]] = relationship("Baseline", viewonly=True)
    milestones: Mapped[list["Milestone"]] = relationship("Milestone", viewonly=True)
    sprints: Mapped[list["Sprint"]] = relationship("Sprint", viewonly=True)
    # The RAID / cost / status / narrative / quality / procurement children, read-only
    # from the project side for the same reason as above. Declared here so the delete
    # guard, which reads blocking children off the mapper, actually sees them and can
    # name what it refuses ("still has risks") instead of falling through to an opaque
    # constraint 409. Every one of these is a real child whose loss is data loss.
    risks: Mapped[list["Risk"]] = relationship("Risk", viewonly=True)
    issues: Mapped[list["Issue"]] = relationship("Issue", viewonly=True)
    change_requests: Mapped[list["ChangeRequest"]] = relationship("ChangeRequest", viewonly=True)
    budget_lines: Mapped[list["BudgetLine"]] = relationship("BudgetLine", viewonly=True)
    cost_entries: Mapped[list["CostEntry"]] = relationship("CostEntry", viewonly=True)
    stakeholders: Mapped[list["Stakeholder"]] = relationship("Stakeholder", viewonly=True)
    status_snapshots: Mapped[list["StatusSnapshot"]] = relationship("StatusSnapshot", viewonly=True)
    quality_measurements: Mapped[list["QualityMeasurement"]] = relationship(
        "QualityMeasurement", viewonly=True
    )
    narrative_artifacts: Mapped[list["NarrativeArtifact"]] = relationship(
        "NarrativeArtifact", viewonly=True
    )
    procurement_agreements: Mapped[list["ProcurementAgreement"]] = relationship(
        "ProcurementAgreement", viewonly=True
    )
    # The sign-off ledger is append-only, so its rows are the decision history of
    # this project and dropping the project would drop them. Read-only for the same
    # reason as the rest, and visible to the guard so the refusal says "still has
    # sign_offs" rather than an opaque constraint 409.
    sign_offs: Mapped[list["SignOff"]] = relationship("SignOff", viewonly=True)


class Workstream(Base):
    """A stream of work (an epic, in agile mode) within a project."""

    __tablename__ = "workstream"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)

    project: Mapped[Project] = relationship(back_populates="workstreams")
    tasks: Mapped[list["Task"]] = relationship(back_populates="workstream")


class Task(Base):
    """The leaf unit of work.

    ``estimate_unit`` follows the owning project's delivery mode — points for
    agile (velocity maths), hours for predictive (cost maths via person rates).
    The CHECK keeps the vocabulary closed; the mode-to-unit pairing is validated
    at the API boundary, where the project row is in hand.
    """

    __tablename__ = "task"
    __table_args__ = (
        one_of("estimate_unit", ESTIMATE_UNITS),
        one_of("status", TASK_STATUSES),
        CheckConstraint("percent_complete BETWEEN 0 AND 100", name="ck_percent_complete"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    workstream_id: Mapped[int] = mapped_column(ForeignKey("workstream.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    estimate: Mapped[float | None] = mapped_column(default=None)
    estimate_unit: Mapped[str] = mapped_column(String(10), default="points")
    actual_effort: Mapped[float | None] = mapped_column(default=None)
    percent_complete: Mapped[int] = mapped_column(default=0)
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id"), default=None, index=True
    )

    workstream: Mapped[Workstream] = relationship(back_populates="tasks")
    # Writable side of the person link: assign by setting ``task.assignee``; the
    # ``Person.tasks`` collection is the read-only mirror, so the FK has one owner.
    assignee: Mapped["Person | None"] = relationship("Person", back_populates="tasks")
    # Read-only from the task side, so the delete guard sees a task's baseline lines
    # and names them rather than 500ing on the foreign key — losing a planned line is
    # exactly the data loss the guard refuses.
    baseline_lines: Mapped[list["BaselineLine"]] = relationship("BaselineLine", viewonly=True)
