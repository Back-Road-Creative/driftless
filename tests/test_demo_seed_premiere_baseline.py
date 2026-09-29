"""Pins the ``Premiere`` milestone's offset and slip-inertness.

``Premiere`` is baselined ``offset=-10`` with the default ``slip=0``, so its
``baseline_date`` equals its ``target_date`` -- it never trips
``assess.evaluators.schedule.milestone_slipped`` (only a ``missed`` status or
``target_date > baseline_date`` does that). A future "fix" that adds a
``slip=`` to make Premiere read as late would change the demo's visible
threat set; this test fails loudly if the offset or slip default drifts.
"""

from datetime import timedelta

from driftless.assess.evaluators.schedule import milestone_slipped
from driftless.demo.data import ANCHOR, demo_payload
from driftless.models import Milestone


def _premiere() -> dict[str, object]:
    projects = [
        p
        for b in demo_payload(ANCHOR)["businesses"]
        for pf in b["portfolios"]
        for p in pf["projects"]
    ]
    (rollout,) = [p for p in projects if p["name"] == "Season 4 Rollout"]
    (premiere,) = [m for m in rollout["milestones"] if m["name"] == "Premiere"]
    return premiere


def test_premiere_is_baselined_ten_days_before_anchor_with_zero_slip() -> None:
    premiere = _premiere()
    assert premiere["target_date"] == ANCHOR - timedelta(days=10)
    assert premiere["baseline_date"] == premiere["target_date"]


def test_premiere_offset_is_inert_for_the_schedule_slip_signal() -> None:
    """Confirms the -10 offset does not, by itself, make Premiere read as a
    live slip -- the demo's slip signal comes from ``Sizzle reel delivery``
    (``status="missed"``, ``slip=14``), not from Premiere's early placement."""
    premiere = _premiere()
    milestone = Milestone(
        name=premiere["name"],
        status=premiere["status"],
        target_date=premiere["target_date"],
        baseline_date=premiere["baseline_date"],
    )
    assert not milestone_slipped(milestone, as_of=ANCHOR)
