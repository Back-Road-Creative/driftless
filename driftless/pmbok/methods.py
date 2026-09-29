"""``METHODS``: Scrum and Kanban, described in Driftless's own words — never a quote or
close paraphrase of either guide. Scope decided 2026-08-22: Scrum and Kanban only, no
SAFe, no XP. Kanban has no one canonical guide the way Scrum has *The Scrum Guide*, so
``source``/``source_version`` name the specific guide and edition chosen for it.

Each profile carries the FULL canonical set for its guide: Scrum's three
accountabilities, five events, three artifacts and their three commitments, plus its
self-management/empowerment stance; Kanban's six general practices, six change-
management/service-delivery principles, its board and cards, its seven cadences, and
its four standard flow metrics.

``crosswalk`` names the PMBOK-6 process ids or ``TT_CATALOG`` keys a practice most
nearly resembles; empty is allowed only with a ``crosswalk_reason``.
``tests/test_methods.py`` walks the whole registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PracticeKind(str, Enum):
    """What kind of thing a method practice is."""

    ROLE = "role"
    EVENT = "event"
    ARTIFACT = "artifact"
    POLICY = "policy"
    METRIC = "metric"


@dataclass(frozen=True)
class Practice:
    """One practice: a plain sentence, its kind, and what it crosswalks to (empty
    only with a ``crosswalk_reason``)."""

    key: str
    display_name: str
    plain_summary: str
    kind: PracticeKind
    crosswalk: tuple[str, ...] = ()
    crosswalk_reason: str = ""


@dataclass(frozen=True)
class MethodProfile:
    """One method's identity, source, and the practices that make it up."""

    key: str
    display_name: str
    source: str
    source_version: str
    plain_summary: str
    practices: tuple[Practice, ...]


_SCRUM_PRACTICES: tuple[Practice, ...] = (
    # Accountabilities
    Practice(
        "product_owner",
        "Product Owner",
        "One person decides what to build next and keeps the backlog ordered.",
        PracticeKind.ROLE,
        ("5.3",),
    ),
    Practice(
        "scrum_master",
        "Scrum Master",
        "One person coaches the team and removes obstacles to its work.",
        PracticeKind.ROLE,
        ("9.5",),
    ),
    Practice(
        "developers",
        "Developers",
        "The people who build the product and decide together how the work gets done.",
        PracticeKind.ROLE,
        ("9.4",),
    ),
    # Events
    Practice(
        "sprint",
        "Sprint",
        "A short, fixed cycle in which the team builds a usable slice of the product.",
        PracticeKind.EVENT,
        ("6.5", "rolling_wave_planning"),
    ),
    Practice(
        "sprint_planning",
        "Sprint Planning",
        "At the start of each cycle, the team agrees what it will build and roughly how.",
        PracticeKind.EVENT,
        ("6.5", "agile_release_planning"),
    ),
    Practice(
        "daily_scrum",
        "Daily Scrum",
        "A short daily check-in where the team adjusts its plan for the next day's work.",
        PracticeKind.EVENT,
        ("meetings",),
    ),
    Practice(
        "sprint_review",
        "Sprint Review",
        "At the end of each cycle, the team shows finished work and gathers feedback.",
        PracticeKind.EVENT,
        ("10.2", "meetings"),
    ),
    Practice(
        "sprint_retrospective",
        "Sprint Retrospective",
        "After each cycle, the team looks back at how it worked and picks one thing to improve.",
        PracticeKind.EVENT,
        ("8.2", "meetings"),
    ),
    # Artifacts and their commitments
    Practice(
        "product_backlog",
        "Product Backlog",
        "The single ordered list of everything that might still be needed in the product.",
        PracticeKind.ARTIFACT,
        ("5.4", "decomposition"),
    ),
    Practice(
        "product_goal",
        "Product Goal",
        "The backlog's long-term objective, describing the future state the product is aiming for.",
        PracticeKind.POLICY,
        ("4.1",),
    ),
    Practice(
        "sprint_backlog",
        "Sprint Backlog",
        "The slice of work the team picked for this cycle, plus its plan to finish it.",
        PracticeKind.ARTIFACT,
        ("6.2",),
    ),
    Practice(
        "sprint_goal",
        "Sprint Goal",
        "The single purpose the cycle's chosen work is meant to achieve together.",
        PracticeKind.POLICY,
        ("6.5",),
    ),
    Practice(
        "increment",
        "Increment",
        "The working piece of product a cycle adds on top of everything built before it.",
        PracticeKind.ARTIFACT,
        ("4.3",),
    ),
    Practice(
        "definition_of_done",
        "Definition of Done",
        "The shared rule the team uses to agree when a piece of work is truly finished.",
        PracticeKind.POLICY,
        ("8.1",),
    ),
    # Empowerment / self-management
    Practice(
        "self_management",
        "Self-Management",
        "The team decides among itself who does each piece of work and how.",
        PracticeKind.POLICY,
        ("9.4",),
    ),
    Practice(
        "scrum_values",
        "Scrum Values",
        "Five shared values — commitment, focus, openness, respect and courage — guide the team.",
        PracticeKind.POLICY,
        ("ground_rules",),
    ),
)

