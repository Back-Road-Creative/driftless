"""Plain-language content for the Scope Management processes (5.1-5.6),
``KnowledgeArea.SCOPE``.

Scope is the discipline of deciding what the project will and will not
deliver, and then keeping that boundary honest as everyone asks for more.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "scope"

CONTENT: dict[str, ProcessContent] = {
    "5.1": ProcessContent(
        plain_summary="Decide, up front, how you will define and control what is in scope.",
        why_bother=(
            "Without an agreed method for defining and approving scope, every stakeholder "
            "applies their own idea of what counts as in-bounds, and arguments follow."
        ),
        done_when="A scope management approach is written down and the team is using it.",
        first_time_tip=(
            "Match the approach to the project's size. A one-page scope plan is plenty for "
            "a small effort; save the detailed version for something genuinely complex."
        ),
        worked_example=(
            "For the library renovation, the project manager writes one page saying scope "
            "changes get logged as change requests and reviewed by the director every Friday "
            "— small enough that a heavier scope-management process would only slow things down."
        ),
        pitfalls=(
            "Copying a large project's scope process onto a small one and drowning in paperwork.",
            "Never writing the approach down, so each new request is handled ad hoc.",
            "Choosing an approach nobody on the team actually follows once work starts.",
        ),
    ),
    "5.2": ProcessContent(
        plain_summary="Find out, in detail, what stakeholders actually need from the project.",
        why_bother=(
            "A requirement missed here surfaces later as a change request, and a late change "
            "almost always costs more than the same requirement caught at the start."
        ),
        done_when="Requirements are documented, traced, and stakeholders agree they are complete.",
        first_time_tip=(
            "Interview stakeholders one at a time before you run a group workshop. A quiet "
            "voice gets heard alone that a loud group would talk over."
        ),
        worked_example=(
            "The project manager interviews the head librarian, a teen-program volunteer and "
            "an accessibility advocate separately, and learns the teen room needs power outlets "
            "at every table — a requirement none of them would have raised in a joint meeting."
        ),
        pitfalls=(
            "Only asking the loudest stakeholder and assuming their wish list speaks for everyone.",
            "Gathering requirements but never writing them down where they can be traced later.",
            "Closing requirements gathering before every named stakeholder has actually weighed in.",
        ),
    ),
    "5.3": ProcessContent(
        plain_summary="Turn the gathered requirements into a clear statement of what is in and out.",
        why_bother=(
            "A vague scope statement leaves room for everyone to read it their own way, and "
            "that gap is exactly where scope creep gets in."
        ),
        done_when="A scope statement exists naming what is included and, just as clearly, what is not.",
        first_time_tip=(
            "Write the exclusions as plainly as the inclusions. What you are not doing "
            "prevents more arguments later than what you are doing."
        ),
        worked_example=(
            "The scope statement says the project repaints the reading room, replaces the "
            "shelving and adds teen-room outlets, and explicitly excludes the roof, which the "
            "board keeps raising but has never funded."
        ),
        pitfalls=(
            "Listing only inclusions and letting exclusions stay implied.",
            "Writing the statement so vaguely two readers could disagree on what it covers.",
            "Leaving out a boundary a stakeholder has already raised more than once.",
        ),
    ),
    "5.4": ProcessContent(
        plain_summary="Break the total work down into smaller pieces small enough to plan.",
        why_bother=(
            "A single giant task is too big to estimate, staff, or track. Breaking it down "
            "is what makes the rest of planning possible at all."
        ),
        done_when="Every piece of work is decomposed into a work package small enough to assign and track.",
        first_time_tip=(
            "Stop decomposing once a piece is small enough to estimate and assign to one "
            "owner. Breaking it down further just adds bookkeeping."
        ),
        worked_example=(
            '"Renovate the reading room" becomes work packages: demolish old shelving, '
            "repair the water-damaged wall, repaint, install new shelving, wire the teen "
            "room's outlets — each small enough for one contractor crew to own and estimate."
        ),
        pitfalls=(
            "Stopping decomposition too early, leaving a work package too big to estimate.",
            "Decomposing so far that tracking the pieces costs more than the work itself.",
            "Missing a piece of work entirely because nothing in the WBS names it.",
        ),
    ),
    "5.5": ProcessContent(
        plain_summary="Get the customer to formally accept each finished deliverable.",
        why_bother=(
            "Skipping formal acceptance leaves the door open for a customer to reject work "
            "much later, after the team has already moved on to the next task."
        ),
        done_when="Every completed deliverable has been formally accepted by the customer or sponsor.",
        first_time_tip=(
            "Get acceptance deliverable by deliverable, not in one bundle at the end. A "
            "problem found early is far cheaper to fix than one found at the finish line."
        ),
        worked_example=(
            "As soon as the new shelving is installed, the director walks the room and signs "
            "off on it, instead of waiting until the whole renovation — paint and outlets "
            "included — is finished to accept anything."
        ),
        pitfalls=(
            "Waiting until the very end to accept every deliverable at once.",
            'Treating a verbal "looks good" as formal acceptance with nothing written down.',
            "Accepting a deliverable nobody actually inspected against its requirements.",
        ),
    ),
    "5.6": ProcessContent(
        plain_summary="Watch for scope drifting from what was agreed, and correct it.",
        why_bother=(
            "Unmanaged scope drift is one of the most common ways a project quietly runs "
            "over budget and over schedule without anyone deciding that it should."
        ),
        done_when="Actual scope is being compared to the baseline, and any drift routes through change control.",
        first_time_tip=(
            "Say no to a small favor as readily as a big one. Small unapproved additions "
            "add up to the same overrun a single big one would cause."
        ),
        worked_example=(
            "A volunteer asks the contractor to also repaint the hallway \"while they're at "
            'it." The project manager checks it against the scope statement, sees it is '
            "excluded, and routes it through change control instead of letting it happen quietly."
        ),
        pitfalls=(
            "Saying yes to a small request because it seems too minor to bother with change control.",
            "Only checking for scope drift when the budget already looks wrong.",
            "Letting an unapproved addition become the new normal because nobody said no.",
        ),
    ),
}
