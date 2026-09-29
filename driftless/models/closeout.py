"""``LessonLearned``: one row per lesson raised, replacing prose-only knowledge.

PMBOK's lessons learned register used to have no home of its own: it was one
more body of free text under ``NarrativeArtifact``, so a project could only
ever have *a* lessons learned document, never a register of individually
dated, categorised entries an evaluator or a report could count and group.
This gives it a row: one lesson per raising, categorised by the knowledge
area it touches, with what happened, what to do differently next time, and
who raised it. ``pmbok.mapping``'s ``lessons_learned_register`` resolver
reads these rows now, not the retired narrative kind.

``category`` reuses the ten PMBOK knowledge-area strings (``pmbok.model.
KnowledgeArea``'s own values) rather than inventing a second vocabulary —
kept as a plain tuple here, not an import of the enum, so this leaf model
does not reach up into the PMBOK reference layer for a CHECK constraint.
"""

from datetime import date

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

LESSON_CATEGORIES = (
    "integration",
    "scope",
    "schedule",
    "cost",
    "quality",
    "resource",
    "communications",
    "risk",
    "procurement",
    "stakeholder",
)


class LessonLearned(Base):
    """One lesson raised on a project: what happened, and what to do next time."""

    __tablename__ = "lesson_learned"
    __table_args__ = (one_of("category", LESSON_CATEGORIES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    raised_on: Mapped[date]
    category: Mapped[str] = mapped_column(String(20))
    what_happened: Mapped[str] = mapped_column(Text)
    what_to_do_next_time: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(200))
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")

    project: Mapped[Project] = relationship()