_KANBAN_PRACTICES: tuple[Practice, ...] = (
    # General practices
    Practice(
        "visualize_workflow",
        "Visualize the Workflow",
        "A board that shows every piece of work and which stage it is in.",
        PracticeKind.POLICY,
        ("data_representation",),
    ),
    Practice(
        "limit_work_in_progress",
        "Limit Work in Progress",
        "A hard cap on how many items each stage of work may hold at once.",
        PracticeKind.POLICY,
        ("resource_optimization",),
    ),
    Practice(
        "manage_flow",
        "Manage Flow",
        "Watching how smoothly items move through the stages to catch delays early.",
        PracticeKind.POLICY,
        ("6.6",),
    ),
    Practice(
        "make_policies_explicit",
        "Make Policies Explicit",
        "Writing down the rules for moving work forward so everyone applies them the same way.",
        PracticeKind.POLICY,
        ("8.1",),
    ),
    Practice(
        "implement_feedback_loops",
        "Implement Feedback Loops",
        "Holding the regular reviews below so the process itself keeps improving.",
        PracticeKind.POLICY,
        ("meetings",),
    ),
    Practice(
        "improve_collaboratively",
        "Improve Collaboratively",
        "Changing the process one small, agreed step at a time, based on the evidence.",
        PracticeKind.POLICY,
        ("8.2",),
    ),
    # Change-management principles
    Practice(
        "start_with_what_you_do_now",
        "Start With What You Do Now",
        "Begin with the way work happens today instead of redesigning it first.",
        PracticeKind.POLICY,
        (),
        "PMBOK-6 assumes a plan precedes execution; it carries no principle of starting "
        "from the current, unchanged process.",
    ),
    Practice(
        "pursue_incremental_change",
        "Pursue Incremental Change",
        "Agree to make small, gradual improvements rather than one big overhaul.",
        PracticeKind.POLICY,
        ("8.2",),
    ),
    Practice(
        "encourage_leadership_at_every_level",
        "Encourage Leadership at Every Level",
        "Support anyone, not only managers, in acting to improve how work gets done.",
        PracticeKind.POLICY,
        (),
        "PMBOK-6 assigns improvement authority to named roles (sponsor, manager); it names "
        "no principle of leadership from any level.",
    ),
    # Service-delivery principles
    Practice(
        "focus_on_customer_needs",
        "Focus on Customer Needs",
        "Understand and focus on what the customer actually expects.",
        PracticeKind.POLICY,
        ("5.2",),
    ),
    Practice(
        "manage_the_work_not_the_people",
        "Manage the Work, Not the People",
        "Manage the work itself and let people decide how to organize around it.",
        PracticeKind.POLICY,
        ("9.4",),
    ),
    Practice(
        "evolve_policies_to_improve_outcomes",
        "Evolve Policies to Improve Outcomes",
        "Regularly adjust the rules for how work moves to get better results.",
        PracticeKind.POLICY,
        ("8.2",),
    ),
    # Standard flow metrics
    Practice(
        "work_in_progress",
        "Work in Progress",
        "Counting how many items are actively being worked on right now.",
        PracticeKind.METRIC,
        ("6.6",),
    ),
    Practice(
        "lead_time",
        "Lead Time",
        "How long an item takes from being requested to being delivered.",
        PracticeKind.METRIC,
        ("6.6",),
    ),
    Practice(
        "cycle_time",
        "Cycle Time",
        "How long an item takes once work on it actually starts.",
        PracticeKind.METRIC,
        ("6.6",),
    ),
    Practice(
        "throughput",
        "Throughput",
        "How many items finish in a given period of time.",
        PracticeKind.METRIC,
        ("6.6",),
    ),
    # Cadences
    Practice(
        "kanban_meeting",
        "Kanban Meeting",
        "A short daily meeting where the team looks at the board and plans its next step.",
        PracticeKind.EVENT,
        ("meetings",),
    ),
    Practice(
        "replenishment_meeting",
        "Replenishment Meeting",
        "A regular meeting where new work is chosen and pulled onto the board.",
        PracticeKind.EVENT,
        ("meetings",),
    ),
    Practice(
        "delivery_planning_meeting",
        "Delivery Planning Meeting",
        "A regular meeting where the team plans the next delivery of finished work.",
        PracticeKind.EVENT,
        ("meetings",),
    ),
    Practice(
        "service_delivery_review",
        "Service Delivery Review",
        "A regular review of how well the service is meeting its delivery targets.",
        PracticeKind.EVENT,
        ("8.3",),
    ),
    Practice(
        "operations_review",
        "Operations Review",
        "A regular review across teams of how the whole operation is performing.",
        PracticeKind.EVENT,
        ("4.5",),
    ),
    Practice(
        "risk_review",
        "Risk Review",
        "A regular review of the risks facing the work and how they are being handled.",
        PracticeKind.EVENT,
        ("11.7",),
    ),
    Practice(
        "strategy_review",
        "Strategy Review",
        "A periodic review of whether the work still serves the organization's direction.",
        PracticeKind.EVENT,
        ("4.1",),
    ),
    # Artifacts
    Practice(
        "kanban_board",
        "Kanban Board",
        "A shared board with a column for each stage of the workflow.",
        PracticeKind.ARTIFACT,
        ("data_representation",),
    ),
    Practice(
        "card",
        "Card",
        "One card for one piece of work, moved across the board as its state changes.",
        PracticeKind.ARTIFACT,
        ("5.4",),
    ),
)

METHODS: dict[str, MethodProfile] = {
    "scrum": MethodProfile(
        "scrum",
        "Scrum",
        "scrum_guide",
        "The Scrum Guide, November 2020 edition (Schwaber & Sutherland)",
        "A short, repeating cycle where a small team builds a piece of the product and "
        "checks in often.",
        _SCRUM_PRACTICES,
    ),
    "kanban": MethodProfile(
        "kanban",
        "Kanban",
        "essential_kanban_condensed",
        "Essential Kanban Condensed, 2016 edition (Anderson & Carmichael, Lean Kanban University)",
        "A way of managing ongoing work by making it visible, capping how much runs at "
        "once, and improving steadily.",
        _KANBAN_PRACTICES,
    ),
}
