"""Plain-language content for the Cost Management processes (7.1-7.4),
``KnowledgeArea.COST``.

Cost management is deciding what the work should cost, turning that into a
budget that is time-phased against the schedule, and then watching actual
spend against it.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "cost"

CONTENT: dict[str, ProcessContent] = {
    "7.1": ProcessContent(
        plain_summary="Decide, up front, how you will estimate, budget, and control cost.",
        why_bother=(
            "Without an agreed method, one estimator's numbers and another's cannot be "
            "compared, and the budget nobody trusted from the start rarely gets trusted later."
        ),
        done_when="A cost management approach is written down and the team is using it.",
        first_time_tip=(
            "Decide your cost estimating precision before the first estimate is made. "
            "Rounding rules that change midway confuse every comparison after that."
        ),
        worked_example=(
            "For the library renovation the project manager agrees with the director that "
            "estimates round to the nearest $500, that a written contractor quote is the basis "
            "for any figure over $5,000, and that spend is reviewed at the same Friday meeting "
            "as the schedule."
        ),
        pitfalls=(
            "Changing the rounding rules midway, so no two estimates can be compared.",
            "Leaving how reserve is held undecided until the first estimate needs one.",
            "Writing a cost plan the person who pays the invoices never sees.",
        ),
    ),
    "7.2": ProcessContent(
        plain_summary="Work out roughly how much each activity will realistically cost.",
        why_bother=(
            "An estimate padded too high loses the project to a competitor or a budget cut; "
            "one that is too low sets the project up to run out of money before it finishes."
        ),
        done_when="Every activity carries a cost estimate with its basis and assumptions recorded.",
        first_time_tip=(
            "Estimate a reserve for the risks you already know about, separately from the "
            "activity costs themselves. Blending the two hides how much of the number is a guess."
        ),
        worked_example=(
            "Repainting the reading room is estimated at $8,000 from a contractor quote and the "
            "shelving at $22,000 from last year's branch project, with $3,000 held separately as "
            "reserve against the water damage behind a wall nobody has opened yet."
        ),
        pitfalls=(
            "Taking one quote as the estimate when a second would have shown the range.",
            "Blending reserve into activity costs, hiding how much of the number is a guess.",
            "Recording the figure but not its basis, so nobody can re-check it later.",
        ),
    ),
    "7.3": ProcessContent(
        plain_summary="Add up the activity costs into an approved, time-phased budget.",
        why_bother=(
            "The activity estimates alone do not say when money is needed, and a budget "
            "with no timing tells finance nothing useful about cash flow."
        ),
        done_when="An approved cost baseline exists, showing planned spend against the schedule over time.",
        first_time_tip=(
            "Plot the budget as a curve against the schedule before you finalize it. A flat "
            "line rarely matches how spending actually happens over a project."
        ),
        worked_example=(
            "The activity estimates add up to $41,000, and spreading them across the schedule — "
            "demolition and paint in March, shelving in May when the supplier can deliver — is "
            "what tells the board it needs $18,000 available before April."
        ),
        pitfalls=(
            "Adding the estimates up but never spreading them across the schedule.",
            "Ignoring a funding limit until the month the money is not there.",
            "Baselining a budget the schedule has already moved past.",
        ),
    ),
    "7.4": ProcessContent(
        plain_summary="Track actual spending against the budget and act on the gap.",
        why_bother=(
            "A project that only discovers it is over budget at the very end has no time "
            "left to correct course; catching the gap early is what makes a fix possible."
        ),
        done_when="Actual spend is compared to the baseline regularly and any variance has a response.",
        first_time_tip=(
            "Update actual spend as often as you update the schedule, not less often. A cost "
            "report that lags the schedule hides overruns until they are already large."
        ),
        worked_example=(
            "Six weeks in, $19,000 is spent against the $14,000 planned by that point, because "
            "the wall repair ran deeper than the quote assumed. It surfaces at the Friday review "
            "while reserve can still cover it, rather than at handover."
        ),
        pitfalls=(
            "Comparing spend to the whole budget instead of to what was planned by now.",
            "Updating actual spend less often than the schedule, so overruns surface late.",
            "Treating a draw on reserve as free because the total still fits.",
        ),
    ),
}
