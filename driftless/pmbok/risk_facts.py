"""Response-planning facts an evaluator, page or report can each read the same way.

The small exposure arithmetic a filed response changes — residual exposure, the
schedule and cost impact of the responses on file, and which open risks carry no
response at all — computed here, once, so the threat board, the gantt note, the
cost workbench line and the risk report cannot print different numbers for the
same store.

``driftless.calc.risk`` (a sibling branch, #331) will eventually own this
arithmetic; until it lands this module is the one place it happens, built as a
thin adapter over ``adapters.project_rows`` so a later import swaps the body
without moving any of the callers below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.models import Project, Risk, RiskResponse
from driftless.models.records import OPEN_RISK_STATUSES
from driftless.pmbok import mapping


@dataclass(frozen=True)
class RiskResponseFacts:
    """One project's response-planning read, as of a date.

    ``residual_exposure`` sums, over every OPEN risk, the latest filed response's
    ``residual_probability * residual_impact`` — or, for a risk with no response on
    file, its own raw ``probability * impact``: nothing has been done to move it, so
    its full exposure still stands. ``unanswered_risk_ids`` names exactly those.
    """

    residual_exposure: float
    responded_schedule_days: int
    responded_cost: float
    unanswered_risk_ids: tuple[int, ...]


def latest_by_risk(responses: list[RiskResponse], as_of: date) -> dict[int, RiskResponse]:
    """The most recently FILED response per risk as of ``as_of`` — recording order
    (``id``) among the responses dated on or before it, the same "latest recorded
    wins" rule ``StatusSnapshot``'s same-date corrections use. A response filed for
    a later date is not yet a fact at an earlier as-of, so it never reaches an
    earlier render of the register, the reserve line or the risk report."""
    latest: dict[int, RiskResponse] = {}
    for response in sorted(responses, key=lambda r: r.id):
        if response.as_of <= as_of:
            latest[response.risk_id] = response
    return latest


def gather(session: Session, project: Project, as_of: date) -> RiskResponseFacts:
    """This project's response-planning facts, as of ``as_of`` — pure, no wall clock."""
    all_risks = adapters.project_rows(session, Risk, project.id)
    risks = [r for r in all_risks if r.status in OPEN_RISK_STATUSES]
    # ``mapping.rows_for``, not ``adapters.project_rows``: this read is the newest
    # of the two, and ``report.gather.business_nodes`` opens its OWN nested
    # ``assess.adapters.prefetched`` scope, which pops the whole outer scope on
    # exit rather than restoring it (``mapping.prefetched`` does restore, so its
    # scope survives that nesting) -- see ``mapping.rows_for``.
    latest = latest_by_risk(mapping.rows_for(session, RiskResponse, project.id), as_of)
    residual_exposure = 0.0
    responded_days = 0
    responded_cost = 0.0
    unanswered: list[int] = []
    for risk in risks:
        response = latest.get(risk.id)
        if response is None:
            residual_exposure += risk.probability * risk.impact
            unanswered.append(risk.id)
            continue
        residual_exposure += response.residual_probability * response.residual_impact
        responded_days += response.schedule_days
        responded_cost += response.cost_of_response
    return RiskResponseFacts(
        residual_exposure=round(residual_exposure, 2),
        responded_schedule_days=responded_days,
        responded_cost=round(responded_cost, 2),
        unanswered_risk_ids=tuple(sorted(unanswered)),
    )
