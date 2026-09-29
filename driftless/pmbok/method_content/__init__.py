"""Working material for the method-profile pages: ``CONTENT``.

A method's crosswalk table says what it resembles; it hands a reader nothing to
run. ``CONTENT`` is the small, closed set of authored templates that fills that
gap — a sprint-planning agenda and a Definition of Done checklist for Scrum, a
board-policy template for Kanban — keyed by :data:`driftless.pmbok.methods.METHODS`'s
own key.

Unlike ``technique_content`` or ``artifact_content``, this is not a growing,
concurrently-authored catalog: ``METHODS`` holds exactly two profiles (scope
decided 2026-08-22 — Scrum and Kanban only), so one module, not a
per-family-discovery package, is the whole of it. ``tests/test_web_methods.py``
walks every entry onto its page.

This copy is newly authored for Driftless, describing Scrum/Kanban working
practice in general terms — it is not a quote or close paraphrase of either
guide, and it makes no claim about how any particular project run through this
product actually plans a sprint or manages its board.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MethodContentBlock:
    """One piece of working material: a heading and the items under it."""

    heading: str
    items: tuple[str, ...]


CONTENT: dict[str, tuple[MethodContentBlock, ...]] = {
    "scrum": (
        MethodContentBlock(
            "Sprint Planning Agenda",
            (
                "Restate the Sprint Goal candidate and check it against the Product Goal.",
                "Walk the top of the Product Backlog and confirm each item is ready to pull.",
                "The Developers select the work they believe they can finish this Sprint.",
                "Break selected items into a plan of concrete tasks for the Sprint Backlog.",
                "Confirm the Definition of Done applies unchanged, or note any exceptions.",
                "Restate the finished Sprint Goal and the Sprint Backlog back to the room.",
            ),
        ),
        MethodContentBlock(
            "Definition of Done Checklist",
            (
                "Code (or equivalent work product) is complete and reviewed by someone else.",
                "Automated checks relevant to the change pass.",
                "The result is integrated with the rest of the product, not sitting apart.",
                "Any documentation the change requires has been updated.",
                "The Product Owner has seen it and agrees it meets the Sprint Goal's intent.",
            ),
        ),
    ),
    "kanban": (
        MethodContentBlock(
            "Board Policy Template",
            (
                "Name every column on the board and what "
                "'done' means to leave it for the next one.",
                "Set an explicit work-in-progress limit for each column that needs one.",
                "State the pull rule: a column pulls from upstream only when it has spare capacity.",
                "Write down what makes an item eligible to enter the board at all.",
                "Record how blocked work is marked and who is responsible for unblocking it.",
                "Set the cadence for reviewing and changing these policies.",
            ),
        ),
    ),
}
