"""Decisions and meetings — pure functions and value objects over plain option,
ballot and record data. No I/O, no ORM, no wall clock: the web layer builds the
inputs from a form or GET params and this module only ever computes from them.

``vote`` and ``multicriteria_score`` are the two decision-making techniques with
a real computation behind them; ``autocratic_record``, ``meeting_record`` and
``facilitation_plan`` are shapes and a fixed agenda a person fills in, not a
formula, but living here keeps every decisions.py caller pure the same way.

``multicriteria_score`` is named generically rather than ``bid_score`` on
purpose: Procurement's proposal-evaluation and source-selection techniques are
the same weighted-scoring problem this solves, and a later procurement
calculator should import this function rather than reimplement it. No such
module exists yet, so there is nothing to import from here today.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum


class VotingRule(str, Enum):
    """How a tally becomes a decision."""

    UNANIMITY = "unanimity"
    MAJORITY = "majority"
    PLURALITY = "plurality"


@dataclass(frozen=True)
class VoteResult:
    """One tally, and whether ``rule`` was actually met — in plain words."""

    tally: dict[str, int]
    leader: str
    rule: VotingRule
    rule_met: bool
    explanation: str


def vote(options: Sequence[str], ballots: Sequence[str], rule: VotingRule) -> VoteResult:
    """Tally ``ballots`` over ``options`` and say whether ``rule`` was met.

    Every ballot must name a listed option — a stray write-in is refused before
    it can silently vanish from the count. ``unanimity`` requires every ballot
    for the leader; ``majority`` requires more than half; ``plurality`` requires
    only that the leader have no tie for first.
    """
    if not options:
        raise ValueError("vote requires at least one option")
    stray = [b for b in ballots if b not in options]
    if stray:
        raise ValueError(f"ballot(s) name an option not on the list: {stray}")
    tally = {option: 0 for option in options}
    for ballot in ballots:
        tally[ballot] += 1
    total = len(ballots)
    if total == 0:
        return VoteResult(tally, options[0], rule, False, "No ballots were cast.")
    ranked = sorted(options, key=lambda o: (-tally[o], options.index(o)))
    leader = ranked[0]
    leader_votes = tally[leader]
    if rule is VotingRule.UNANIMITY:
        met = leader_votes == total
        explanation = (
            f"{leader} won every one of the {total} ballots cast."
            if met
            else f"{leader} led with {leader_votes} of {total} ballots, short of unanimity."
        )
    elif rule is VotingRule.MAJORITY:
        met = leader_votes > total / 2
        explanation = (
            f"{leader} won {leader_votes} of {total} ballots, more than half."
            if met
            else f"{leader} led with {leader_votes} of {total} ballots, short of a majority."
        )
    else:  # PLURALITY
        tied = [o for o in ranked if tally[o] == leader_votes]
        met = len(tied) == 1
        explanation = (
            f"{leader} led with {leader_votes} of {total} ballots, more than any other option."
            if met
            else f"{', '.join(tied)} tied at {leader_votes} ballots each; plurality names no "
            "single winner."
        )
    return VoteResult(tally, leader, rule, met, explanation)


@dataclass(frozen=True)
class ScoreResult:
    """A weighted-criteria ranking, best first, and which criterion decides it."""

    ranking: tuple[tuple[str, float], ...]
    winner: str
    deciding_criterion: str
    sensitivity_note: str


def multicriteria_score(
    options: Sequence[str],
    criteria_weights: Mapping[str, float],
    scores: Mapping[str, Mapping[str, float]],
) -> ScoreResult:
    """Rank ``options`` by criterion score x weight, summed per option.

    ``scores`` is ``{option: {criterion: raw_score}}``; a missing option or
    criterion reads as 0.0 rather than raising, so an incomplete GET what-if
    still ranks something. ``deciding_criterion`` is the criterion whose
    weighted gap between first and second place is largest — the one where a
    different score would most likely flip the outcome.
    """
    if not options:
        raise ValueError("multicriteria_score requires at least one option")
    if not criteria_weights:
        raise ValueError("multicriteria_score requires at least one criterion")
    totals = {
        option: sum(
            scores.get(option, {}).get(criterion, 0.0) * weight
            for criterion, weight in criteria_weights.items()
        )
        for option in options
    }
    ranked = sorted(options, key=lambda o: (-totals[o], options.index(o)))
    winner = ranked[0]
    if len(ranked) == 1:
        deciding = next(iter(criteria_weights))
        note = "Only one option was scored, so no comparison decides the outcome."
    else:
        runner_up = ranked[1]
        gaps = {
            criterion: weight
            * (
                scores.get(winner, {}).get(criterion, 0.0)
                - scores.get(runner_up, {}).get(criterion, 0.0)
            )
            for criterion, weight in criteria_weights.items()
        }
        deciding = max(gaps, key=lambda c: gaps[c])
        note = (
            f"{winner} pulled ahead of {runner_up} most on {deciding}; a different score "
            "there is the most likely thing to change the outcome."
        )
    ranking = tuple(sorted(((o, totals[o]) for o in options), key=lambda kv: (-kv[1], kv[0])))
    return ScoreResult(ranking, winner, deciding, note)


@dataclass(frozen=True)
class AutocraticRecord:
    """One person's decision for the group, and why — nothing computed."""

    decider: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.decider.strip():
            raise ValueError("autocratic_record requires a decider")
        if not self.rationale.strip():
            raise ValueError("autocratic_record requires a rationale")


