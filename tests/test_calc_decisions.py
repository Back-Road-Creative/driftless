"""Tests for the pure decisions/meetings core: voting, weighted scoring,
autocratic records, meeting records and facilitation agendas.
"""

from __future__ import annotations

from datetime import date

import pytest

from driftless.calc.decisions import (
    AutocraticRecord,
    FacilitationTechnique,
    MeetingAction,
    VotingRule,
    autocratic_record,
    facilitation_plan,
    meeting_record,
    multicriteria_score,
    vote,
)

OPTIONS = ("red", "blue", "green")


def test_unanimity_is_met_only_when_every_ballot_agrees() -> None:
    result = vote(OPTIONS, ["red", "red", "red"], VotingRule.UNANIMITY)
    assert result.leader == "red"
    assert result.rule_met is True
    assert "every one" in result.explanation


def test_unanimity_is_refused_by_a_single_dissent() -> None:
    result = vote(OPTIONS, ["red", "red", "blue"], VotingRule.UNANIMITY)
    assert result.leader == "red"
    assert result.rule_met is False
    assert "short of unanimity" in result.explanation


def test_majority_needs_more_than_half() -> None:
    tie = vote(OPTIONS, ["red", "red", "blue", "blue"], VotingRule.MAJORITY)
    assert tie.rule_met is False
    win = vote(OPTIONS, ["red", "red", "red", "blue"], VotingRule.MAJORITY)
    assert win.leader == "red" and win.rule_met is True


def test_plurality_is_met_by_a_lead_with_no_tie() -> None:
    result = vote(OPTIONS, ["red", "red", "blue", "green"], VotingRule.PLURALITY)
    assert result.leader == "red"
    assert result.rule_met is True


def test_plurality_is_not_met_on_a_tie_for_first() -> None:
    result = vote(OPTIONS, ["red", "blue"], VotingRule.PLURALITY)
    assert result.rule_met is False
    assert "tied" in result.explanation


def test_a_ballot_naming_no_listed_option_is_refused() -> None:
    with pytest.raises(ValueError):
        vote(OPTIONS, ["purple"], VotingRule.PLURALITY)


def test_no_ballots_cast_reports_no_rule_met() -> None:
    result = vote(OPTIONS, [], VotingRule.MAJORITY)
    assert result.rule_met is False
    assert result.tally == {"red": 0, "blue": 0, "green": 0}


def test_multicriteria_score_ranks_by_weighted_total() -> None:
    weights = {"cost": 0.6, "quality": 0.4}
    scores = {
        "vendor-a": {"cost": 8.0, "quality": 5.0},
        "vendor-b": {"cost": 5.0, "quality": 9.0},
    }
    result = multicriteria_score(("vendor-a", "vendor-b"), weights, scores)
    # a: 8*.6 + 5*.4 = 6.8   b: 5*.6 + 9*.4 = 6.6
    assert result.winner == "vendor-a"
    assert result.ranking[0] == ("vendor-a", 6.8)
    assert result.ranking[1] == ("vendor-b", 6.6)


def test_multicriteria_deciding_criterion_is_the_largest_weighted_gap() -> None:
    weights = {"cost": 0.6, "quality": 0.4}
    scores = {
        "vendor-a": {"cost": 10.0, "quality": 5.0},
        "vendor-b": {"cost": 4.0, "quality": 6.0},
    }
    # cost gap: 0.6*(10-4)=3.6  quality gap: 0.4*(5-6)=-0.4 -> cost decides
    result = multicriteria_score(("vendor-a", "vendor-b"), weights, scores)
    assert result.deciding_criterion == "cost"


def test_multicriteria_score_requires_options_and_criteria() -> None:
    with pytest.raises(ValueError):
        multicriteria_score((), {"cost": 1.0}, {})
    with pytest.raises(ValueError):
        multicriteria_score(("a",), {}, {})


def test_autocratic_record_refuses_a_blank_decider_or_rationale() -> None:
    record = autocratic_record("PM", "The vendor deadline forced the call.")
    assert isinstance(record, AutocraticRecord)
    assert record.decider == "PM"
    with pytest.raises(ValueError):
        autocratic_record("", "why")
    with pytest.raises(ValueError):
        autocratic_record("PM", "  ")


def test_meeting_record_carries_attendees_decisions_and_actions() -> None:
    action = MeetingAction("Send the revised charter", owner="jp", due=date(2026, 4, 1))
    record = meeting_record("Kickoff", ["jp", "ada"], ["Scope confirmed"], [action])
    assert record.attendees == ("jp", "ada")
    assert record.actions[0].owner == "jp"
    assert record.actions[0].due == date(2026, 4, 1)


def test_meeting_record_refuses_no_purpose_or_no_attendees() -> None:
    with pytest.raises(ValueError):
        meeting_record("", ["jp"], [], [])
    with pytest.raises(ValueError):
        meeting_record("Kickoff", [], [], [])


def test_facilitation_plan_returns_a_fixed_agenda_for_the_technique() -> None:
    plan = facilitation_plan(
        "Prioritise the backlog", ["jp", "ada"], FacilitationTechnique.WORKSHOP
    )
    assert plan.technique is FacilitationTechnique.WORKSHOP
    assert plan.agenda[0].startswith("State the purpose")
    assert len(plan.agenda) >= 3


def test_facilitation_plan_covers_every_technique() -> None:
    for technique in FacilitationTechnique:
        plan = facilitation_plan("Purpose", ["someone"], technique)
        assert plan.agenda, technique


def test_facilitation_plan_refuses_no_purpose_or_no_participants() -> None:
    with pytest.raises(ValueError):
        facilitation_plan("", ["jp"], FacilitationTechnique.INTERVIEWS)
    with pytest.raises(ValueError):
        facilitation_plan("Purpose", [], FacilitationTechnique.INTERVIEWS)


def test_vote_refuses_an_empty_options_list() -> None:
    with pytest.raises(ValueError, match="at least one option"):
        vote((), ["red"], VotingRule.MAJORITY)


def test_multicriteria_score_with_a_single_option_names_no_deciding_comparison() -> None:
    result = multicriteria_score(("vendor-a",), {"cost": 1.0}, {"vendor-a": {"cost": 5.0}})
    assert result.winner == "vendor-a"
    assert result.deciding_criterion == "cost"
    assert (
        result.sensitivity_note
        == "Only one option was scored, so no comparison decides the outcome."
    )
