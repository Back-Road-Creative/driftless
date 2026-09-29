"""Plain-language content for the Quality Management processes (8.1-8.3),
``KnowledgeArea.QUALITY``.

Quality means deciding what "good enough" means before the work starts, then
building it in as you go, and finally checking the finished product actually
meets it.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "quality"

CONTENT: dict[str, ProcessContent] = {
    "8.1": ProcessContent(
        plain_summary="Decide what quality means for this project and how you will prove it.",
        why_bother=(
            "Without agreed standards, 'good enough' means something different to every "
            "stakeholder, and disagreements about whether work is done right multiply."
        ),
        done_when="Quality standards and the metrics used to check them are written down and agreed.",
        first_time_tip=(
            "Pick metrics that are cheap to measure regularly. A standard nobody can "
            "practically check gets skipped the first time the schedule is tight."
        ),
        worked_example=(
            '"Good enough" for the reading room is written down as paint with no roller marks '
            "visible under the room's own lighting and shelving that holds 40 kg a shelf — both "
            "things one person can check in ten minutes."
        ),
        pitfalls=(
            "Setting a standard nobody can check in the time the work actually allows.",
            "Borrowing a standard from a different kind of work without adapting it.",
            "Writing a metric with no number in it, so two people score it differently.",
        ),
    ),
    "8.2": ProcessContent(
        plain_summary="Build quality into the work as it happens, not just check it afterward.",
        why_bother=(
            "Catching a defect while the work is still in progress is far cheaper than "
            "finding it after the deliverable is finished and handed off."
        ),
        done_when="Quality activities from the plan are running alongside the work, not deferred to the end.",
        first_time_tip=(
            "Audit the process, not just the product, early in the project. A process fix "
            "prevents the same defect from recurring in every later deliverable."
        ),
        worked_example=(
            "The first run of shelving comes back with the wrong bracket spacing. Rather than "
            "redo that section and move on, the installer's own measuring step is audited, which "
            "is what keeps the same error out of the eleven sections still to come."
        ),
        pitfalls=(
            "Inspecting the product every time and never the process that produced it.",
            "Deferring every quality activity until the deliverable is already finished.",
            "Treating a single defect as bad luck rather than looking for its cause.",
        ),
    ),
    "8.3": ProcessContent(
        plain_summary="Check the finished product against the agreed standards before it ships.",
        why_bother=(
            "Shipping a defect the customer finds costs far more in rework, trust, and "
            "sometimes contract penalties than catching it here would have cost."
        ),
        done_when="Deliverables have been measured against the standards and any defect has been resolved.",
        first_time_tip=(
            "Sample early deliverables even if the process seems fine. A problem in the "
            "first batch is cheaper to fix than the same problem repeated across the rest."
        ),
        worked_example=(
            "Before the room reopens, a shelf is loaded to 40 kg and the paint is checked under "
            "the room's own lights against the standard agreed in Plan Quality Management. Both "
            "pass, and the reworked brackets are re-checked alongside them."
        ),
        pitfalls=(
            "Checking a deliverable against memory rather than the written standard.",
            "Sampling only the last batch, after the earlier ones have already shipped.",
            "Accepting a deliverable with an open defect on a promise to fix it later.",
        ),
    ),
}