def autocratic_record(decider: str, rationale: str) -> AutocraticRecord:
    """Wrap ``decider`` and ``rationale`` as the record a meeting evidence log
    can store — refuses either half being blank rather than storing a decision
    nobody can trace."""
    return AutocraticRecord(decider=decider, rationale=rationale)


@dataclass(frozen=True)
class MeetingAction:
    """One action a meeting produced: what, who owns it, and by when (if set)."""

    description: str
    owner: str = ""
    due: date | None = None


@dataclass(frozen=True)
class MeetingRecord:
    """A meeting's shape: purpose, who attended, what was decided, what follows."""

    purpose: str
    attendees: tuple[str, ...]
    decisions: tuple[str, ...]
    actions: tuple[MeetingAction, ...]

    def __post_init__(self) -> None:
        if not self.purpose.strip():
            raise ValueError("meeting_record requires a purpose")
        if not self.attendees:
            raise ValueError("meeting_record requires at least one attendee")


def meeting_record(
    purpose: str,
    attendees: Sequence[str],
    decisions: Sequence[str],
    actions: Sequence[MeetingAction],
) -> MeetingRecord:
    """Build a :class:`MeetingRecord` from plain sequences the web layer parsed
    out of a form."""
    return MeetingRecord(purpose, tuple(attendees), tuple(decisions), tuple(actions))


class FacilitationTechnique(str, Enum):
    """Which facilitation format ``facilitation_plan`` is agendaing."""

    BRAINSTORMING = "brainstorming"
    NOMINAL_GROUP = "nominal_group"
    FOCUS_GROUP = "focus_group"
    INTERVIEWS = "interviews"
    WORKSHOP = "workshop"


@dataclass(frozen=True)
class FacilitationPlan:
    """A purpose, a participant list, and the fixed agenda for one technique."""

    purpose: str
    participants: tuple[str, ...]
    technique: FacilitationTechnique
    agenda: tuple[str, ...]


#: One fixed, plain-language agenda per technique — not computed, so the same
#: technique always reads back the same steps for any purpose and participant
#: list, the same way a worksheet's headings never depend on what is filled in.
_AGENDA: dict[FacilitationTechnique, tuple[str, ...]] = {
    FacilitationTechnique.BRAINSTORMING: (
        "State the purpose and the one question the group is generating ideas against.",
        "Generate ideas without judging them — quantity over quality at this stage.",
        "Group similar ideas together once nobody has more to add.",
        "Have the group narrow the grouped ideas to the ones worth acting on.",
    ),
    FacilitationTechnique.NOMINAL_GROUP: (
        "State the purpose and the one question the group is answering.",
        "Each participant writes their own ideas silently, with no discussion.",
        "Go around the group once each, recording every idea with no debate.",
        "Discuss each idea briefly for clarity, not to argue for or against it.",
        "Each participant ranks the ideas privately; the ranks are totalled to prioritise them.",
    ),
    FacilitationTechnique.FOCUS_GROUP: (
        "State the purpose and who was invited, and why.",
        "Ask open questions and let the group's own conversation surface the detail.",
        "Note what several participants raise unprompted, not only what is asked about.",
        "Summarise back to the group what was heard, and confirm it before closing.",
    ),
    FacilitationTechnique.INTERVIEWS: (
        "State the purpose and confirm how long the conversation will run.",
        "Ask open questions and let the interviewee's own words lead the detail.",
        "Confirm what was understood before moving to the next question.",
        "Write up the interview while it is still fresh, before the next one.",
    ),
    FacilitationTechnique.WORKSHOP: (
        "State the purpose and the decision or artifact the workshop must produce.",
        "Work through the agenda in blocks, with a named owner for each block.",
        "Capture decisions and open questions as the workshop goes, not from memory after.",
        "Close by confirming what was decided and who owns each follow-up action.",
    ),
}


def facilitation_plan(
    purpose: str, participants: Sequence[str], technique: FacilitationTechnique
) -> FacilitationPlan:
    """A plain-steps agenda for ``technique``, refusing an unnamed purpose or an
    empty participant list rather than planning a meeting nobody is coming to."""
    if not purpose.strip():
        raise ValueError("facilitation_plan requires a purpose")
    if not participants:
        raise ValueError("facilitation_plan requires at least one participant")
    return FacilitationPlan(
        purpose=purpose,
        participants=tuple(participants),
        technique=technique,
        agenda=_AGENDA[technique],
    )
