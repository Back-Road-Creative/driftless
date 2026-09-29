"""``TECHNIQUES``: the technique registry, one ``TechniqueDefinition`` per member
of ``driftless.pmbok.tt.FAMILIES`` (and so of ``TT_CATALOG`` too — the two are
literally the same set). Adding a technique to a family in ``tt.py``
automatically gives it a definition here; there is no second list to update.

The identity fields — ``key``, ``display_name``, ``family``, ``source`` and
``source_version`` — are populated by this module directly, for every catalog
member. ``display_name`` is ``driftless.naming.humanize`` called on the key, with
``_DISPLAY_NAME_OVERRIDES`` naming the few terms of art that rule gets wrong; the
rule itself is never restated here. The explanation fields (summary, steps, pitfalls, ...) come from
``driftless.pmbok.technique_content``, which composes them out of one module
per family — see that package's docstring. Every catalog key has content today,
and ``tests/test_technique_totality.py`` walks the whole catalog and fails on the
first key and field that does not; structurally, though, a key no content module
claims still gets a ``TechniqueDefinition`` with those fields empty, so a
technique added to ``tt.py`` appears here immediately and is caught there rather
than crashing a page.

Provenance is read from ``tt.EXTENSIONS`` rather than restated: a member of
that set is a technique Driftless added itself, so it gets ``EXTENSION_SOURCE``
and no edition string, and everything else gets ``PMBOK_SOURCE`` plus the one
``PMBOK_SOURCE_VERSION``. Adding an extension in ``tt.py`` therefore cannot
leave a false PMBOK citation behind here.

``assistance_mode`` is ``AssistanceMode.GUIDE`` for every technique outside
``_ASSISTANCE_MODE_OVERRIDES`` — ``assess.model.ASSISTANT_ROUTES`` is the only
thing that knows whether a technique can be RUN rather than merely read about,
so "we can explain this" is the honest ceiling for everything not named there.
``tests/test_technique_definitions.py`` walks both and fails the moment a route
ships without its mode being raised here to match.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from driftless.naming import humanize
from driftless.pmbok.technique_content import TechniqueContent, collect_content
from driftless.pmbok.tt import EXTENSIONS, FAMILIES

#: What a technique's identity is drawn from. ``PMBOK_SOURCE`` is the authorized
#: standard; ``EXTENSION_SOURCE`` is a technique Driftless itself added to the
#: vocabulary because no process in the edition names it (``tt.EXTENSIONS`` is the
#: set, and the only place membership is decided).
PMBOK_SOURCE = "pmbok_6"
EXTENSION_SOURCE = "extension"

#: The one place the edition string is written, so it lives in a field rather than
#: in prose. Only a ``PMBOK_SOURCE`` definition carries it: an extension cites no
#: edition, and inventing one for it would be a false citation.
PMBOK_SOURCE_VERSION = "PMBOK Guide, 6th edition"


class AssistanceMode(str, Enum):
    """How much help a later feature can give, weakest first (the default)."""

    GUIDE = "guide"
    WORKSHEET = "worksheet"
    CALCULATOR = "calculator"
    MODELER = "modeler"


class TechniqueFamily(str, Enum):
    """The technique groupings ``tt.py``'s ``FAMILIES`` names directly — one member
    here per key there, which ``tests/test_technique_definitions`` walks."""

    GENERAL = "general"
    INTEGRATION = "integration"
    SCOPE = "scope"
    SCHEDULE = "schedule"
    COST = "cost"
    QUALITY = "quality"
    RESOURCE = "resource"
    RISK = "risk"
    PROCUREMENT = "procurement"
    STAKEHOLDER = "stakeholder"


@dataclass(frozen=True)
class TechniqueDefinition:
    """One technique's identity plus its explanation content, which
    ``technique_content``'s per-family modules supply."""

    key: str
    display_name: str
    family: TechniqueFamily
    source: str
    source_version: str = ""
    summary: str = ""
    when_to_use: str = ""
    when_to_avoid: str = ""
    steps: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    pitfalls: tuple[str, ...] = ()
    worked_example: str = ""
    further_reading: tuple[str, ...] = ()
    assistance_mode: AssistanceMode = AssistanceMode.GUIDE


#: The keys ``driftless.naming.humanize`` gets wrong, and what they should read as.
#: That rule now lower-cases minor words mid-label and gets "for" right on its
#: own (``design_for_x`` needs no entry here any more); the one term of art it
#: still cannot reach is the hyphen in "to-complete". Every other key takes the
#: rule unaltered — so this table is the exception list, never a second naming
#: scheme.
_DISPLAY_NAME_OVERRIDES = {
    "to_complete_performance_index": "To-Complete Performance Index",
}

