"""The assessment engine: run every evaluator, roll up Integration, suppress, rank.

``assess_project`` runs the nine knowledge-area evaluators and adds the
Integration assessment, which is the worst-of its children (integration is the
roll-up, not a separate signal). ``live_threats`` drops threats a sign-off has
suppressed; suppression is robust by construction — a signed-off threat stays
hidden only while its live score is no worse than the score recorded at
sign-off, so pushing the signal past that threshold makes it reappear.
``top_threats`` ranks the live threats across the whole store for the dashboard.

Everything takes an explicit as-of date and reads no wall clock, so an
assessment regenerates byte-identically from the same store.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.evaluators import (
    communications,
    cost,
    procurement,
    quality,
    resource,
    risk,
    schedule,
    scope,
    stakeholder,
)
from driftless.assess.model import Coverage, SEVERITY_WEIGHT, Action, Assessment, Threat
from driftless.calc.rollup import RagStatus
from driftless.models import Project, SignOff
from driftless.models.governance import SUPPRESSING_DECISIONS
from driftless.pmbok import state

# The nine knowledge-area evaluators; Integration is the roll-up added below.
_EVALUATORS = (
    scope,
    schedule,
    cost,
    quality,
    resource,
    communications,
    risk,
    procurement,
    stakeholder,
)


_THREAT_SIGN_OFF_KEY = "driftless.assess.engine.threat_sign_offs"


@contextmanager
def threat_sign_offs(session: Session) -> Iterator[None]:
    """One pass over the THREAT sign-off ledger for the block — every row per
    subject, ascending ``(signed_at, id)``, the order ``state.current_sign_off``
    expects — so :func:`is_suppressed` stops querying once per threat and answers
    any as-of. Public: callers batching suppression checks open it around them."""
    ledger: dict[str, list[SignOff]] = {}
    for row in session.scalars(
        select(SignOff)
        .where(SignOff.subject_kind == "threat")
        .order_by(SignOff.signed_at, SignOff.id)
    ):
        ledger.setdefault(row.subject_ref, []).append(row)
    session.info[_THREAT_SIGN_OFF_KEY] = ledger
    try:
        yield
    finally:
        session.info.pop(_THREAT_SIGN_OFF_KEY, None)


def _worst(statuses: tuple[RagStatus, ...]) -> RagStatus:
    """Worst-child-wins over RAG statuses; green when there are no children."""
    worst: RagStatus = "green"
    for status in statuses:
        if SEVERITY_WEIGHT[status] > SEVERITY_WEIGHT[worst]:
            worst = status
    return worst


def _integration(nine: tuple[Assessment, ...], project: Project, as_of: date) -> Assessment:
    """Integration = worst-of the other knowledge areas, with escalation actions."""
    worst = _worst(tuple(a.status for a in nine))
    score = round(max((a.risk_score for a in nine), default=0.0), 4)
    coverage: Coverage
    if any(a.coverage == "missing" for a in nine):
        coverage = "missing"
    elif any(a.coverage == "stale" for a in nine):
        coverage = "stale"
    elif any(a.coverage == "measured" for a in nine):
        coverage = "measured"
    else:
        coverage = "not_applicable"
    if worst == "green":
        return Assessment("integration", as_of, 0.0, "green", coverage=coverage)

    ref = f"project:{project.id}"
    # Only the clauses with something in them: "amber in —" is not a sentence a
    # reader can act on, and the threat board and hub rail print this verbatim.
    clauses = [
        f"{status} in {', '.join(a.kind for a in nine if a.status == status)}"
        for status in ("red", "amber")
        if any(a.status == status for a in nine)
    ]
    threat = Threat(
        state.threat_subject_ref("integration", project.id),
        "integration",
        worst,
        score,
        f"Overall health is {worst}: {'; '.join(clauses)}.",
        ref,
    )
    actions = (
        Action(
            f"integration:icc:{project.id}",
            "Perform integrated change control",
            "change_control_tools",
            "Route the cross-area impacts through one controlled change decision.",
            ref,
        ),
        Action(
            f"integration:escalate:{project.id}",
            "Escalate to the sponsor",
            "meetings",
            "Bring the red areas to the sponsor for a direction and funding call.",
            ref,
        ),
    )
    return Assessment("integration", as_of, score, worst, (threat,), actions, coverage)


def assess_project(session: Session, project: Project, as_of: date) -> tuple[Assessment, ...]:
    """Every knowledge area's assessment for ``project`` — Integration first, then the nine."""
    nine = tuple(ev.evaluate(session, project, as_of) for ev in _EVALUATORS)
    return (_integration(nine, project, as_of), *nine)


def is_suppressed(session: Session, threat: Threat, as_of: date) -> bool:
    """Whether a sign-off hides ``threat`` at ``as_of``.

    Suppressed only while the latest sign-off recorded against ``as_of`` or
    earlier (``state.current_sign_off`` — a later decision cannot rewrite an
    earlier page or trend point) carries a suppressing decision *and* a recorded
    signal no smaller than the threat's live score — so a regression re-surfaces
    it. A sign-off with no recorded signal never suppresses, so the score always
    has to be captured.
    """
    cached: dict[str, list[SignOff]] | None = session.info.get(_THREAT_SIGN_OFF_KEY)
    latest = (
        state.current_sign_off(cached.get(threat.id, []), as_of)
        if cached is not None
        else state.latest_sign_off(session, "threat", threat.id, as_of)
    )
    if latest is None or latest.decision not in SUPPRESSING_DECISIONS:
        return False
    return latest.signal is not None and threat.score <= latest.signal


def _threats_of(assessments: tuple[Assessment, ...]) -> tuple[Threat, ...]:
    return tuple(threat for assessment in assessments for threat in assessment.threats)


def _rank_key(threat: Threat) -> tuple[float, float, float, str]:
    """Rank by severity, then score, then the no-response tie-break, then id.

    ``open_no_response`` only decides a tie between two threats already equal on
    severity and score — an open risk with no filed response outranks an
    equal-severity, equal-score threat whose worst risks all carry one, without
    moving either one's own score."""
    return (
        SEVERITY_WEIGHT[threat.severity],
        threat.score,
        float(threat.open_no_response),
        threat.id,
    )


def live_threats(session: Session, project: Project, as_of: date) -> tuple[Threat, ...]:
    """A project's unsuppressed threats, most severe first."""
    threats = [
        t
        for t in _threats_of(assess_project(session, project, as_of))
        if not is_suppressed(session, t, as_of)
    ]
    return tuple(sorted(threats, key=_rank_key, reverse=True))


def top_threats(session: Session, as_of: date) -> tuple[Threat, ...]:
    """Every project's unsuppressed threats across the store, ranked for the feed.

    Each project drives every evaluator, and three of them recompute the EVM
    snapshot down to ``line.task``. ``adapters.eager_project`` eager-loads that
    Baseline → Line → Task cascade and the milestones onto the one Project query,
    so the store-wide walk no longer fires a lazy query per baseline line. The
    two scopes below cut the per-PROJECT bill the same way — one batched read per
    project-scoped model the evaluators use, one pass over the threat sign-off
    ledger — for the same threats, ranked identically."""
    projects = list(
        session.scalars(
            select(Project).order_by(Project.name, Project.id).options(*adapters.eager_project())
        )
    )
    with adapters.prefetched(session, projects), threat_sign_offs(session):
        threats = [t for project in projects for t in live_threats(session, project, as_of)]
    return tuple(sorted(threats, key=_rank_key, reverse=True))
