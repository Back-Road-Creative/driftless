"""Business-scoped strategy roots for the balanced operating scorecard.

Objectives deliberately start at business scope.  Portfolio, program, project,
and department objectives can follow once the root workflow has demonstrated
which narrower scopes are useful; a polymorphic scope now would weaken every
parent validation and delete guard before there is evidence it is needed.
"""

from datetime import date

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Business, Project, one_of

SCORECARD_PERSPECTIVES = (
    "financial",
    "customer_stakeholder",
    "internal_operations",
    "people_capability",
)
OBJECTIVE_STATUSES = ("active", "paused", "retired")
SCORECARD_DIRECTIONS = ("higher_is_better", "lower_is_better")
METRIC_SOURCE_TYPES = ("manual", "registered_connector")
# A definition that never stated a start has always been in force. A VALUE, not
# NULL: the widened constraint must see two undated rows as one identity.
METRIC_ALWAYS = date.min
SCORECARD_SOURCE_STATUSES = ("active", "retired")
SCORECARD_CONTRIBUTION_TYPES = ("direct", "supporting")
SCORECARD_CONTRIBUTION_STATUSES = ("active", "retired")


class StrategicObjective(Base):
    """A business outcome, grouped by one stable scorecard perspective."""

    __tablename__ = "strategic_objective"
    __table_args__ = (
        one_of("perspective", SCORECARD_PERSPECTIVES),
        one_of("status", OBJECTIVE_STATUSES),
        CheckConstraint(
            "active_until IS NULL OR active_from IS NULL OR active_from <= active_until",
            name="ck_strategic_objective_active_window",
        ),
        UniqueConstraint("business_id", "name", name="uq_strategic_objective_business_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"), index=True)
    perspective: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    owner: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    active_from: Mapped[date | None] = mapped_column(default=None)
    active_until: Mapped[date | None] = mapped_column(default=None)
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    business: Mapped[Business] = relationship()
    # The metric's writable side is its own objective FK. This read-only parent
    # relation lets the generic delete guard name the metrics it protects.
    metric_definitions: Mapped[list["ScorecardMetricDefinition"]] = relationship(
        "ScorecardMetricDefinition", viewonly=True
    )
    contributions: Mapped[list["ScorecardContribution"]] = relationship(
        "ScorecardContribution", viewonly=True
    )


class ScorecardSource(Base):
    """Business-scoped metadata for an approved non-manual metric source.

    A registry entry names a source and its owner; it deliberately has no URL,
    credential, or executable expression. Integrations can resolve the key in a
    separately governed adapter registry without turning scorecard data into code.
    """

    __tablename__ = "scorecard_source"
    __table_args__ = (
        one_of("status", SCORECARD_SOURCE_STATUSES),
        UniqueConstraint("business_id", "key", name="uq_scorecard_source_business_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    business: Mapped[Business] = relationship()


class ScorecardContribution(Base):
    """A project-to-objective link explaining how delivery supports strategy."""

    __tablename__ = "scorecard_contribution"
    __table_args__ = (
        one_of("contribution_type", SCORECARD_CONTRIBUTION_TYPES),
        one_of("status", SCORECARD_CONTRIBUTION_STATUSES),
        UniqueConstraint(
            "project_id", "objective_id", name="uq_scorecard_contribution_project_objective"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("strategic_objective.id"), index=True)
    contribution_type: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
    objective: Mapped[StrategicObjective] = relationship()


class ScorecardMetricDefinition(Base):
    """A measurable, directional indicator for one strategic objective.

    Definitions declare what success means; observations and connector execution
    remain separate workflows. A connector name is data only until a later
    registry explicitly recognises it, so this record stores no formulas or credentials.

    Versioned, not mutable: a logical metric is the rows sharing one
    ``(objective_id, name)``, each ``effective_from`` the date it took effect. A
    grading input changes by a NEW row (``adapters.metric_definition_as_of``).
    """

    __tablename__ = "scorecard_metric_definition"
    __table_args__ = (
        one_of("direction", SCORECARD_DIRECTIONS),
        one_of("source_type", METRIC_SOURCE_TYPES),
        CheckConstraint("cadence_days > 0", name="ck_scorecard_metric_cadence"),
        CheckConstraint(
            "(direction = 'higher_is_better' AND target_value >= amber_threshold "
            "AND amber_threshold >= red_threshold) OR "
            "(direction = 'lower_is_better' AND target_value <= amber_threshold "
            "AND amber_threshold <= red_threshold)",
            name="ck_scorecard_metric_directional_thresholds",
        ),
        CheckConstraint(
            "(source_type = 'manual' AND source_key IS NULL) OR "
            "(source_type = 'registered_connector' AND source_key IS NOT NULL)",
            name="ck_scorecard_metric_source_key",
        ),
        UniqueConstraint(
            "objective_id", "name", "effective_from", name="uq_scorecard_metric_objective_name"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("strategic_objective.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(String(20))
    unit: Mapped[str] = mapped_column(String(50))
    target_value: Mapped[float] = mapped_column(Float)
    amber_threshold: Mapped[float] = mapped_column(Float)
    red_threshold: Mapped[float] = mapped_column(Float)
    cadence_days: Mapped[int] = mapped_column()
    owner: Mapped[str | None] = mapped_column(String(200), default=None)
    source_type: Mapped[str] = mapped_column(String(30), default="manual")
    source_key: Mapped[str | None] = mapped_column(String(100), default=None)
    effective_from: Mapped[date] = mapped_column(default=METRIC_ALWAYS, server_default="0001-01-01")
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    objective: Mapped[StrategicObjective] = relationship()
    observations: Mapped[list["ScorecardMetricObservation"]] = relationship(viewonly=True)


class ScorecardMetricObservation(Base):
    """One immutable, dated measurement supporting a scorecard metric."""

    __tablename__ = "scorecard_metric_observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_definition_id: Mapped[int] = mapped_column(
        ForeignKey("scorecard_metric_definition.id"), index=True
    )
    observed_on: Mapped[date]
    value: Mapped[float] = mapped_column(Float)
    evidence_note: Mapped[str] = mapped_column(String(2000), default="")

    metric_definition: Mapped[ScorecardMetricDefinition] = relationship()
