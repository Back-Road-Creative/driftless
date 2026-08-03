"""Per-project RAID and money records: risks, issues, change requests, budget and spend.

``Risk.exposure`` is not a column but a SQLAlchemy hybrid — ``probability *
impact`` run in Python on a loaded row and compiled into SQL for filters — so a
stored exposure can never disagree with the two numbers behind it.

A change request is the only thing allowed to alter approved scope, and it does
so by causing a *new* baseline version rather than editing one:
``resulting_baseline_id`` names the version it produced, and the CHECK lets only
an approved request carry that link. That the new version supersedes the old,
and that nothing else edits approved scope, stays the API layer's job.

``BudgetLine`` is planned and ``CostEntry`` actual over one ``COST_CATEGORIES``
vocabulary, so planned-versus-actual is a group-by, not a join heuristic.
``CostEntry`` spells its columns ``incurred_on`` and ``amount`` because
``driftless.calc.evm.actual_cost`` reads exactly those names to recover AC(t).
Vocabularies are CHECKs, as in ``hierarchy`` and ``delivery``.

``StatusSnapshot`` is the weekly audit trail — the series every trend chart is
drawn from — and ``Stakeholder`` the comms plan. ``RAG_STATUSES`` matches
``driftless.calc.rollup.RagStatus`` so a stored status is one a rollup can consume
without translation.
"""

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.delivery import Baseline
from driftless.models.hierarchy import Project, one_of

RISK_STATUSES = ("open", "mitigating", "closed", "realised")
OPEN_RISK_STATUSES = ("open", "mitigating")  # the RISK_STATUSES subset still open — the one
# vocabulary every "open risks" read (exposure counts, registers, documents) filters against,
# so none of them can drift onto a different pair of statuses.
RISK_RESPONSES = ("avoid", "mitigate", "transfer", "accept")
ISSUE_STATUSES = ("open", "in_progress", "resolved", "closed")
CHANGE_STATUSES = ("proposed", "approved", "rejected", "withdrawn")
COST_CATEGORIES = ("labour", "materials", "services", "travel", "contingency")
RAG_STATUSES = ("green", "amber", "red")
STAKEHOLDER_LEVELS = ("low", "medium", "high")
COMMS_CADENCES = ("weekly", "fortnightly", "monthly", "on_request")


class Risk(Base):
    """A future event that might cost the project. ``exposure`` is derived, never stored."""

    __tablename__ = "risk"
    __table_args__ = (
        one_of("status", RISK_STATUSES),
        one_of("response", RISK_RESPONSES),
        CheckConstraint("probability BETWEEN 0 AND 1", name="ck_risk_probability"),
        CheckConstraint("impact >= 0", name="ck_risk_impact"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    probability: Mapped[float]
    impact: Mapped[float]
    response: Mapped[str] = mapped_column(String(20), default="mitigate")
    owner: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")

    project: Mapped[Project] = relationship()
    # The issues this risk turned into. Read-only: the writable side of ``issue.risk_id``
    # is the issue's own ``risk``, and one column keeps one owner. Declared so the delete
    # guard sees them — a realised risk's issues are its whole history.
    issues: Mapped[list["Issue"]] = relationship("Issue", viewonly=True)

    @hybrid_property
    def exposure(self) -> float:
        return self.probability * self.impact  # probability-weighted cost, in Python and in SQL


class Issue(Base):
    """A problem happening now. ``risk_id`` is the risk it came from, null if raised outright."""

    __tablename__ = "issue"
    __table_args__ = (
        one_of("status", ISSUE_STATUSES),
        CheckConstraint("resolved_on IS NULL OR resolved_on >= raised_on", name="ck_issue_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    raised_on: Mapped[date]
    resolved_on: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    risk_id: Mapped[int | None] = mapped_column(ForeignKey("risk.id"), default=None, index=True)

    project: Mapped[Project] = relationship()
    risk: Mapped[Risk | None] = relationship()


class ChangeRequest(Base):
    """A proposed change to approved scope. Approval produces a new baseline version."""

    __tablename__ = "change_request"
    __table_args__ = (
        one_of("status", CHANGE_STATUSES),
        CheckConstraint(
            "resulting_baseline_id IS NULL OR status = 'approved'", name="ck_change_approved"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    raised_on: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    resulting_baseline_id: Mapped[int | None] = mapped_column(
        ForeignKey("baseline.id"), default=None, index=True
    )
    # PMBOK clause id (e.g. "5.6") of the process that raised this; nullable — history
    # may not know. Not a FK: the catalog is code, so the API schema enforces it.
    origin_process_id: Mapped[str | None] = mapped_column(String(8), default=None)

    project: Mapped[Project] = relationship()
    resulting_baseline: Mapped[Baseline | None] = relationship()


class BudgetLine(Base):
    """Planned spend for one cost category — one line per project and category."""

    __tablename__ = "budget_line"
    __table_args__ = (
        one_of("category", COST_CATEGORIES),
        CheckConstraint("planned_amount >= 0", name="ck_budget_planned_amount"),
        UniqueConstraint("project_id", "category", name="uq_budget_line_project_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    category: Mapped[str] = mapped_column(String(20))
    planned_amount: Mapped[float]

    project: Mapped[Project] = relationship()


class CostEntry(Base):
    """Money actually spent, dated — the rows ``driftless.calc.evm`` accrues into AC(t)."""

    __tablename__ = "cost_entry"
    __table_args__ = (
        one_of("category", COST_CATEGORIES),
        CheckConstraint("amount >= 0", name="ck_cost_entry_amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    incurred_on: Mapped[date]
    amount: Mapped[float]

    project: Mapped[Project] = relationship()


class StatusSnapshot(Base):
    """One DATED reading of a project's health — the series behind every trend chart.

    ``percent_complete`` is *stamped* here, not typed in: the tasks under the
    project already carry completion, so a hand-entered copy on the weekly form
    would be a second write path for the same fact and the two would drift. The
    weekly form computes it and stamps it; doing that computing belongs to the
    API/service layer, and this schema's job is to hold the stamped number and
    keep it in range, exactly as ``hierarchy.Task`` does.

    The series is append-only in spirit, which the unique constraint makes true in
    fact: one snapshot per project per DATE, so no trend can hold two disagreeing
    readings for one day — and, no cadence being enforced, must plot ``taken_on``.
    """

    __tablename__ = "status_snapshot"
    __table_args__ = (
        one_of("rag_status", RAG_STATUSES),
        CheckConstraint("percent_complete BETWEEN 0 AND 100", name="ck_snapshot_percent_complete"),
        UniqueConstraint("project_id", "taken_on", name="uq_status_snapshot_project_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    taken_on: Mapped[date]
    percent_complete: Mapped[int] = mapped_column(default=0)
    rag_status: Mapped[str] = mapped_column(String(20), default="green")
    note: Mapped[str | None] = mapped_column(String(2000), default=None)

    project: Mapped[Project] = relationship()


class Stakeholder(Base):
    """Someone with a stake in the project; interest and influence set the comms cadence."""

    __tablename__ = "stakeholder"
    __table_args__ = (
        one_of("interest", STAKEHOLDER_LEVELS),
        one_of("influence", STAKEHOLDER_LEVELS),
        one_of("comms_cadence", COMMS_CADENCES),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    interest: Mapped[str] = mapped_column(String(20), default="medium")
    influence: Mapped[str] = mapped_column(String(20), default="medium")
    comms_cadence: Mapped[str] = mapped_column(String(20), default="monthly")

    project: Mapped[Project] = relationship()
