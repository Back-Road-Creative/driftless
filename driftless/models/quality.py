"""Quality definitions and dated observations with explicit threshold direction.

``QualityMetric`` is the durable project contract; its nullable measurement link
adds direction-aware policy without rewriting legacy evidence.
"""

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

QUALITY_DIRECTIONS = ("lower_is_better", "higher_is_better", "target_band")


class QualityMetric(Base):
    __tablename__ = "quality_metric"
    __table_args__ = (
        one_of("direction", QUALITY_DIRECTIONS),
        CheckConstraint(
            "(direction = 'lower_is_better' AND lower_bound IS NULL AND upper_bound IS NOT NULL) "
            "OR (direction = 'higher_is_better' AND lower_bound IS NOT NULL "
            "AND upper_bound IS NULL) "
            "OR (direction = 'target_band' AND lower_bound IS NOT NULL AND upper_bound IS NOT NULL "
            "AND lower_bound <= upper_bound)",
            name="ck_quality_metric_directional_bounds",
        ),
        UniqueConstraint("project_id", "name", name="uq_quality_metric_project_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(String(20))
    lower_bound: Mapped[float | None] = mapped_column(default=None)
    upper_bound: Mapped[float | None] = mapped_column(default=None)
    unit: Mapped[str | None] = mapped_column(String(50), default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    measurements: Mapped[list["QualityMeasurement"]] = relationship(viewonly=True)


class QualityMeasurement(Base):
    """One dated reading of one quality metric: target, actual, and the unit of both."""

    __tablename__ = "quality_measurement"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    quality_metric_id: Mapped[int | None] = mapped_column(
        ForeignKey("quality_metric.id"), index=True, default=None
    )
    metric: Mapped[str] = mapped_column(String(200))
    target_value: Mapped[float]
    actual_value: Mapped[float]
    unit: Mapped[str | None] = mapped_column(String(50), default=None)
    measured_on: Mapped[date]

    project: Mapped[Project] = relationship()
    quality_metric: Mapped[QualityMetric | None] = relationship()
