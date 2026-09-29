"""Stakeholder engagement and communications — pure functions over plain value
objects. No I/O, no ORM, no wall clock: the caller (``web.assist_stakeholders``)
adapts stored ``Stakeholder`` rows into :class:`StakeholderRow` below, and every
answer here is derived from that value alone plus, for the what-if, a caller-supplied
desired engagement level. Nothing here imports ``driftless.models``, ``driftless.db``
or another ``driftless.calc`` module.

Three calculators over the one stored row (``models.records.Stakeholder``: name,
interest, influence, comms_cadence — no second table this PR adds):

- :func:`power_interest_grid` sorts stakeholders into the four classic quadrants.
- :func:`engagement_gap` compares a current reading against a desired one on the
  five-level engagement vocabulary and names the action the gap calls for.
- :func:`channel_choice` picks push, pull or interactive for one communication.
- :func:`communications_matrix` applies ``channel_choice`` per stakeholder to build
  the who/what/how-often/how rows the Manage Communications process asks for.

The store carries no "current engagement level" field — that would be a second
table this PR deliberately does not add — so :func:`inferred_current_engagement`
is an explicit, documented proxy from the one signal already stored (interest),
never a wall-clock or a guess: the same interest always yields the same reading.
"""

from __future__ import annotations

from dataclasses import dataclass

#: PMBOK's five engagement levels, least to most engaged.
ENGAGEMENT_LEVELS = ("unaware", "resistant", "neutral", "supportive", "leading")

#: Power/interest grid quadrant labels, in PMBOK's own words.
QUADRANTS = ("manage_closely", "keep_satisfied", "keep_informed", "monitor")

#: The three levels ``models.records.STAKEHOLDER_LEVELS`` and the channel-choice axes
#: below share — restated here rather than imported, since a calc module takes no
#: dependency on the ORM layer (see module docstring).
LEVELS = ("low", "medium", "high")
AUDIENCE_SIZES = ("small", "medium", "large")
CHANNEL_METHODS = ("push", "pull", "interactive")

#: Levels counted as the "high" half of an axis: splitting low from {medium, high}
#: keeps every stakeholder in exactly one bucket per axis on the three-level
#: vocabulary the store already carries, with no fourth boundary to invent.
_HIGH = frozenset({"medium", "high"})

#: Interest read straight onto the five-level engagement vocabulary. An explicit,
#: documented proxy — the store has no engagement-level field of its own (see
#: module docstring) — never a computed truth: "we have never asked this
#: stakeholder", "we have asked and they are lukewarm", "we have asked and they
#: are keen" is the honest ceiling interest alone can support.
_CURRENT_ENGAGEMENT_BY_INTEREST = {
    "low": "unaware",
    "medium": "neutral",
    "high": "supportive",
}


@dataclass(frozen=True)
class StakeholderRow:
    """One stakeholder, as the calculators need it — adapted from the stored row."""

    name: str
    interest: str
    influence: str
    comms_cadence: str


def power_interest_grid(stakeholders: list[StakeholderRow]) -> dict[str, tuple[str, ...]]:
    """Sort ``stakeholders`` into the four power/interest quadrants, by name.

    The rule, in plain words: influence is a stakeholder's POWER. A stakeholder whose
    influence is "medium" or "high" sits on the powerful half of the grid, and one
    whose interest is "medium" or "high" sits on the interested half. High power and
    high interest is managed closely; high power and low interest is kept satisfied
    (the disengaged powerful player); low power and high interest is kept informed;
    low power and low interest is only monitored.
    """
    quadrants: dict[str, list[str]] = {quadrant: [] for quadrant in QUADRANTS}
    for stakeholder in stakeholders:
        high_power = stakeholder.influence in _HIGH
        high_interest = stakeholder.interest in _HIGH
        if high_power and high_interest:
            quadrant = "manage_closely"
        elif high_power:
            quadrant = "keep_satisfied"
        elif high_interest:
            quadrant = "keep_informed"
        else:
            quadrant = "monitor"
        quadrants[quadrant].append(stakeholder.name)
    return {quadrant: tuple(names) for quadrant, names in quadrants.items()}


def inferred_current_engagement(interest: str) -> str:
    """This stakeholder's current engagement level, as a proxy read off ``interest``
    alone. See the module docstring for why this is a documented approximation
    rather than a stored fact."""
    if interest not in _CURRENT_ENGAGEMENT_BY_INTEREST:
        raise ValueError(f"interest must be one of {LEVELS}, got {interest!r}")
    return _CURRENT_ENGAGEMENT_BY_INTEREST[interest]


