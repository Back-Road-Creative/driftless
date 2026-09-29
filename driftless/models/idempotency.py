"""One row per ``Idempotency-Key`` a client has spent, so a retry cannot duplicate a write.

``key`` is UNIQUE and that is the whole mechanism: the database, not application logic,
makes a second use of one key impossible. ``method``/``path`` let a key replayed against a
DIFFERENT endpoint be refused rather than answered with another endpoint's response.
``status_code``/``response_body`` stay NULL until the request finishes, so a row with
neither records an attempt whose outcome is unknown -- see :mod:`driftless.api.idempotency`.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from driftless.db import Base


class IdempotencyRecord(Base):
    """A spent ``Idempotency-Key``, and the answer it earned once one exists."""

    __tablename__ = "idempotency_record"
    __table_args__ = (UniqueConstraint("key", name="uq_idempotency_record_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int | None] = mapped_column(default=None)
    response_body: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
