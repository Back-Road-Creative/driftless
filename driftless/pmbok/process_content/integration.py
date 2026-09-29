"""Plain-language content for the Integration Management processes (4.1-4.7),
``KnowledgeArea.INTEGRATION``.

Integration is the area that ties every other area's plans and changes
together into one coherent project, so these seven read as the spine of the
whole standard: authorize the work, plan it, do it, learn from it, watch it,
control what changes, and close it out.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "integration"

CONTENT: dict[str, ProcessContent] = {
    "4.1": ProcessContent(
        plain_summary=("Get formal sign-off that the project exists and names who is running it."),
        why_bother=(
            "Without this, nobody outside your own head has agreed the project is real, "
            "so any spending or staffing decision you make can be second-guessed or reversed."
        ),
        done_when="A sponsor has signed a charter naming the project, its purpose, and its manager.",
        first_time_tip=(
            "Keep the charter to a single page. A charter that reads like a plan invites "
            "line-by-line renegotiation instead of a quick yes."
        ),
        worked_example=(
            "A small nonprofit wants its aging branch library renovated before the next "
            "school year. The director drafts a one-page charter naming the goal, a rough "
            "budget ceiling, and herself as project manager, and the board chair signs it "
            "at the next meeting — the renovation is now an authorized project, not a wish."
        ),
        pitfalls=(
            "Writing a full plan instead of a charter, so the sponsor has to negotiate "
            "line items to get a yes.",
            "Letting work start before anyone with authority has actually signed off.",
            "Naming a project manager nobody with budget authority agreed to.",
        ),
    ),
    "4.2": ProcessContent(
        plain_summary="Pull every area's plan into one document everyone works from.",
        why_bother=(
            "A schedule that disagrees with the budget, or a risk plan nobody on the team has "
            "read, causes rework later that a single shared plan would have caught early."
        ),
        done_when="Every knowledge area's plan is written down in one place and the team has it.",
        first_time_tip=(
            "Write it as a living document, not a binder for the shelf. Revisit it whenever a "
            "change is approved so it never goes stale."
        ),
        worked_example=(
            "For the library renovation, the project manager pulls the scope statement, the "
            "contractor's schedule, the materials budget and the safety plan into one shared "
            "document, so the electrician's outage window and the painter's drying time are "
            "visible on the same timeline instead of living in two separate emails."
        ),
        pitfalls=(
            "Writing the plan once and never updating it as scope or schedule changes get approved.",
            "Letting each area's plan live in its own file, so nobody notices when two disagree.",
            "Making the plan so detailed it takes longer to read than the work it describes.",
        ),
    ),
    "4.3": ProcessContent(
        plain_summary="Actually do the work the plan describes, and keep records as you go.",
        why_bother=(
            "A plan nobody executes is just a wish. This is where the deliverables get built "
            "and the paper trail that later proves the work happened gets created."
        ),
        done_when="Deliverables are being produced and the work log reflects what has actually happened.",
        first_time_tip=(
            "Log decisions and issues as they happen, not from memory at the end of the week. "
            "A same-day note is worth more than a tidy summary written later."
        ),
        worked_example=(
            "The contractor starts demolition and framing on the library's reading room, "
            "the project manager logs the delivery dates for the new shelving, and a daily "
            "site note records that the water damage behind one wall was worse than expected."
        ),
        pitfalls=(
            "Treating the plan as final and never recording what actually happened.",
            "Letting issues pile up unlogged until the weekly status meeting.",
            "Producing deliverables nobody checks against the plan's acceptance criteria.",
        ),
    ),
    "4.4": ProcessContent(
        plain_summary="Capture what the team is learning so it does not walk out the door with them.",
        why_bother=(
            "A hard-won lesson that only lives in one person's head is lost the moment that "
            "person moves on, and the next project pays for relearning it."
        ),
        done_when="Lessons learned are written down and existing know-how has been put to use.",
        first_time_tip=(
            "Log a lesson the week it happens, while the details are still sharp. A lessons "
            "register built entirely at closeout is mostly guesswork."
        ),
        worked_example=(
            "After the hidden water damage delayed framing by a week, the project manager "
            "writes down that the pre-renovation inspection should have included a moisture "
            "reading behind that wall, so the next branch renovation budgets time for it."
        ),
        pitfalls=(
            "Waiting until the project closes to try to remember what went wrong.",
            "Recording lessons nobody on the next project will ever read.",
            "Only logging failures, so the team repeats mistakes it already avoided once.",
        ),
    ),
    "4.5": ProcessContent(
        plain_summary="Compare progress against the plan and flag what needs a decision.",
        why_bother=(
            "Small drift is cheap to correct and expensive to ignore. Catching it here, "
            "rather than at the next status meeting, is what keeps a slip from becoming a crisis."
        ),
        done_when="Current performance has been measured against the plan and any gap is documented.",
        first_time_tip=(
            "Check on a fixed schedule, not only when something already feels wrong. Regular "
            "checks catch drift before it is visible without one."
        ),
        worked_example=(
            "Two weeks into framing, the project manager compares actual spend and progress "
            "against the plan, sees the water-damage repair has eaten the contingency reserve, "
            "and flags that the painting phase now needs a decision on where the extra cost comes from."
        ),
        pitfalls=(
            "Only comparing plan to actuals when a stakeholder asks for a status update.",
            "Measuring progress without documenting what the gap means for the finish date.",
            "Treating every gap as equally urgent instead of triaging which one needs a decision now.",
        ),
    ),
    "4.6": ProcessContent(
        plain_summary="Route every proposed change through one gate before anyone acts on it.",
        why_bother=(
            "Letting changes happen informally is how scope creeps in unnoticed and one "
            "team's fix quietly breaks another team's assumption."
        ),
        done_when="Every change request has been reviewed and either approved, rejected, or deferred.",
        first_time_tip=(
            "Insist on the same review for a small change as a big one. The change that "
            "skips review because it looked minor is usually the one that causes a problem."
        ),
        worked_example=(
            "The contractor asks to substitute a cheaper shelving unit to cover the "
            "water-damage repair cost. The project manager logs it as a change request, "
            "the sponsor reviews the trade-off against the scope statement, and approves it "
            "in writing before the order is placed."
        ),
        pitfalls=(
            "Letting the contractor swap materials on a verbal okay with no written record.",
            "Approving a change without checking what it does to the schedule or budget.",
            "Treating a rejected change as a debate to keep having instead of a closed decision.",
        ),
    ),
    "4.7": ProcessContent(
        plain_summary="Formally end the project or phase and hand off what it produced.",
        why_bother=(
            "Work that is merely abandoned leaves loose ends: unreleased resources, unpaid "
            "invoices, and no clear record that the sponsor accepted the result."
        ),
        done_when="Final deliverables are accepted, contracts are closed, and resources are released.",
        first_time_tip=(
            "Book the closeout meeting before the team disperses. A closeout that has to be "
            "reconstructed after everyone has moved on rarely gets done well."
        ),
        worked_example=(
            "With the shelving installed and the reading room repainted, the director walks "
            "the space, signs off that the renovation matches what was promised, pays the "
            "contractor's final invoice, and releases the volunteers who helped move furniture."
        ),
        pitfalls=(
            "Letting the team scatter before final acceptance and invoices are settled.",
            "Skipping a written sign-off, so a later dispute has nothing to point to.",
            "Never releasing resources or closing contracts, leaving the project technically open.",
        ),
    ),
}
