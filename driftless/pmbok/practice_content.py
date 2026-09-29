"""Working material for individual practices: ``CONTENT``.

A practice's ``plain_summary`` says what it is; its crosswalk says what it
resembles. Neither says how the practice is actually carried out day to day,
or what it looks like when a team is going through the motions without it
actually working. ``CONTENT`` is the small, hand-picked set of practices
where that extra layer is worth adding, keyed by the practice's own ``key``
(:data:`driftless.pmbok.methods.Practice.key`).

Not every practice gets an entry. A role like Product Owner or an artifact
like Card is adequately described by its one-sentence summary; padding it
with a manufactured "how it's run" section would be filler, not information.
Entries here are reserved for events, cadences and policies where a reader
can plausibly do the practice well or badly, and where naming the difference
is useful. ``tests/test_web_methods.py`` walks every entry onto its page.

This copy is newly authored for Driftless, describing Scrum/Kanban working
practice in general terms — it is not a quote or close paraphrase of either
guide, and it makes no claim about how any particular project run through
this product actually plans a sprint, holds a meeting or manages its board.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PracticeDetail:
    """How a practice is run well, and what it looks like when it isn't."""

    running_it: tuple[str, ...]
    going_wrong: tuple[str, ...]


CONTENT: dict[str, PracticeDetail] = {
    "sprint_planning": PracticeDetail(
        (
            "The top of the Product Backlog is already refined enough to plan against "
            "before the meeting starts, not discovered during it.",
            "The Developers, not the Product Owner or Scrum Master, decide how much work "
            "they can take on.",
        ),
        (
            "The amount of work chosen is set by hope or by pressure from outside the "
            "team rather than by what the team has actually finished in past Sprints.",
            "The meeting turns into re-arguing priorities the Product Owner already "
            "settled by ordering the backlog.",
        ),
    ),
    "daily_scrum": PracticeDetail(
        (
            "It stays inside its timebox and focuses on adjusting the plan for the next "
            "day's work, not reporting status.",
            "Only the Developers need to run it; anyone else present listens.",
        ),
        (
            "It becomes a status report delivered to the Scrum Master or a manager "
            "instead of the Developers planning among themselves.",
            "It regularly runs long because it drifts into solving problems that belong "
            "in a smaller side conversation.",
        ),
    ),
    "sprint_review": PracticeDetail(
        (
            "What gets shown is working product, not a slide deck describing it.",
            "Stakeholders are actually present and their feedback changes what goes on "
            "the backlog next.",
        ),
        (
            "The review becomes a rubber stamp because nothing shown is genuinely usable yet.",
            "Feedback is collected but never makes it back onto the Product Backlog.",
        ),
    ),
    "sprint_retrospective": PracticeDetail(
        (
            "The team leaves with one concrete change it will actually make, not a "
            "long list of observations.",
            "The chosen change is visibly carried into the next Sprint's plan.",
        ),
        (
            "The same complaints resurface every retrospective because nothing chosen "
            "in a prior one was ever followed through.",
            "It turns into blame directed at individuals rather than at the way the "
            "work is organized.",
        ),
    ),
    "definition_of_done": PracticeDetail(
        (
            "It is written down somewhere the whole team can see, and it applies the "
            "same way to every item.",
            "It only grows stricter over time as the team learns what completeness "
            "actually requires.",
        ),
        (
            "It gets quietly loosened for one item near a deadline so the burndown "
            "looks better than the work really is.",
            "Different people on the team believe different things count as done.",
        ),
    ),
    "visualize_workflow": PracticeDetail(
        (
            "The board's columns match the path work actually follows, not an idealized "
            "version of it.",
            "Every piece of work in progress has a card on the board, with nothing "
            "moving through a side channel the board can't see.",
        ),
        (
            "Hidden work never gets a card, so the board stops reflecting what people "
            "are actually doing.",
            "The board is updated in a weekly meeting instead of as work actually "
            "moves, so it is always stale.",
        ),
    ),
    "limit_work_in_progress": PracticeDetail(
        (
            "Each column's limit is a hard cap that holds even when it would be "
            "convenient to start one more thing.",
            "When a column is at its limit, the team helps clear it rather than "
            "starting new work elsewhere.",
        ),
        (
            "The limit gets raised whenever it becomes inconvenient, until it no "
            "longer limits anything.",
            "Limits are set once and never revisited even as the team's capacity changes.",
        ),
    ),
    "manage_flow": PracticeDetail(
        (
            "Cycle time and where items stall are watched as a trend over many items, "
            "not judged from one anecdote.",
            "A stall gets attention while the item is still on the board, not after it "
            "finally ships.",
        ),
        (
            "Flow metrics are collected and displayed but nobody acts on what they show.",
            "Attention only goes to the newest or loudest item, not the one that has "
            "actually stalled longest.",
        ),
    ),
    "make_policies_explicit": PracticeDetail(
        (
            "The rules for moving work forward are written down somewhere everyone can "
            "reach, not kept in one person's head.",
            "A dispute about whether an item can move gets settled by pointing at the "
            "written policy.",
        ),
        (
            "The real rule for moving work only exists as one senior person's judgment, "
            "so decisions vary by who is asked.",
            "Policies are written once and never checked against how work is actually moving.",
        ),
    ),
    "kanban_meeting": PracticeDetail(
        (
            "It stays short, stays focused on the board, and ends with clear next "
            "steps rather than open discussion.",
            "It happens at the same time and place every day so it becomes a habit, "
            "not an event to schedule around.",
        ),
        (
            "It turns into a long status meeting where each person narrates their day "
            "instead of the team looking at the board together.",
            "It gets skipped whenever the team feels busy, which is exactly when it "
            "would help most.",
        ),
    ),
    "replenishment_meeting": PracticeDetail(
        (
            "It runs on its own cadence, separate from the daily meeting, and only "
            "pulls in work that is genuinely ready.",
            "What gets pulled in is limited to what the board's own capacity can "
            "actually absorb next.",
        ),
        (
            "It gets skipped, so new work is added to the board ad hoc whenever "
            "someone thinks of it.",
            "Items are pulled in before they are ready, so they stall on the board "
            "waiting for information that should have been settled first.",
        ),
    ),
}
