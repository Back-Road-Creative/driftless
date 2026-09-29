"""Response planning: what a project does about one risk, who owns it and what it costs.

``RiskResponse`` is a separate row from ``Risk`` rather than more columns on it, because
a risk can carry more than one response over its life (a first mitigation that proves
insufficient, a later escalation) and each one needs its own owner, trigger and residual
reading — the append-and-supersede shape every other planning record in this schema uses,
not an edit-in-place summary field.

``strategy`` is the union of the two PMBOK strategy families — threats (avoid, mitigate,
transfer, accept, escalate) and opportunities (exploit, enhance, share, accept, escalate) —
stored as one CHECK-constrained vocabulary because a column cannot itself express "the
subset that matches this OTHER row's kind". That cross-row rule — a response's strategy
must belong to the family its risk's ``kind`` names — is a write-boundary check instead
(``driftless.api.rules.risk_response_matches_kind``), the same tier ``dependency_lands_valid``
already uses for a rule one row cannot see on its own.

``residual_probability``/``residual_impact`` are the risk's OWN two figures, re-estimated
for after the response lands — never derived from ``Risk.probability``/``impact``, since a
response is exactly the plan to move them. ``driftless.pmbok.risk_facts`` is the one place
that turns a filed response's residual pair into the exposure figure the rest of the
product reads, so a page or report that wants "residual exposure" asks it rather than
multiplying these two out again.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of
from driftless.models.records import Risk

if TYPE_CHECKING:  # names for the annotations only — never imported at runtime
    from driftless.models.people import Person

#: The union of both PMBOK-6 strategy families (11.5.2.3 threats, 11.5.2.4 opportunities).
#: "accept" and "escalate" are shared by both; which subset a given response may draw from
#: is decided by its risk's ``kind`` (``driftless.api.rules.risk_response_matches_kind``),
#: never by this column alone.
RESPONSE_STRATEGIES = (
    "avoid",
    "mitigate",
    "transfer",
    "exploit",
    "enhance",
    "share",
    "accept",
    "escalate",
)
#: The ``RESPONSE_STRATEGIES`` a ``threat``-kind risk may file a response under.
THREAT_STRATEGIES = frozenset({"avoid", "mitigate", "transfer", "accept", "escalate"})
#: The ``RESPONSE_STRATEGIES`` an ``opportunity``-kind risk may file a response under.
OPPORTUNITY_STRATEGIES = frozenset({"exploit", "enhance", "share", "accept", "escalate"})
RESPONSE_STATUSES = ("planned", "in_progress", "implemented", "abandoned")


class RiskResponse(Base):
    """One response plan filed against a risk: strategy, owner, trigger and residual read.

    ``project_id`` mirrors ``risk_id -> risk.project_id`` rather than being derived at read
    time — the same "link, not parent, but named directly for batched scoping" shape
    ``Issue.risk_id`` already uses beside its own ``project_id`` — so ``adapters.project_rows``
    reads this table exactly like every other project-scoped record, and
    ``driftless.api.rules.risk_lands_in_project``-style checks keep the two in step.
    """

    __tablename__ = "risk_response"
    __table_args__ = (
        one_of("strategy", RESPONSE_STRATEGIES),
        one_of("status", RESPONSE_STATUSES),
        CheckConstraint(
            "residual_probability BETWEEN 0 AND 1", name="ck_risk_response_residual_probability"
        ),
        CheckConstraint("residual_impact >= 0", name="ck_risk_response_residual_impact"),
        CheckConstraint("cost_of_response >= 0", name="ck_risk_response_cost_of_response"),
        CheckConstraint("schedule_days >= 0", name="ck_risk_response_schedule_days"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("risk.id"), index=True)
    strategy: Mapped[str] = mapped_column(String(20))
    owner_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(2000))
    planned_action: Mapped[str] = mapped_column(String(2000))
    residual_probability: Mapped[float]
    residual_impact: Mapped[float]
    cost_of_response: Mapped[float] = mapped_column(default=0.0)
    schedule_days: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    actor: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date]
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    risk: Mapped[Risk] = relationship()
    # Writable side of the owner link: file a response by setting ``response.owner``; the
    # read-only reverse (``Person.risk_responses``) exists only so the delete guard sees it.
    owner: Mapped["Person"] = relationship("Person", back_populates="risk_responses")

    @property
    def residual_exposure(self) -> float:
        """The probability-weighted cost this response leaves behind — never stored,
        the same "derived, not carried" rule ``Risk.exposure`` already follows."""
        return self.residual_probability * self.residual_impact