#: Every technique whose ``assess.model.ASSISTANT_ROUTES`` entry has shipped, and the
#: mode its calculator earns. The one place that raises a technique's ceiling above
#: ``GUIDE`` — ``tests/test_technique_definitions.py`` fails until this table and
#: ``ASSISTANT_ROUTES`` name exactly the same keys.
_ASSISTANCE_MODE_OVERRIDES: dict[str, AssistanceMode] = {
    "earned_value_analysis": AssistanceMode.CALCULATOR,
    "to_complete_performance_index": AssistanceMode.CALCULATOR,
    # The risk-response planner: a register a reader files one response into (the
    # WORKSHEET half) plus a no-write residual-exposure recompute (the CALCULATOR
    # half) — WORKSHEET is the ceiling raised here since filing a row, not merely
    # computing a figure, is the page's defining action.
    "strategies_for_threats": AssistanceMode.WORKSHEET,
    "strategies_for_opportunities": AssistanceMode.WORKSHEET,
    "contingent_response_strategies": AssistanceMode.WORKSHEET,
    "strategies_for_overall_project_risk": AssistanceMode.WORKSHEET,
    "decision_tree_analysis": AssistanceMode.CALCULATOR,
    "risk_probability_and_impact_assessment": AssistanceMode.CALCULATOR,
    # The requirements/WBS worksheet: a traceability matrix and a WBS a reader
    # builds by filing rows, the defining action of a WORKSHEET.
    "decomposition": AssistanceMode.WORKSHEET,
    # The team assist page: the RBS, the stored RACI, acquisitions and training
    # gaps, the team-assessment trend and open conflicts with their actions —
    # a reader files an assignment, an assessment or a conflict/action, the
    # defining action of a WORKSHEET.
    "organizational_theory": AssistanceMode.WORKSHEET,
    "pre_assignment": AssistanceMode.WORKSHEET,
    "virtual_teams": AssistanceMode.WORKSHEET,
    "colocation": AssistanceMode.WORKSHEET,
    "training": AssistanceMode.WORKSHEET,
    "team_building": AssistanceMode.WORKSHEET,
    "recognition_and_rewards": AssistanceMode.WORKSHEET,
    "individual_and_team_assessments": AssistanceMode.WORKSHEET,
    "conflict_management": AssistanceMode.WORKSHEET,
    "product_analysis": AssistanceMode.WORKSHEET,
    "context_diagram": AssistanceMode.WORKSHEET,
    "prototypes": AssistanceMode.WORKSHEET,
    "benchmarking": AssistanceMode.WORKSHEET,
    "inspection": AssistanceMode.WORKSHEET,
    "stakeholder_analysis": AssistanceMode.CALCULATOR,
    "stakeholder_engagement_assessment_matrix": AssistanceMode.CALCULATOR,
    "communication_methods": AssistanceMode.CALCULATOR,
    "communication_technology": AssistanceMode.CALCULATOR,
    "make_or_buy_analysis": AssistanceMode.CALCULATOR,
    "proposal_evaluation": AssistanceMode.CALCULATOR,
    "source_selection_analysis": AssistanceMode.CALCULATOR,
    "agile_release_planning": AssistanceMode.CALCULATOR,
    "voting": AssistanceMode.CALCULATOR,
    "multicriteria_decision_analysis": AssistanceMode.CALCULATOR,
    "autocratic_decision_making": AssistanceMode.WORKSHEET,
    "focus_groups": AssistanceMode.WORKSHEET,
    "meetings": AssistanceMode.WORKSHEET,
    "cost_aggregation": AssistanceMode.CALCULATOR,
    "reserve_analysis": AssistanceMode.CALCULATOR,
    "funding_limit_reconciliation": AssistanceMode.CALCULATOR,
    "financing": AssistanceMode.CALCULATOR,
    "historical_information_review": AssistanceMode.CALCULATOR,
    "analogous_estimating": AssistanceMode.CALCULATOR,
    "parametric_estimating": AssistanceMode.CALCULATOR,
    "three_point_estimating": AssistanceMode.CALCULATOR,
    "bottom_up_estimating": AssistanceMode.CALCULATOR,
    "root_cause_analysis": AssistanceMode.WORKSHEET,
    "cost_of_quality": AssistanceMode.CALCULATOR,
    "audits": AssistanceMode.WORKSHEET,
    # The schedule-network calculator: CALCULATOR for the six techniques it merely
    # reads and previews, MODELER for critical chain method, whose buffers are a
    # standing model the page keeps recomputed against the network's current state
    # rather than a single figure read off it.
    "critical_path_method": AssistanceMode.CALCULATOR,
    "precedence_diagramming_method": AssistanceMode.CALCULATOR,
    "leads_and_lags": AssistanceMode.CALCULATOR,
    "schedule_network_analysis": AssistanceMode.CALCULATOR,
    "resource_optimization": AssistanceMode.CALCULATOR,
    "schedule_compression": AssistanceMode.CALCULATOR,
    "critical_chain_method": AssistanceMode.MODELER,
}


