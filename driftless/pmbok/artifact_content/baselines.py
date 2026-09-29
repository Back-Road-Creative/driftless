"""Artifact explanations for the baselines family (artifacts.FAMILIES["baselines"]).

The approved, frozen versions of scope, schedule and cost that everything else
is measured against — a baseline only changes through a reviewed change, never
by quietly editing the plan.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "baselines"

CONTENT: dict[str, ArtifactContent] = {
    "scope_baseline": ArtifactContent(
        plain_summary="The approved, frozen version of exactly what the project will deliver.",
        why_it_matters=(
            "Without a frozen version, 'what we're building' keeps shifting and nobody can "
            "say for sure whether the team is on track."
        ),
        what_it_looks_like_here=(
            "The latest approved baseline for the project, with its line items; healthy only "
            "when it actually has lines to measure against."
        ),
    ),
    "schedule_baseline": ArtifactContent(
        plain_summary="The approved, frozen version of when each piece of work is planned to happen.",
        why_it_matters="It is the fixed line 'ahead of schedule' or 'behind schedule' is measured against.",
        what_it_looks_like_here=(
            "The same approved baseline as scope, read for its planned start and finish "
            "dates; healthy only when every date actually makes sense in order."
        ),
    ),
    "cost_baseline": ArtifactContent(
        plain_summary="The approved, frozen version of how much the project is planned to spend, and when.",
        why_it_matters="It is the fixed line actual spending gets compared against to spot trouble early.",
        what_it_looks_like_here="The project's budget lines, added up; healthy once the total is a real, positive amount.",
    ),
    "performance_measurement_baseline": ArtifactContent(
        plain_summary="The scope, schedule and cost baselines combined into one plan to measure real progress against.",
        why_it_matters=(
            "It is the single reference earned-value tracking needs — without all three "
            "pieces together, 'ahead' or 'behind' cannot honestly be answered."
        ),
        what_it_looks_like_here=(
            "Not stored separately: it is the same three approved baselines above, read "
            "together rather than kept as a fourth copy."
        ),
    ),
}
