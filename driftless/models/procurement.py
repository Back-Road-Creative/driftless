"""Procurement agreements: the contracts a project runs work through.

This is what makes the Procurement knowledge area real. A ``ProcurementAgreement``
is one vendor contract — its value, its status, and the window it runs over — so
the Procurement evaluator can flag a disputed agreement, one whose end date has
passed while it is still active, or contracted spend that outruns the budget
lines behind it. As everywhere in this store the health reading is *derived* from
these rows, never stamped onto them.

``status`` is a CHECK vocabulary. ``amount`` is the contract's value and cannot
be negative. ``end_date`` is nullable — an open-ended retainer has no fixed end —
and when present must not precede ``start_date``, enforced by a CHECK so no write
path can store an impossible window.
"""

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

PROCUREMENT_STATUSES = ("draft", "active", "closed", "disputed")


class ProcurementAgreement(Base):
    """One vendor contract on a project — value, status and the window it covers."""

    __tablename__ = "procurement_agreement"
    __table_args__ = (
        one_of("status", PROCUREMENT_STATUSES),
        CheckConstraint("amount >= 0", name="ck_agreement_amount"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_agreement_window"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    vendor: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    amount: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    start_date: Mapped[date]
    end_date: Mapped[date | None] = mapped_column(default=None)

    project: Mapped[Project] = relationship()
