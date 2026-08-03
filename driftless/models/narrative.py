"""First-class narrative PMBOK artifacts: the prose a process reads and owes.

Several PMBOK artifacts are prose, not numbers — the assumption log a process
reads, the enterprise environmental factors and organizational process assets it
consumes, the lessons learned it feeds forward, and the subsidiary management
plans, statements and assessments a process owes. Without a home they are
unmodellable, so the wizard could neither require them nor populate them and the
process-state engine could never see them as "present". A ``NarrativeArtifact``
gives each a row: one body of text per project per kind, so the artifact-mapping
layer can answer "does this project have an assumption log?" with a query.

The first four kinds predate the catalog convention and keep their short names;
every kind after them is stored under its catalog artifact name exactly, which
is what lets a resolver for one of them be a single mapping entry.

One per ``(project, kind)`` by construction — a project has *an* assumption log,
not a pile of them; updating it rewrites the body (and the ChangeLog listener
keeps the history). ``kind`` is a CHECK vocabulary, matching the rest of the
models.
"""

from datetime import date

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

NARRATIVE_KINDS = (
    "assumption_log",
    "eef",
    "opa",
    "lessons_learned",
    "scope_management_plan",
    "requirements_management_plan",
    "schedule_management_plan",
    "cost_management_plan",
    "quality_management_plan",
    "resource_management_plan",
    "communications_management_plan",
    "risk_management_plan",
    "procurement_management_plan",
    "stakeholder_engagement_plan",
    "project_scope_statement",
    "requirements_documentation",
    "team_charter",
    "basis_of_estimates",
    "team_performance_assessments",
)


class NarrativeArtifact(Base):
    """One project's prose of a given kind — the modellable form of a narrative input."""

    __tablename__ = "narrative_artifact"
    __table_args__ = (
        one_of("kind", NARRATIVE_KINDS),
        UniqueConstraint("project_id", "kind", name="uq_narrative_project_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    kind: Mapped[str] = mapped_column(String(30))
    body: Mapped[str] = mapped_column(Text, default="")
    updated_on: Mapped[date | None] = mapped_column(default=None)

    project: Mapped[Project] = relationship()
