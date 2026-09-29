"""``TechniqueRun``: the provenance row every technique a project runs leaves.

Append-only like ``SignOff`` (``models/governance.py``): no update path, and
:func:`driftless.services.technique_runs.record_run` is the only writer.
``inputs_snapshot``/``outputs_produced`` are JSON text, matching
``ChangeLog.detail``, so the table stays portable between SQLite and Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of
from driftless.pmbok.provenance import MethodContext

TECHNIQUE_RUN_METHODS: tuple[str, ...] = tuple(m.value for m in MethodContext)


def _utcnow() -> datetime:
    """Now, in UTC — the write-time stamp; never read by a pure calculator."""
    return datetime.now(UTC)


class TechniqueRun(Base):
    """One append-only record: this project ran this technique for this process."""

    __tablename__ = "technique_run"
    __table_args__ = (one_of("method", TECHNIQUE_RUN_METHODS),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    technique_key: Mapped[str] = mapped_column(String(100))
    process_id: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date] = mapped_column()
    method: Mapped[str] = mapped_column(String(20))
    source_version: Mapped[str] = mapped_column(String(200), default="")
    inputs_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    outputs_produced: Mapped[str] = mapped_column(Text, default="{}")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship()
