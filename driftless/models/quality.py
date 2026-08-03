"""Quality measurements: a metric's target versus what was actually measured.

This is what makes the Quality knowledge area real rather than aspirational. A
``QualityMeasurement`` is one dated reading of one metric — its target, its
actual, and the unit both are in — so the Quality evaluator can say whether a
project is inside tolerance and how fresh the evidence is. Nothing is computed
and stored here; the assessment engine reads these rows and derives status.

A metric can be read many times over a project's life (the series is the trend),
so there is deliberately no uniqueness on ``(project, metric)`` — ``measured_on``
distinguishes readings. Direction of "good" is not modelled: a tolerance is a
band around target, and the evaluator judges distance from target, which reads
correctly whether higher or lower is better.
"""

from datetime import date

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project


class QualityMeasurement(Base):
    """One dated reading of one quality metric: target, actual, and the unit of both."""

    __tablename__ = "quality_measurement"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    metric: Mapped[str] = mapped_column(String(200))
    target_value: Mapped[float]
    actual_value: Mapped[float]
    unit: Mapped[str | None] = mapped_column(String(50), default=None)
    measured_on: Mapped[date]

    project: Mapped[Project] = relationship()
