"""The computed process-state engine: where each project stands on each process.

Process state is never stored — it is computed, every time, from two sources: the
artifacts the project has produced (``driftless.pmbok.mapping``) and the sign-off
ledger (``SignOff``). So it cannot drift, and there is deliberately no
ProcessInstance table: a process a project does not do is a ``SignOff`` with
decision ``waived``, not a second source of truth.

A process is:
- ``WAIVED`` if its latest process sign-off waives it (tailored out);
- ``SIGNED_OFF`` if its latest process sign-off accepts/resolves it (approved done);
- otherwise judged from its *tracked* outputs — ``PRODUCED`` when every required
  one exists, ``IN_PROGRESS`` when any (required or optional) does,
  ``NOT_STARTED`` when none do. An optional output is evidence of activity but
  is never required for ``PRODUCED``.

Everything takes an explicit as-of date and reads no wall clock, so a state map
regenerates identically from the same store.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import Project, SignOff
from driftless.pmbok import catalog, mapping
from driftless.pmbok.model import Process

#: Process sign-off decisions that mean "approved as done", distinct from waived.
_DONE_DECISIONS = ("accepted", "resolved")

_SIGN_OFF_PREFETCH_KEY = "driftless.pmbok.state.sign_off_prefetch"


@contextmanager
def prefetched(session: Session, projects: Sequence[Project]) -> Iterator[None]:
    """Bound a store-wide state map's statements: pre-fetch what it reads.

    One query for the scope's projects' process sign-offs (filtered: the
    ledger grows with the store, the scope does not), grouped per subject,
    ascending (signed_at, id), rows kept whole so one scope answers every
    as-of — plus ``mapping.prefetched``'s one query per tracked model. The
    previous scope is saved and restored as ``mapping.prefetched`` does, so
    nesting narrows the inner block's cache and hands the outer its own back.
    """
    ledger: dict[str, list[SignOff]] = {}
    rows = session.scalars(
        select(SignOff)
        .where(SignOff.subject_kind == "process")
        .where(SignOff.project_id.in_([project.id for project in projects]))
        .order_by(SignOff.signed_at, SignOff.id)
    )
    for row in rows:
        ledger.setdefault(row.subject_ref, []).append(row)
    outer: dict[str, list[SignOff]] | None = session.info.get(_SIGN_OFF_PREFETCH_KEY)
    session.info[_SIGN_OFF_PREFETCH_KEY] = ledger
    try:
        with mapping.prefetched(session, projects):
            yield
    finally:
        if outer is None:
            session.info.pop(_SIGN_OFF_PREFETCH_KEY, None)
        else:
            session.info[_SIGN_OFF_PREFETCH_KEY] = outer


class ProcessState(str, Enum):
    """Where a project stands on a single process."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PRODUCED = "produced"
    SIGNED_OFF = "signed_off"
    WAIVED = "waived"


def process_subject_ref(process: Process, project: Project) -> str:
    """The severity-independent sign-off subject for a process on a project."""
    return f"process:{process.id}:project:{project.id}"


def threat_subject_ref(kind: str, project_id: int) -> str:
    """The severity-independent sign-off subject for a threat on a project.

    The one home for the ``"{kind}:project:{id}"`` convention: every evaluator's
    ``Threat.id`` is this ref, and ``engine.is_suppressed`` looks a threat up by it
    under byte equality, so building it here (never by hand) keeps a sign-off
    matching the threat it names. The feed prepends a ``"threat:"`` display prefix
    for its item id and the web strips it back — that prefix is a namespace, not a
    second ref form. Mirrors :func:`process_subject_ref` for the process side.
    """
    return f"{kind}:project:{project_id}"


def latest_sign_off(
    session: Session, subject_kind: str, subject_ref: str, as_of: date | None = None
) -> SignOff | None:
    """The current decision for a subject as of a date — see ``current_sign_off``.

    Decisions recorded against a later assessment date than ``as_of`` are
    invisible: a 2026 sign-off cannot rewrite what a 2020 page said. ``None``
    (the default, for callers with no date to bound by) reads the whole ledger.
    """
    cached: dict[str, list[SignOff]] | None = session.info.get(_SIGN_OFF_PREFETCH_KEY)
    if cached is not None and subject_kind == "process":
        return current_sign_off(cached.get(subject_ref, []), as_of)
    rows = session.scalars(
        select(SignOff)
        .where(SignOff.subject_kind == subject_kind, SignOff.subject_ref == subject_ref)
        .order_by(SignOff.signed_at, SignOff.id)
    )
    return current_sign_off(list(rows), as_of)


