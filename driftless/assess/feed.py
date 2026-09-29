"""The attention feed: one ranked list of threats and incomplete-data signals.

``attention_feed`` is the canonical ranking — the web renders its order verbatim
and never re-ranks. Threats come from ``engine.top_threats`` (sign-off
suppression is reused, never reimplemented) with score, severity and description
carried over; incomplete-data signals (no status ever filed, stale status, low
process completeness) carry fixed scores below the worked-example red band so a
red threat usually leads, ordered no_status > stale_status > low_completeness.
Ordering is severity-aware by construction: every RED threat ranks above every
incomplete-data signal regardless of raw score, because some evaluators can
emit a red threat scoring under the signals' fixed floor and severity must
still win. Non-red threats (amber, green, unknown) keep ranking against the
signals by score, as before. Items sort by (red-first, score desc, id asc) — a
total, deterministic order. Pure and as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless.assess import engine
from driftless.assess.model import RagStatus
from driftless.models import Project, StatusSnapshot
from driftless.pmbok import mapping, state
from driftless.wizard import engine as wizard

AttentionKind = Literal["threat", "no_status", "stale_status", "low_completeness"]

#: Days after which the latest status snapshot counts as stale — the SAME
#: constant ``mapping.STATUS_CADENCE_DAYS`` holds status_report to (not a copy):
#: loosening the cadence policy can't desync the feed's staleness read from the
#: communications evaluator's.
STALE_AFTER_DAYS = mapping.STATUS_CADENCE_DAYS

#: Completeness share below which the process record itself is an attention item.
LOW_COMPLETENESS_THRESHOLD = 0.25

#: Fixed, test-pinned (score, base action) per incomplete-data kind. These
#: scores sit below a typical red threat's score, but the red-outranks-signal
#: guarantee is enforced structurally by ``_rank``, not by that gap alone.
_SIGNALS: dict[AttentionKind, tuple[float, str]] = {
    "no_status": (0.09, "File a first status snapshot."),
    "stale_status": (0.06, "File a fresh status snapshot."),
    "low_completeness": (0.03, "Produce the missing process outputs."),
}

#: One fixed recommended move per threat kind.
_THREAT_ACTIONS: dict[str, str] = {
    "integration": "Run integrated change control and escalate to the sponsor.",
    "scope": "Baseline the approved scope changes.",
    "schedule": "Re-plan the slipped milestones.",
    "cost": "Re-estimate cost at completion.",
    "quality": "Re-measure the failing or stale quality metrics.",
    "resource": "Rebalance the over-allocated resources.",
    "communications": "Issue a fresh status report.",
    "risk": "Plan responses or top up contingency.",
    "procurement": "Resolve the procurement disputes or lapses.",
    "stakeholder": "Re-engage the high-influence stakeholders.",
}


@dataclass(frozen=True)
class AttentionItem:
    """One feed entry: a threat or an incomplete-data signal, on one score scale."""

    id: str
    kind: AttentionKind
    severity: RagStatus
    score: float
    description: str
    action: str
    project_id: int
    project_name: str


def _rank(item: AttentionItem) -> tuple[int, float, str]:
    """Sort key: every red item ranks before every non-red item, by construction.

    Rank 0 for ``severity == "red"``, rank 1 for everything else (amber, green,
    unknown threats, and every incomplete-data signal, which is always
    ``"unknown"``). Within a rank, score desc then id asc — unchanged from the
    score-only order this replaces, so amber-vs-signal ordering stays exactly
    as it was; only the red guarantee is new.
    """
    return (0 if item.severity == "red" else 1, -item.score, item.id)


def attention_feed(session: Session, as_of: date) -> tuple[AttentionItem, ...]:
    """Every project's threats and incomplete-data signals, most pressing first.

    Contract: this order is final — the web renders it verbatim, never re-ranks.
    Every red threat ranks above every incomplete-data signal regardless of raw
    score; ties within that split break by score desc, then id asc.
    """
    projects = list(session.scalars(select(Project).order_by(Project.name, Project.id)))
    names = {p.id: p.name for p in projects}
    items: list[AttentionItem] = []
    for t in engine.top_threats(session, as_of):
        pid = int(t.source_ref.rsplit(":", 1)[1])  # every evaluator refs "project:<id>"
        action = _THREAT_ACTIONS.get(t.kind, f"Work the {t.kind} threat.")
        name = names.get(pid, f"project {pid}")
        items.append(
            AttentionItem(
                f"threat:{t.id}", "threat", t.severity, t.score, t.description, action, pid, name
            )
        )

    # Latest snapshot per project from ONE grouped query — never one per project.
    latest: dict[int, date] = {
        pid: taken_on
        for pid, taken_on in session.execute(
            select(StatusSnapshot.project_id, func.max(StatusSnapshot.taken_on))
            .where(StatusSnapshot.taken_on <= as_of)
            .group_by(StatusSnapshot.project_id)
        ).all()
    }

    # ``state.prefetched`` bounds the per-project completeness/wizard walk below
    # to a fixed query set — statements do not scale with the project count,
    # the same guarantee ``rollup.business_process_cells`` already relies on for
    # the identical per-process walk (pinned by ``test_perf_n1``).
    with state.prefetched(session, projects):
        for project in projects:
            signals: list[tuple[AttentionKind, str]] = []
            taken = latest.get(project.id)
            if taken is None:
                signals.append(("no_status", f"{project.name} has never filed a status snapshot."))
            elif (as_of - taken).days > STALE_AFTER_DAYS:
                age = (as_of - taken).days
                signals.append(
                    ("stale_status", f"{project.name}'s latest status is {age} days old.")
                )
            share = state.completeness(project, session, as_of)
            if share is None or share < LOW_COMPLETENESS_THRESHOLD:
                detail = "nothing assessable yet" if share is None else f"{share:.0%} complete"
                signals.append(("low_completeness", f"{project.name}'s process record: {detail}."))
            if not signals:
                continue
            # Wizard enrichment only for already-flagged projects — it enriches, not spams.
            step = wizard.next_step(session, project, as_of)
            for kind, description in signals:
                score, action = _SIGNALS[kind]
                if step is not None:
                    action = f"{action} Wizard's next process: {step.name}."
                # severity "unknown": incomplete data is missing knowledge, not assessed risk.
                item_id = f"{kind}:project:{project.id}"
                items.append(
                    AttentionItem(
                        item_id,
                        kind,
                        "unknown",
                        score,
                        description,
                        action,
                        project.id,
                        project.name,
                    )
                )

    items.sort(key=_rank)
    return tuple(items)


def trend_delta(score: float, prior_score: float | None) -> dict[str, Any]:
    """Week-over-week trend for one item, matched to its prior-week self by id.

    Mirrors ``driftless.web.views._trend_delta`` exactly -- same rounding, same
    up/down/flat/new rule -- so a viewer reads score direction identically on the
    threat board and the attention rail. ``new`` when the item had no counterpart
    a week ago; otherwise the rounded score change drives ``dir`` -- ``up``
    worsened (higher score is worse), ``down`` improved, ``flat`` unchanged --
    with the signed ``amount`` carried for display. Lives here rather than in
    ``web`` so the rail can use it without assess importing web.
    """
    if prior_score is None:
        return {"dir": "new", "amount": None}
    amount = round(score - prior_score, 4)
    direction = "up" if amount > 0 else "down" if amount < 0 else "flat"
    return {"dir": direction, "amount": amount}


def attention_trends(
    session: Session, as_of: date, current: Sequence[AttentionItem]
) -> dict[str, dict[str, Any]]:
    """Week-over-week trend for every item in ``current``, keyed by item id.

    ``current`` is the caller's ALREADY-COMPUTED feed at ``as_of`` -- it is never
    recomputed here. Only the feed a week earlier (``as_of - 7d``) is fetched, so
    a render that also calls :func:`attention_feed` for ``current`` runs the feed
    exactly twice total (current + prior), never once per item. An item absent
    from the prior week's feed (a brand-new threat or signal) reads ``new``;
    otherwise :func:`trend_delta` compares its score to its prior-week self,
    matched by the SAME stable item id both weeks use. Purely annotates -- the
    caller's order and contents are untouched.
    """
    prior = {item.id: item.score for item in attention_feed(session, as_of - timedelta(days=7))}
    return {item.id: trend_delta(item.score, prior.get(item.id)) for item in current}