@dataclass(frozen=True)
class EngagementGap:
    """One stakeholder's gap between a current and a desired engagement level."""

    current: str
    desired: str
    direction: str  # "on_target" | "behind" | "ahead"
    steps: int
    action: str


def engagement_gap(current: str, desired: str) -> EngagementGap:
    """The gap between ``current`` and ``desired`` on ``ENGAGEMENT_LEVELS``, and the
    one-sentence action it calls for. ``steps`` is the distance between them,
    always non-negative; ``direction`` says which way the gap runs."""
    for value, label in ((current, "current"), (desired, "desired")):
        if value not in ENGAGEMENT_LEVELS:
            raise ValueError(f"{label} must be one of {ENGAGEMENT_LEVELS}, got {value!r}")
    delta = ENGAGEMENT_LEVELS.index(desired) - ENGAGEMENT_LEVELS.index(current)
    if delta == 0:
        return EngagementGap(current, desired, "on_target", 0, "Already at the desired level.")
    if delta > 0:
        step_word = "level" if delta == 1 else "levels"
        action = (
            f"Move {current} stakeholders to {desired}: raise touchpoints and tailor the "
            f"message to close the {delta} {step_word} between where they are and where "
            "this project needs them."
        )
        return EngagementGap(current, desired, "behind", delta, action)
    action = (
        f"Already past {desired} at {current}: sustain the relationship rather than pulling "
        "back the engagement that got them there."
    )
    return EngagementGap(current, desired, "ahead", -delta, action)


@dataclass(frozen=True)
class ChannelChoice:
    """A push/pull/interactive recommendation, with the reason behind it."""

    method: str
    reason: str


def channel_choice(audience_size: str, urgency: str, sensitivity: str) -> ChannelChoice:
    """Pick push, pull or interactive for one communication.

    High urgency or high sensitivity needs interactive: a real-time exchange to
    confirm the message landed and was understood, never a one-way send. Absent
    that, a large audience is served better by a self-service pull channel than by
    pushing the same message at everyone individually. Everything else is a
    straightforward push."""
    for value, label in (
        (audience_size, "audience_size"),
        (urgency, "urgency"),
        (sensitivity, "sensitivity"),
    ):
        if value not in LEVELS and (label != "audience_size" or value not in AUDIENCE_SIZES):
            vocab = AUDIENCE_SIZES if label == "audience_size" else LEVELS
            raise ValueError(f"{label} must be one of {vocab}, got {value!r}")
    if urgency == "high" or sensitivity == "high":
        return ChannelChoice(
            "interactive",
            "High urgency or sensitivity needs a real-time exchange to confirm the message "
            "landed and was understood, not a one-way send.",
        )
    if audience_size == "large":
        return ChannelChoice(
            "pull",
            "A large, low-urgency, low-sensitivity audience is served better by a "
            "self-service channel than by pushing the same message at everyone individually.",
        )
    return ChannelChoice(
        "push",
        "Small-to-medium audience, low urgency and low sensitivity: send it directly.",
    )


@dataclass(frozen=True)
class CommunicationRow:
    """One row of the communications matrix: who, what, how often, and how."""

    who: str
    what: str
    how_often: str
    channel: str
    reason: str


def communications_matrix(stakeholders: list[StakeholderRow]) -> tuple[CommunicationRow, ...]:
    """Who to tell, what, how often and over which channel — one row per
    stakeholder. ``comms_cadence`` names how often directly; influence stands in
    for urgency (a miss with a powerful stakeholder matters more) and interest for
    sensitivity (the content matters more to a stakeholder already engaged) — the
    same judgment call Manage Communications makes by hand, fed to
    :func:`channel_choice` instead of a fourth field nothing stores."""
    rows = []
    for stakeholder in stakeholders:
        choice = channel_choice(
            audience_size="small", urgency=stakeholder.influence, sensitivity=stakeholder.interest
        )
        what = (
            "Project status and decisions that affect them"
            if stakeholder.interest in _HIGH
            else "A brief status headline"
        )
        rows.append(
            CommunicationRow(
                stakeholder.name, what, stakeholder.comms_cadence, choice.method, choice.reason
            )
        )
    return tuple(rows)