def is_assessable(process: Process) -> bool:
    """Whether any of the process's REQUIRED outputs is a kind the store can track.

    Optional (conditional) outputs do not count: a process whose only tracked
    output is optional could never honestly reach PRODUCED, so it must not
    enter completeness denominators.
    """
    return any(
        mapping.is_tracked(kind) for kind in process.outputs if kind not in process.optional_outputs
    )


def excluded_from_completeness(process: Process, proc_state: ProcessState) -> bool:
    """Whether a (process, state) pair drops out of every completeness figure.

    WAIVED processes are excluded — tailoring one out must not count against the
    project. Not-assessable processes (no tracked outputs) are excluded too: the
    store cannot confirm them, so counting them either way would be a guess.
    The single rule every completeness consumer calls — they can never drift
    apart from it.
    """
    return proc_state is ProcessState.WAIVED or not is_assessable(process)


def process_state(
    process: Process, project: Project, session: Session, as_of: date
) -> ProcessState:
    """Compute one process's state for ``project`` as of ``as_of``."""
    decision = latest_sign_off(session, "process", process_subject_ref(process, project), as_of)
    if decision is not None:
        if decision.decision == "waived":
            return ProcessState.WAIVED
        if decision.decision in _DONE_DECISIONS:
            return ProcessState.SIGNED_OFF

    # PRODUCED is judged on required tracked outputs alone; a present optional
    # output is evidence of activity (IN_PROGRESS) but never demotes PRODUCED
    # and never promotes to it.
    required = [
        kind
        for kind in process.outputs
        if mapping.is_tracked(kind) and kind not in process.optional_outputs
    ]
    if not required:
        return ProcessState.NOT_STARTED
    present = [kind for kind in required if mapping.resolve(kind, project, session, as_of).present]
    if len(present) == len(required):
        return ProcessState.PRODUCED
    if present:
        return ProcessState.IN_PROGRESS
    optional = (
        kind
        for kind in process.outputs
        if kind in process.optional_outputs and mapping.is_tracked(kind)
    )
    if any(mapping.resolve(kind, project, session, as_of).present for kind in optional):
        return ProcessState.IN_PROGRESS
    return ProcessState.NOT_STARTED


def project_process_states(
    project: Project, session: Session, as_of: date
) -> tuple[tuple[Process, ProcessState], ...]:
    """Every catalog process paired with its state for ``project``, in catalog order."""
    return tuple(
        (process, process_state(process, project, session, as_of)) for process in catalog.PROCESSES
    )


def completeness(project: Project, session: Session, as_of: date) -> float | None:
    """Share of assessable, non-waived processes that are produced or signed off.

    Waived processes are excluded — tailoring them out must not count against the
    project. Processes with no tracked outputs are excluded too: the store cannot
    confirm them, so counting them either way would be a guess. ``None`` means
    there is nothing to assess.
    """
    counted = 0
    done = 0
    for process, state in project_process_states(project, session, as_of):
        if excluded_from_completeness(process, state):
            continue
        counted += 1
        if state in (ProcessState.PRODUCED, ProcessState.SIGNED_OFF):
            done += 1
    if counted == 0:
        return None
    return done / counted


def current_sign_off(rows: Sequence[SignOff], as_of: date | None) -> SignOff | None:
    """The current decision in one subject's ledger slice, bounded by ``as_of``.

    ``rows`` is a subject's history in ascending (signed_at, id) order — the order
    both prefetch caches and ``latest_sign_off`` build. The newest entry wins,
    skipping decisions recorded against an assessment date (``SignOff.as_of``)
    later than the as-of asked about: a sign-off made this week must not rewrite
    last month's page, feed or trend point. A row with no recorded assessment
    date applies at every as-of, and ``as_of=None`` reads the slice unbounded.
    """
    for row in reversed(rows):
        if as_of is None or row.as_of is None or row.as_of <= as_of:
            return row
    return None
