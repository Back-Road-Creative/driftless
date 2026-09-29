"""Plain-language content for the Schedule Management processes (6.1-6.6),
``KnowledgeArea.SCHEDULE``.

Schedule turns the broken-down work into a timeline: name the activities,
order them, estimate how long each takes, build the calendar, and then keep
it honest as the work actually happens.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "schedule"

CONTENT: dict[str, ProcessContent] = {
    "6.1": ProcessContent(
        plain_summary="Decide, up front, how you will build and control the schedule.",
        why_bother=(
            "Without an agreed approach, one planner's spreadsheet and another's project "
            "tool tell two different stories about when the work will finish."
        ),
        done_when="A schedule management approach is written down and the team is using it.",
        first_time_tip=(
            "Pick your scheduling tool and units before the first estimate is entered. "
            "Switching tools halfway through means redoing work already done."
        ),
        worked_example=(
            "The project manager agrees with the director that the renovation is planned in "
            "days rather than hours, that the contractor's dates and the volunteers' go in one "
            "shared calendar, and that the schedule is reviewed at the same Friday meeting as "
            "the budget."
        ),
        pitfalls=(
            "Planning in hours when the work is booked by the day, so every date needs converting.",
            "Keeping the contractor's dates in one calendar and the volunteers' in another.",
            "Agreeing a review cadence nobody holds once the work actually starts.",
        ),
    ),
    "6.2": ProcessContent(
        plain_summary="List the specific activities needed to produce each work package.",
        why_bother=(
            "A work package described only at a high level cannot be scheduled or assigned; "
            "naming the actual activities is what makes it plannable."
        ),
        done_when="Every work package has a named list of the activities that will produce it.",
        first_time_tip=(
            "Name each activity with a verb and an object, like 'draft the layout,' not just "
            "a noun. A verb forces you to say what actually gets done."
        ),
        worked_example=(
            '"Repair the water-damaged wall" becomes four activities: open the wall, dry it '
            "out, replace the studs and close it up. It has to be four, because the drying "
            "happens between two of them and one task could never show that wait."
        ),
        pitfalls=(
            "Leaving a work package as one activity when parts of it happen at different times.",
            "Naming an activity with a noun, so nobody can tell what work it actually involves.",
            "Listing activities for the visible work and forgetting inspections and sign-offs.",
        ),
    ),
    "6.3": ProcessContent(
        plain_summary="Work out which activities must happen before others can start.",
        why_bother=(
            "Without a defined order, the schedule cannot say what happens next or which "
            "delay ripples into which later task."
        ),
        done_when="Every activity's dependencies are recorded and the sequence forms a valid network.",
        first_time_tip=(
            "Ask 'what would stop this from starting' for every activity, not just what "
            "comes before it logically. Real-world blockers are easy to miss on paper."
        ),
        worked_example=(
            "Painting cannot start until the wall is closed up, and the shelving cannot go in "
            "until the paint is dry, so the three run end to start. The teen room's wiring "
            "depends on none of them and can happen any week the electrician is free."
        ),
        pitfalls=(
            "Linking every activity in a single chain when some could run side by side.",
            "Recording the obvious order and missing a dependency on someone outside the team.",
            "Treating a delivery date as a dependency without saying which activity it blocks.",
        ),
    ),
    "6.4": ProcessContent(
        plain_summary="Estimate how long each activity will realistically take to finish.",
        why_bother=(
            "An optimistic guess here understates the whole schedule, and everything built "
            "on top of it — the finish date, the staffing plan — inherits that understatement."
        ),
        done_when="Every activity carries a duration estimate with its basis and assumptions recorded.",
        first_time_tip=(
            "Give a range, not a single number, for anything you are not confident about. "
            "A range keeps the uncertainty visible instead of hiding it in one guess."
        ),
        worked_example=(
            "Repainting the reading room is three days for two painters, from the contractor's "
            "own rate. The wall repair is two to five days, because nobody has opened it yet — "
            "and that range is what keeps the doubt visible instead of buried in one number."
        ),
        pitfalls=(
            "Estimating the work and forgetting the waiting — drying, delivery, an inspection.",
            "Giving one confident number for the activity nobody has actually looked at yet.",
            "Shortening an estimate to fit a date that was promised before the estimate existed.",
        ),
    ),
    "6.5": ProcessContent(
        plain_summary="Combine the activities, their order, and their durations into one schedule.",
        why_bother=(
            "This is the step that finally answers 'when do we finish,' by pulling every "
            "earlier scheduling decision together into one calendar the team can commit to."
        ),
        done_when="A baseline schedule exists showing dates for every activity and the project finish.",
        first_time_tip=(
            "Find the critical path before you promise a finish date. It tells you exactly "
            "which activities have zero room to slip."
        ),
        worked_example=(
            "Pulled together, the activities put demolition and paint in March and the shelving "
            "in May, when the supplier can deliver. The critical path runs through the wall "
            "repair, so its two-to-five-day range is the range on the whole finish date."
        ),
        pitfalls=(
            "Promising a finish date before the critical path shows what has no slack.",
            "Building a calendar that ignores when the supplier can actually deliver.",
            "Baselining a schedule nobody who has to work to it has seen.",
        ),
    ),
    "6.6": ProcessContent(
        plain_summary="Track actual progress against the schedule and act when it slips.",
        why_bother=(
            "A schedule nobody rechecks against reality just quietly stops being true, and "
            "the first anyone hears about it is when the deadline is already missed."
        ),
        done_when="Actual progress is compared to the baseline regularly and any slip has a response.",
        first_time_tip=(
            "Update the schedule on a fixed cadence even when nothing seems to have "
            "changed. A schedule updated only when there is bad news stops being trusted."
        ),
        worked_example=(
            "Six weeks in, the wall repair has run to the five-day end of its range and painting "
            "has not started. It surfaces at the Friday review while the shelving delivery can "
            "still be moved, rather than in May when the van arrives at a room that is not ready."
        ),
        pitfalls=(
            "Comparing progress to the whole schedule instead of to what was planned by now.",
            "Updating the schedule only when there is bad news, so nobody trusts a quiet week.",
            "Recording a slip without deciding what happens to the dates that depend on it.",
        ),
    ),
}
