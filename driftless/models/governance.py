"""The append-only sign-off ledger: human (or agent) decisions on threats and processes.

A sign-off records that someone looked at a computed problem — a threat the
assessment engine raised, a process the tailoring decision excludes, or a
baseline version awaiting approval — and made a call about it. Like ``StatusSnapshot`` and ``ChangeLog`` it is
append-only *in spirit and in use*: nothing edits a row, and a reversal is a new
event with the opposite decision, so the ledger is the whole history and the
current position is simply its latest entry for a subject.

Two design choices carry the weight:

- **``subject_ref`` is severity-independent.** It names *what* the decision is
  about (``"cost:project:42"``, ``"process:4.3:project:42"``), not how bad it is
  right now. The assessment layer builds it; the same threat keeps the same ref
  as its score moves.
- **``signal`` is the score at the moment of sign-off.** That is what lets a
  suppression be robust by construction: the assessment engine hides a
  signed-off threat only while the live score is no worse than the recorded
  ``signal``. Worsen the signal past it and the threat re-crosses threshold and
  returns — a sign-off cannot bury a regression. A process waiver carries no
  score, so ``signal`` is nullable.

``signed_at`` is a real wall-clock stamp of when the decision was made — stored
data, set at the write boundary, never read by the pure assessment core (which
stays clock-free); ``as_of`` records the assessment date the decision was made
against. Vocabularies are CHECK constraints, matching the rest of the models.
"""

from datetime import UTC, date, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import Project, one_of

SIGNOFF_SUBJECTS = ("threat", "process", "baseline", "gate")
SIGNOFF_DECISIONS = ("accepted", "resolved", "deferred", "rejected", "waived")
#: Who signed — ``"human"`` (the default) or ``"agent"``, mirroring ``Person.kind``.
#: Stamped once, at write time, by ``driftless.services.sign_offs.create_sign_off`` —
#: so the ledger and the heatmap show the same distinction between a person and the
#: token acting on one's behalf without re-deriving it by name match on every read.
SIGNOFF_ACTOR_KINDS = ("human", "agent")
#: Decisions that take a subject out of the live feed (until a threat regresses
#: past its recorded ``signal``). ``rejected`` deliberately does not — it is an
#: explicit "this is real, keep showing it".
SUPPRESSING_DECISIONS = ("accepted", "resolved", "deferred", "waived")


def _utcnow() -> datetime:
    """Now, in UTC — the write-time stamp; the pure assessment core never calls this."""
    return datetime.now(UTC)


class SignOff(Base):
    """One immutable decision about a threat or a process. Latest entry per subject wins."""

    __tablename__ = "sign_off"
    __table_args__ = (
        one_of("subject_kind", SIGNOFF_SUBJECTS),
        one_of("decision", SIGNOFF_DECISIONS),
        one_of("signed_by_kind", SIGNOFF_ACTOR_KINDS),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("project.id"), default=None, index=True
    )
    subject_kind: Mapped[str] = mapped_column(String(20))
    subject_ref: Mapped[str] = mapped_column(String(200))
    decision: Mapped[str] = mapped_column(String(20))
    signal: Mapped[float | None] = mapped_column(default=None)
    signed_by: Mapped[str] = mapped_column(String(200), default="unknown")
    signed_by_kind: Mapped[str] = mapped_column(String(20), default="human", server_default="human")
    note: Mapped[str | None] = mapped_column(String(2000), default=None)
    as_of: Mapped[date | None] = mapped_column(default=None)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project | None] = relationship()


class Gate(Base):
    """A named stage boundary on a project's own timeline, ordered by ``position``.

    ``Gate`` is a thin definition row on purpose (plan gap G20): it names a
    project, a place in sequence and the PMBOK processes that must be complete
    to pass, but it stores no status of its own. Readiness is never stored —
    it is computed, every time, the same way process state is
    (:mod:`driftless.pmbok.state`): a gate is ready iff every process named in
    ``required_processes`` is in a completed derived state for that project
    (``PRODUCED``, ``SIGNED_OFF`` or ``WAIVED`` — a process tailored out must
    not block a gate it was never meant to gate). Passage is a ``SignOff``
    row like any other subject (``subject_kind == "gate"``, ``subject_ref``
    the gate's own id) — there is deliberately no second "passed" flag on this
    table to drift from the ledger.

    ``required_processes`` is a comma-separated string of PMBOK clause
    numbers (``Process.id``, e.g. ``"11.2"``) rather than a second table: the
    catalog itself is the closed, frozen vocabulary those ids are validated
    against (:func:`driftless.pmbok.catalog.get`), so a join table would only
    duplicate what ``driftless.pmbok.state.gate_readiness`` already reads on
    every call. See :meth:`process_ids`.
    """

    __tablename__ = "gate"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(default=0)
    required_processes: Mapped[str] = mapped_column(String(2000), default="", server_default="")

    project: Mapped[Project] = relationship()

    def process_ids(self) -> tuple[str, ...]:
        """The gate's required PMBOK clause numbers, parsed from storage."""
        return tuple(pid for pid in self.required_processes.split(",") if pid)
