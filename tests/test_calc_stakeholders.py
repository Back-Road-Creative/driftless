"""Tests for the stakeholder engagement and communications calculators."""

from __future__ import annotations

import pytest

from driftless.calc.stakeholders import (
    ENGAGEMENT_LEVELS,
    ChannelChoice,
    StakeholderRow,
    channel_choice,
    communications_matrix,
    engagement_gap,
    inferred_current_engagement,
    power_interest_grid,
)


def test_power_interest_grid_sorts_all_four_quadrants() -> None:
    stakeholders = [
        StakeholderRow("Sponsor", interest="high", influence="high", comms_cadence="weekly"),
        StakeholderRow("Regulator", interest="low", influence="high", comms_cadence="monthly"),
        StakeholderRow("End user", interest="high", influence="low", comms_cadence="monthly"),
        StakeholderRow("Neighbour", interest="low", influence="low", comms_cadence="on_request"),
    ]
    grid = power_interest_grid(stakeholders)
    assert grid["manage_closely"] == ("Sponsor",)
    assert grid["keep_satisfied"] == ("Regulator",)
    assert grid["keep_informed"] == ("End user",)
    assert grid["monitor"] == ("Neighbour",)


def test_power_interest_grid_treats_medium_as_the_high_half() -> None:
    stakeholder = StakeholderRow(
        "Ops lead", interest="medium", influence="medium", comms_cadence="weekly"
    )
    grid = power_interest_grid([stakeholder])
    assert grid["manage_closely"] == ("Ops lead",)


def test_inferred_current_engagement_reads_off_interest_only() -> None:
    assert inferred_current_engagement("low") == "unaware"
    assert inferred_current_engagement("medium") == "neutral"
    assert inferred_current_engagement("high") == "supportive"


def test_inferred_current_engagement_refuses_an_unknown_level() -> None:
    with pytest.raises(ValueError, match="interest"):
        inferred_current_engagement("extreme")


def test_engagement_gap_on_target_names_no_action() -> None:
    gap = engagement_gap("supportive", "supportive")
    assert gap.direction == "on_target"
    assert gap.steps == 0


def test_engagement_gap_behind_counts_the_steps_and_says_move() -> None:
    gap = engagement_gap("unaware", "supportive")
    assert gap.direction == "behind"
    assert gap.steps == 3
    assert "unaware" in gap.action and "supportive" in gap.action


def test_engagement_gap_ahead_says_sustain_not_pull_back() -> None:
    gap = engagement_gap("leading", "neutral")
    assert gap.direction == "ahead"
    assert gap.steps == 2
    assert "sustain" in gap.action.lower()


def test_engagement_gap_refuses_a_level_outside_the_vocabulary() -> None:
    with pytest.raises(ValueError, match="desired"):
        engagement_gap("neutral", "excited")


def test_every_engagement_level_is_reachable_from_every_other() -> None:
    for current in ENGAGEMENT_LEVELS:
        for desired in ENGAGEMENT_LEVELS:
            gap = engagement_gap(current, desired)
            assert gap.steps == abs(
                ENGAGEMENT_LEVELS.index(desired) - ENGAGEMENT_LEVELS.index(current)
            )


def test_channel_choice_urgent_or_sensitive_is_interactive() -> None:
    assert channel_choice("small", "high", "low").method == "interactive"
    assert channel_choice("small", "low", "high").method == "interactive"


def test_channel_choice_large_low_stakes_audience_is_pull() -> None:
    choice = channel_choice("large", "low", "low")
    assert choice == ChannelChoice("pull", choice.reason)


def test_channel_choice_small_low_stakes_is_push() -> None:
    assert channel_choice("small", "low", "low").method == "push"


def test_channel_choice_refuses_an_unknown_audience_size() -> None:
    with pytest.raises(ValueError, match="audience_size"):
        channel_choice("huge", "low", "low")


def test_communications_matrix_derives_a_row_per_stakeholder() -> None:
    stakeholders = [
        StakeholderRow("Sponsor", interest="high", influence="high", comms_cadence="weekly"),
        StakeholderRow("Neighbour", interest="low", influence="low", comms_cadence="on_request"),
    ]
    rows = communications_matrix(stakeholders)
    assert [row.who for row in rows] == ["Sponsor", "Neighbour"]
    sponsor, neighbour = rows
    assert sponsor.how_often == "weekly"
    assert sponsor.channel == "interactive"  # high influence -> high urgency
    assert neighbour.channel == "push"


def test_communications_matrix_is_empty_for_no_stakeholders() -> None:
    assert communications_matrix([]) == ()
