"""Cross-cutting per-record annotations: a URI reference today, a note tomorrow.

``ArtifactLink`` is a reference row, not a file store (see ``COMPETITORS.md``
gap G4): ``uri`` names where the artifact actually lives (a share, a repo, an
external doc system) and this table never holds bytes. ``record_kind`` is a
table name off ``Base.metadata`` — the same convention
``driftless.db.changelog.ChangeLog.table_name`` already uses to name the row a
change belongs to — and ``record_id`` is that table's primary key as text, so
one link row can point at any record without a table-per-kind fan-out.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship

from driftless.db import Base


class ArtifactLink(Base):
    """One URI reference to an external artifact, filed against a record."""

    __tablename__ = "artifact_link"
    __table_args__ = (Index("ix_artifact_link_record", "record_kind", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_kind: Mapped[str] = mapped_column(String(100))
    record_id: Mapped[str] = mapped_column(String(100))
    uri: Mapped[str] = mapped_column(String(2000))
    title: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    actor: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date] = mapped_column()
    row_revision: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")


class NoteIsAppendOnly(RuntimeError):
    """Raised when a persisted ``Note`` is updated or deleted rather than superseded."""


class Note(Base):
    """One append-only note filed against any record, same ``record_kind``/
    ``record_id`` convention as :class:`ArtifactLink`. A correction is a new row
    whose ``supersedes_id`` names the note it replaces -- the prior row is never
    edited or removed, which :func:`_refuse_mutation` below enforces at the ORM
    layer rather than leaving it to API-route omission alone."""

    __tablename__ = "note"
    __table_args__ = (Index("ix_note_record", "record_kind", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_kind: Mapped[str] = mapped_column(String(100))
    record_id: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date] = mapped_column()
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("note.id"), default=None, index=True
    )

    supersedes: Mapped["Note | None"] = relationship(
        remote_side=[id], back_populates="superseded_by"
    )
    # The other side of the self-reference, so the delete guard names a superseding
    # note instead of answering a bare constraint violation.
    superseded_by: Mapped[list["Note"]] = relationship(back_populates="supersedes")


@event.listens_for(Note, "before_update")
def _refuse_update(mapper: Mapper[Any], connection: Any, target: Note) -> None:
    raise NoteIsAppendOnly("a Note cannot be updated; add a new one with supersedes_id set")


@event.listens_for(Note, "before_delete")
def _refuse_delete(mapper: Mapper[Any], connection: Any, target: Note) -> None:
    raise NoteIsAppendOnly("a Note cannot be deleted; it is a permanent record")