def _display_name(key: str) -> str:
    """This technique's visible name: the one word-shaping rule, unless this key is
    one of the few the rule gets wrong.

    ``humanize`` is CALLED, never restated here. It used to be restated, and that was
    not tidiness: ``naming.technique_slug`` is built from the same function, so a
    second copy meant rewriting the rule moved every technique URL while every display
    name stayed put — and nothing failed. ``tests/test_technique_definitions`` pins the
    call itself, not merely that the two agree today.
    """
    return _DISPLAY_NAME_OVERRIDES.get(key, humanize(key))


#: Explanation content, keyed by technique key, composed from every family
#: content module ``technique_content`` can discover. A key absent here (no
#: content module has claimed it yet) yields an all-empty ``TechniqueContent``.
_CONTENT: dict[str, TechniqueContent] = collect_content()

_EMPTY_CONTENT = TechniqueContent()


def _source(key: str) -> tuple[str, str]:
    """This technique's ``(source, source_version)``, decided by ``tt.EXTENSIONS``
    membership alone — the single place that records which techniques the edition
    does not tie to a process."""
    if key in EXTENSIONS:
        return EXTENSION_SOURCE, ""
    return PMBOK_SOURCE, PMBOK_SOURCE_VERSION


def _definition(key: str, family: str) -> TechniqueDefinition:
    content = _CONTENT.get(key, _EMPTY_CONTENT)
    source, source_version = _source(key)
    return TechniqueDefinition(
        key=key,
        display_name=_display_name(key),
        family=TechniqueFamily(family),
        source=source,
        source_version=source_version,
        summary=content.summary,
        when_to_use=content.when_to_use,
        when_to_avoid=content.when_to_avoid,
        steps=content.steps,
        outputs=content.outputs,
        pitfalls=content.pitfalls,
        worked_example=content.worked_example,
        further_reading=content.further_reading,
        assistance_mode=_ASSISTANCE_MODE_OVERRIDES.get(key, AssistanceMode.GUIDE),
    )


#: One entry per ``TT_CATALOG`` member, keyed by that member's name.
TECHNIQUES: dict[str, TechniqueDefinition] = {
    key: _definition(key, family) for family, keys in FAMILIES.items() for key in keys
}


#: What each technique family IS, in one plain sentence — the thing a family heading
#: names but does not explain. Keyed by the enum rather than by its string value, so a
#: family added to :class:`TechniqueFamily` and left unexplained fails
#: ``tests/test_web_techniques.py`` rather than reaching a reader as a bare heading.
#: Authored prose, not derived: no registry holds a sentence about a grouping.
FAMILY_EXPLANATIONS: dict[TechniqueFamily, str] = {
    TechniqueFamily.GENERAL: (
        "Techniques that serve any part of a project — gathering information, weighing "
        "options, judging what the numbers are telling you — rather than belonging to one "
        "specialism."
    ),
    TechniqueFamily.INTEGRATION: (
        "Holding the whole project together: choosing what to do, approving changes, and "
        "keeping the separate plans consistent with one another."
    ),
    TechniqueFamily.SCOPE: (
        "Deciding and writing down exactly what the project will deliver, and what it will "
        "not, so later work can be checked against it."
    ),
    TechniqueFamily.SCHEDULE: (
        "Working out the order of the work, how long each piece takes, and when it has to "
        "happen to hit the dates."
    ),
    TechniqueFamily.COST: (
        "Estimating what the work will cost, setting the budget, and tracking the spend "
        "against it as the work proceeds."
    ),
    TechniqueFamily.QUALITY: (
        "Deciding what good enough means for the deliverables, then checking both the work "
        "and the way it is being done against that."
    ),
    TechniqueFamily.RESOURCE: (
        "Finding, assigning and developing the people and equipment the work needs, and "
        "keeping the load on them realistic."
    ),
    TechniqueFamily.RISK: (
        "Finding what could go wrong or unexpectedly right, judging how much it would "
        "matter, and deciding what to do about it in advance."
    ),
    TechniqueFamily.PROCUREMENT: (
        "Deciding what to buy rather than build, choosing who to buy it from, and managing "
        "the agreements that result."
    ),
    TechniqueFamily.STAKEHOLDER: (
        "Working out who is affected by the project, what each of them needs from it, and "
        "how to keep them properly involved."
    ),
}
