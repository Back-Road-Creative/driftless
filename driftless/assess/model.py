"""The assessment value objects: what an evaluator produces for one knowledge area.

An ``Assessment`` is computed, never stored — a pure function of the store and an
explicit as-of date — so it cannot drift and regenerates byte-identically. A
``Threat`` is a named, rankable problem; an ``Action`` is a recommended next step
drawn from a PMBOK tool or technique (its ``pmbok_tt`` is a ``TT_CATALOG``
member). A threat's ``score`` is its numeric severity, higher being worse: it is
what ranks the feed and what a sign-off is measured against, so suppressing a
threat cannot hide a later regression that pushes the score back up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from driftless.calc.rollup import RAG_SEVERITY
from driftless.calc.rollup import RagStatus as RagStatus  # explicit re-export for the evaluators
from driftless.naming import technique_slug
from driftless.pmbok.definitions import TECHNIQUES, TechniqueDefinition

#: Techniques with a working launchable assistant, keyed by ``pmbok_tt``, mapping to
#: the route that launches it — a format string taking ``project_id`` OR
#: ``department_id``, since an assistant runs against one project or one department
#: (``Action.launch_href`` reads ``target_ref``'s own shape to know which). Empty
#: until the first assistant shipped, so a technique with no entry here still falls
#: back to "reference only". This is the one place a later PR adds a technique's
#: launch target when its assistant ships; nothing that renders an ``Action`` needs
#: to change, and no per-technique list has to be kept in sync by hand. The
#: earned-value calculator serves both cost techniques Control Costs (7.4) names,
#: since TCPI is computed FROM the same earned-value snapshot the page already shows
#: rather than standing apart from it.
#:
#: Every technique that would honestly fit the department workspace's demand-versus-
#: capacity or stakeholder sections (``resource_optimization``,
#: ``stakeholder_analysis``, ``stakeholder_engagement_assessment_matrix``) is ALREADY
#: claimed here by a project-scoped action (the schedule and stakeholder evaluators),
#: and a route is keyed by technique alone — one technique cannot point at a project
#: address and a department address at once. Rather than misroute an unrelated
#: technique to earn a mode it does not deserve, the department workspace's own
#: sections stay reference-only until a technique genuinely free of a project-scoped
#: claim fits one of them.
ASSISTANT_ROUTES: dict[str, str] = {
    "stakeholder_analysis": "/projects/{project_id}/assist/stakeholders",
    "stakeholder_engagement_assessment_matrix": "/projects/{project_id}/assist/stakeholders",
    "communication_methods": "/projects/{project_id}/assist/stakeholders",
    "communication_technology": "/projects/{project_id}/assist/stakeholders",
    "earned_value_analysis": "/projects/{project_id}/assist/earned-value",
    "to_complete_performance_index": "/projects/{project_id}/assist/earned-value",
    # The risk-response planner serves all four response-strategy techniques (11.5):
    # threats, opportunities, contingent responses and overall project risk each land
    # on the one register/what-if page, since a filed response is the one write every
    # one of them recommends.
    "strategies_for_threats": "/projects/{project_id}/assist/risk-responses",
    "strategies_for_opportunities": "/projects/{project_id}/assist/risk-responses",
    "contingent_response_strategies": "/projects/{project_id}/assist/risk-responses",
    "strategies_for_overall_project_risk": "/projects/{project_id}/assist/risk-responses",
    # The EMV decision-tree calculator: a standalone what-if with no register of
    # its own, unlike the risk-response planner above.
    "decision_tree_analysis": "/projects/{project_id}/assist/decision-tree",
    # The P x I scoring worksheet: read-only, unlike the planner above.
    "risk_probability_and_impact_assessment": "/projects/{project_id}/assist/risk-pi",
    # The requirements/WBS worksheet: filing a requirement, tracing it, decomposing the
    # WBS and recording acceptance all land on the one scope-records page (5.4 Create WBS
    # is what this route serves for "decomposition").
    "decomposition": "/projects/{project_id}/assist/requirements",
    # The team assist page: the RBS, the stored RACI, acquisitions and training gaps,
    # the team-assessment trend and open conflicts with their actions all land on one
    # page, since filing any one of those rows is the defining action every one of
    # these nine Resource Management techniques recommends.
    "organizational_theory": "/projects/{project_id}/assist/team",
    "pre_assignment": "/projects/{project_id}/assist/team",
    "virtual_teams": "/projects/{project_id}/assist/team",
    "colocation": "/projects/{project_id}/assist/team",
    "training": "/projects/{project_id}/assist/team",
    "team_building": "/projects/{project_id}/assist/team",
    "recognition_and_rewards": "/projects/{project_id}/assist/team",
    "individual_and_team_assessments": "/projects/{project_id}/assist/team",
    "conflict_management": "/projects/{project_id}/assist/team",
    "product_analysis": "/projects/{project_id}/assist/scope",
    "context_diagram": "/projects/{project_id}/assist/scope",
    "prototypes": "/projects/{project_id}/assist/scope",
    "benchmarking": "/projects/{project_id}/assist/scope",
    "inspection": "/projects/{project_id}/assist/scope",
    # The procurement calculator serves all three techniques Plan Procurement
    # Management (12.1) and Conduct Procurements (12.2) name that a deterministic
    # worksheet could serve: make-or-buy, bid scoring and contract-type guidance.
    "make_or_buy_analysis": "/projects/{project_id}/assist/procurement",
    "proposal_evaluation": "/projects/{project_id}/assist/procurement",
    "source_selection_analysis": "/projects/{project_id}/assist/procurement",
    # Schedule's agile_release_planning: WIP, throughput, cycle/lead time, burndown,
    # burnup, cumulative flow and the velocity-band release forecast — the flow
    # calculator, ``pmbok.flow_facts`` behind it.
    "agile_release_planning": "/projects/{project_id}/flow",
    "voting": "/projects/{project_id}/assist/decisions",
    "multicriteria_decision_analysis": "/projects/{project_id}/assist/decisions",
    "autocratic_decision_making": "/projects/{project_id}/assist/decisions",
    "focus_groups": "/projects/{project_id}/assist/decisions",
    "meetings": "/projects/{project_id}/assist/decisions",
    # The cost workbench: aggregation, reserves, funding limits, financing, the
    # cash-flow S-curve, run rate and the four estimating techniques all share
    # this one page (web/assist_cost.py); cost of quality routes to the quality
    # workbench below, where the measurements it is judged over live.
    "cost_aggregation": "/projects/{project_id}/assist/cost",
    "reserve_analysis": "/projects/{project_id}/assist/cost",
    "funding_limit_reconciliation": "/projects/{project_id}/assist/cost",
    "financing": "/projects/{project_id}/assist/cost",
    "historical_information_review": "/projects/{project_id}/assist/cost",
    "analogous_estimating": "/projects/{project_id}/assist/cost",
    "parametric_estimating": "/projects/{project_id}/assist/cost",
    "three_point_estimating": "/projects/{project_id}/assist/cost",
    "bottom_up_estimating": "/projects/{project_id}/assist/cost",
    # The quality workbench (web/assist_quality.py) serves control charts, a
    # Pareto split and statistical sampling too, but those name no TT_CATALOG
    # member of their own — only the three techniques below are routed here.
    "root_cause_analysis": "/projects/{project_id}/assist/quality",
    "cost_of_quality": "/projects/{project_id}/assist/quality",
    "audits": "/projects/{project_id}/assist/quality",
    # The schedule-network calculator: one page draws the network, the critical
    # path(s) and float, crash/fast-track/levelling previews and the critical-chain
    # buffer extension, so every technique it covers shares this one route.
    "critical_path_method": "/projects/{project_id}/assist/schedule",
    "precedence_diagramming_method": "/projects/{project_id}/assist/schedule",
    "leads_and_lags": "/projects/{project_id}/assist/schedule",
    "schedule_network_analysis": "/projects/{project_id}/assist/schedule",
    "resource_optimization": "/projects/{project_id}/assist/schedule",
    "schedule_compression": "/projects/{project_id}/assist/schedule",
    "critical_chain_method": "/projects/{project_id}/assist/schedule",
}

#: Numeric weight per RAG severity — used to rank threats across knowledge areas
#: and to fold a leaf's RAG in ``report.gather``. ``unknown`` (nothing to assess)
#: sits below green so it never wins a worst-of fold. Derived from calc's
#: canonical ``RAG_SEVERITY`` ranking so the two layers cannot drift apart.
SEVERITY_WEIGHT: dict[RagStatus, float] = {
    status: float(weight) for status, weight in RAG_SEVERITY.items()
}

#: Whether the assessment had current evidence to judge. This is deliberately
#: separate from RAG: green may be supported by evidence, while an inapplicable
#: area is not a missing control and must say so.
Coverage = Literal["measured", "stale", "missing", "not_applicable"]


@dataclass(frozen=True)
class Threat:
    """A named, rankable problem an evaluator raised.

    ``id`` is severity-independent (``"cost:project:42"``) so the same threat
    keeps its identity as its ``score`` moves; ``source_ref`` points at what it is
    about. ``score`` is the numeric severity a sign-off is compared against.

    ``open_no_response`` is a ranking tie-break only, never part of ``score``: an
    open risk with no filed response outranks an equal-severity, equal-score
    threat whose worst risks all carry one. ``engine._rank_key`` reads it after
    ``score`` so it can only decide a tie, never move a threat across the
    red/amber/green line or change the number a sign-off is compared against.
    """

    id: str
    kind: str
    severity: RagStatus
    score: float
    description: str
    source_ref: str
    open_no_response: bool = False


@dataclass(frozen=True)
class Action:
    """A recommended next step: a PMBOK tool/technique applied to a target.

    ``pmbok_tt`` must name a ``TECHNIQUES`` entry — asserted in ``__post_init__``
    rather than left for a renderer to discover, since a recommendation naming a
    technique the registry does not know cannot be presented at all, honestly or
    otherwise. Every other fact an evaluator would need to render or launch the
    technique (its display name, whether it can be launched at all, and where its
    reference material lives) is derived from that registry, never stored here, so it
    cannot drift out of sync with it.

    It once also carried ``reference_process_id`` — a scan of the ITTO catalog for a
    process naming the technique, which is what the old ``/pmbok/{id}#tt-{slug}``
    address was built from. ``reference_href`` replaced that address with the
    technique's own page, and nothing has read the process id since; it is gone rather
    than left half-alive, and with it this module's import of the process catalog.
    Which techniques a process names is still derived where it is actually needed,
    straight off ``catalog.PROCESSES``.
    """

    id: str
    label: str
    pmbok_tt: str
    rationale: str
    target_ref: str

    def __post_init__(self) -> None:
        if self.pmbok_tt not in TECHNIQUES:
            raise AssertionError(
                f"Action {self.id!r} names {self.pmbok_tt!r}, which is not a "
                "registered technique in driftless.pmbok.definitions.TECHNIQUES"
            )

    @property
    def technique(self) -> TechniqueDefinition:
        """This action's technique, by its registry entry — never a raw key."""
        return TECHNIQUES[self.pmbok_tt]

    @property
    def launch_href(self) -> str | None:
        """Where this action's technique can actually be RUN, or ``None`` if it
        cannot — driven by ``ASSISTANT_ROUTES``. A route is a format string taking
        ``project_id`` OR ``department_id``, read off ``target_ref``'s own shape
        (``"project:{id}"`` or ``"department:{id}"``, the two shapes evaluators
        build it in) — the one place that parsing happens, so a renderer never
        repeats it. A ``target_ref`` matching neither shape returns ``None`` rather
        than raising: a route that cannot be addressed is the same as no route."""
        route = ASSISTANT_ROUTES.get(self.pmbok_tt)
        if route is None:
            return None
        prefix, _, target_id = self.target_ref.partition(":")
        if not target_id or prefix not in ("project", "department"):
            return None  # a bare "project:" is no address — never a half-filled one
        if prefix == "project" and "{project_id}" in route:
            return route.format(project_id=target_id)
        if prefix == "department" and "{department_id}" in route:
            return route.format(department_id=target_id)
        return None

    @property
    def reference_href(self) -> str:
        """Where this action's technique can be READ ABOUT: its own page in the
        technique library, which explains when to use it, when not to, the steps in
        order, what it produces, what usually goes wrong and a worked example.

        A ``str``, never ``None`` — and that totality is structural rather than
        lucky. ``__post_init__`` refuses any ``pmbok_tt`` outside ``TECHNIQUES``,
        ``/techniques/{slug}`` is keyed by a slug index built over exactly those
        keys, and ``technique_slug`` is a bijection across it
        (``tests/test_web_techniques`` proves both halves), so every action a
        renderer can hold addresses a page that answers. No surface needs a
        "nowhere to send you" branch.

        This used to point at ``/pmbok/{process}#tt-{slug}`` — an anchor on the ITTO
        list of some process that names the technique, which shows its *name*, one
        hop short of the explanation. Worse, a technique no process names (a
        Driftless extension is tied to no process by definition) got ``None``, so
        four surfaces told the reader there was no linked process and nothing to
        read, about a technique whose full page was already being served. Those
        branches are gone. The ITTO anchor still exists as a deep-link target for a
        reader scanning a process; a recommendation no longer stops there.
        """
        return f"/techniques/{technique_slug(self.pmbok_tt)}"

    @property
    def is_reference_only(self) -> bool:
        """True whenever this action cannot be launched — every technique outside
        ``ASSISTANT_ROUTES``, plus the rare routed one whose ``target_ref`` cannot
        fill the route's placeholder."""
        return self.launch_href is None


@dataclass(frozen=True)
class Assessment:
    """One knowledge area's reading for a project as of a date. Computed, never stored."""

    kind: str
    as_of: date
    risk_score: float
    status: RagStatus
    threats: tuple[Threat, ...] = field(default=())
    actions: tuple[Action, ...] = field(default=())
    coverage: Coverage = "measured"
