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
``BudgetLine`` alone scopes to EITHER a project or a department, never both and
never neither (``ck_budget_line_one_scope``) — a department runs its own
operating budget the same way a project runs its plan, and a twin table would
duplicate every column here for no reason a query could not already group by.
``CostEntry`` spells its columns ``incurred_on`` and ``amount`` because
``driftless.calc.evm.actual_cost`` reads exactly those names to recover AC(t).
Vocabularies are CHECKs, as in ``hierarchy`` and ``delivery``.

``StatusSnapshot`` is the weekly audit trail — the series every trend chart is
drawn from — and ``Stakeholder`` the comms plan. ``RAG_STATUSES`` matches
``driftless.calc.rollup.RagStatus`` so a stored status is one a rollup can consume
without translation.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.delivery import Baseline
from driftless.models.hierarchy import Project, one_of
from driftless.models.people import Department

if TYPE_CHECKING:  # names for the annotations only — never imported at runtime
    from driftless.models.risk import RiskResponse
    from driftless.models.scope import Requirement

RISK_STATUSES = ("open", "mitigating", "closed", "realised")
OPEN_RISK_STATUSES = ("open", "mitigating")  # the RISK_STATUSES subset still open — the one
# vocabulary every "open risks" read (exposure counts, registers, documents) filters against,
# so none of them can drift onto a different pair of statuses.
RISK_RESPONSES = ("avoid", "mitigate", "transfer", "accept")
RISK_KINDS = ("threat", "opportunity")  # what Risk.kind is scoped to; RiskResponse's own
# strategy vocabulary (driftless.models.risk) is validated against whichever half applies.
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
        one_of("kind", RISK_KINDS),
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
    # Threat or opportunity — which half of ``RiskResponse.strategy``'s vocabulary a
    # response filed against this risk must be drawn from. Added after the table
    # existed, so every historical row backfills to "threat", the shape a risk always
    # meant before opportunities were named at all.
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="threat", server_default="threat"
    )
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # The issues this risk turned into. Read-only: the writable side of ``issue.risk_id``
    # is the issue's own ``risk``, and one column keeps one owner. Declared so the delete
    # guard sees them — a realised risk's issues are its whole history.
    issues: Mapped[list["Issue"]] = relationship("Issue", viewonly=True)
    # The response plans filed against this risk. Read-only for the same reason as
    # ``issues`` above: the writable side is each ``RiskResponse``'s own ``risk``, and
    # declaring the collection here is what lets the delete guard name "still has
    # risk_responses" instead of an opaque constraint 409.
    responses: Mapped[list["RiskResponse"]] = relationship("RiskResponse", viewonly=True)

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
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

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
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    resulting_baseline: Mapped[Baseline | None] = relationship()


class BudgetLine(Base):
    """Planned spend for one cost category — one line per project (or department) and category.

    ``project_id`` and ``department_id`` are each nullable, and
    ``ck_budget_line_one_scope`` requires exactly one of them set: a line plans
    either a project's budget or a department's operating budget, never both
    and never neither. Two separate unique constraints (one per scope column)
    is what lets a project and a department each hold their own "one line per
    category" without colliding on the other's NULL.
    """

    __tablename__ = "budget_line"
    __table_args__ = (
        one_of("category", COST_CATEGORIES),
        CheckConstraint("planned_amount >= 0", name="ck_budget_planned_amount"),
        CheckConstraint(
            "(project_id IS NOT NULL) != (department_id IS NOT NULL)",
            name="ck_budget_line_one_scope",
        ),
        UniqueConstraint("project_id", "category", name="uq_budget_line_project_category"),
        UniqueConstraint("department_id", "category", name="uq_budget_line_department_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), default=None)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"), default=None)
    category: Mapped[str] = mapped_column(String(20))
    planned_amount: Mapped[float]
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project | None] = relationship()
    department: Mapped[Department | None] = relationship()


#: ``CostEntry`` is append-only, so a wrong figure is corrected by a reversing negative
#: row plus a new correct row (see docs/temporal-model.md), never an edit -- which means
#: ``amount >= 0`` cannot stand. Dropping the CHECK outright would lose the one thing it
#: actually caught: not a slipped sign (it never distinguished a genuine reversal from a
#: mistake anyway) but an implausible MAGNITUDE, e.g. a data-entry extra zero. This bound
#: replaces it with a symmetric sanity range instead of removing the guard. 1000x the
#: largest cost-domain figure already checked into this repo -- driftless/demo/data.py's
#: biggest ``BudgetLine.planned_amount``, 30_000.0 -- giving generous headroom over any
#: plausible real entry while still catching an order-of-magnitude typo in either
#: direction. A judgement call, not a fact about any organisation's finances; revisit if
#: it ever refuses a legitimate row.
COST_ENTRY_AMOUNT_BOUND = 1000 * 30_000.0  # = 30_000_000.0
_COST_ENTRY_AMOUNT_RANGE = (
    f"amount BETWEEN {-int(COST_ENTRY_AMOUNT_BOUND)} AND {int(COST_ENTRY_AMOUNT_BOUND)}"
)


class CostEntry(Base):
    """Money actually spent, dated — the rows ``driftless.calc.evm`` accrues into AC(t)."""

    __tablename__ = "cost_entry"
    __table_args__ = (
        one_of("category", COST_CATEGORIES),
        CheckConstraint(_COST_ENTRY_AMOUNT_RANGE, name="ck_cost_entry_amount"),
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

    The series is append-only, so a wrong reading cannot be edited, only
    refiled -- and refiling a DATE already snapshotted used to be forbidden
    outright, ``uq_status_snapshot_project_date`` raising ``IntegrityError``,
    which left no way to correct a row at all. That constraint is gone: a
    second snapshot for an already-snapshotted date is now accepted, and the
    most recently RECORDED one -- the higher ``id``, never ``taken_on`` order,
    which two same-date rows now share -- is the one every "latest reading"
    read returns (see ``docs/temporal-model.md``). No backward link names the
    row a correction supersedes: ``ChangeLog`` already records who filed which
    row and when. Two same-date rows CAN disagree now, which binds every reader
    of the *series* rather than a single "latest" pick: it must break that tie
    by recording order rather than let the query's return order decide, as
    ``driftless.web.views.trend_series`` does before plotting.
    """

    __tablename__ = "status_snapshot"
    __table_args__ = (
        one_of("rag_status", RAG_STATUSES),
        CheckConstraint("percent_complete BETWEEN 0 AND 100", name="ck_snapshot_percent_complete"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Explicitly indexed, because the constraint that used to do it is gone. While
    # ``uq_status_snapshot_project_date`` existed, ``project_id`` LED that unique
    # constraint and inherited its index for free -- every "this project's series" read
    # rode on it. Dropping the constraint to allow a same-date correction would have
    # quietly left the busiest foreign key on this table unindexed;
    # ``tests/test_db_hardening.py`` caught exactly that.
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
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
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    # Read-only from the stakeholder side, same reason every other family's blocking
    # child collection is: the writable side of a requirement's link is its own
    # ``source_stakeholder``, and declaring the collection here lets the delete
    # guard name "still has sourced_requirements" instead of an opaque constraint 409.
    sourced_requirements: Mapped[list["Requirement"]] = relationship("Requirement", viewonly=True)
