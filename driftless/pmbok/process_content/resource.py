"""Plain-language content for the Resource Management processes (9.1-9.6),
``KnowledgeArea.RESOURCE``.

Resource management covers both people and physical resources: plan who and
what you need, estimate and acquire them, build the team into a working
unit, lead them day to day, and keep both people and materials available.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "resource"

CONTENT: dict[str, ProcessContent] = {
    "9.1": ProcessContent(
        plain_summary="Decide, up front, who does what and what physical resources you need.",
        why_bother=(
            "Without a clear plan for roles and resources, two people quietly assume the "
            "same task belongs to the other, and neither of them does it."
        ),
        done_when="Roles, responsibilities, and needed physical resources are written down and assigned.",
        first_time_tip=(
            "Name a single owner for each role, even on a small team wearing several hats. "
            "A shared role without a named owner is where accountability disappears."
        ),
        worked_example=(
            "The renovation names one owner per role — the director accepts deliverables, the "
            "project manager runs the schedule, one coordinator handles the teen-room volunteers "
            "— and lists the physical resources too, down to the scaffold the high wall needs."
        ),
        pitfalls=(
            "Letting two people share a role with no single named owner.",
            "Listing the people and forgetting the physical resources the work needs.",
            "Writing the roles down but never telling the team who holds which.",
        ),
    ),
    "9.2": ProcessContent(
        plain_summary="Work out how many people and how much material each activity needs.",
        why_bother=(
            "Understaffing an activity means it slips; overstaffing it wastes budget that "
            "could have covered a different gap elsewhere in the project."
        ),
        done_when="Every activity carries a resource estimate with its basis recorded.",
        first_time_tip=(
            "Estimate resources at the same time you estimate duration, not afterward. The "
            "two numbers depend on each other and drift apart if done separately."
        ),
        worked_example=(
            "Repainting the reading room is estimated at two painters for three days, 30 litres "
            "of paint and one scaffold. The scaffold is the number that matters: only one is "
            "available locally that week, so the estimate and the schedule have to agree."
        ),
        pitfalls=(
            "Estimating the people and forgetting the materials and equipment.",
            "Estimating resources after durations, so the two numbers disagree.",
            "Recording a resource number with no basis anyone can question.",
        ),
    ),
    "9.3": ProcessContent(
        plain_summary="Actually get the people and materials the plan says you need.",
        why_bother=(
            "A great resource plan is worthless if the named people are unavailable or the "
            "materials cannot actually be obtained on the schedule the plan assumed."
        ),
        done_when="The people and physical resources the plan requires have been secured and are ready.",
        first_time_tip=(
            "Confirm availability with each person's actual manager, not just the person "
            "themselves. A verbal yes from the individual is not the same as a released commitment."
        ),
        worked_example=(
            "The two painters are confirmed with their own supervisor rather than only with "
            "them, and the scaffold is reserved in writing for the week the schedule needs it, "
            "not for the month around it."
        ),
        pitfalls=(
            "Taking an individual's yes as a commitment their manager has released.",
            "Securing the people but leaving the equipment to be found later.",
            "Booking a resource for roughly the right time rather than the scheduled week.",
        ),
    ),
    "9.4": ProcessContent(
        plain_summary="Help the team build the skills and trust they need to work well together.",
        why_bother=(
            "A group of individually skilled people who do not work well together produces "
            "worse results than a less skilled team that collaborates well."
        ),
        done_when="Team performance is improving and skill gaps identified earlier have been addressed.",
        first_time_tip=(
            "Invest in team-building early, before the pressure of a tight deadline makes it "
            "feel like time you cannot spare. It pays back most when the schedule gets hard."
        ),
        worked_example=(
            "The contractor's crew and the library volunteers have never worked together, so the "
            "first morning is spent walking the building as one group and agreeing who to ask "
            "about what — an hour that saves a week of volunteers guessing."
        ),
        pitfalls=(
            "Putting team-building off until the schedule is too tight to allow it.",
            "Training the paid staff and leaving the volunteers to work it out.",
            "Assuming an experienced group needs no introduction to each other.",
        ),
    ),
    "9.5": ProcessContent(
        plain_summary="Lead the team day to day: track performance, resolve conflict, give feedback.",
        why_bother=(
            "Unresolved conflict or unnoticed underperformance drags on quietly until it "
            "shows up as a missed deadline, by which point it is much harder to fix."
        ),
        done_when="Team performance is actively tracked, and conflicts and feedback are being addressed.",
        first_time_tip=(
            "Address a conflict as soon as you notice it, not once it disrupts the work. A "
            "small disagreement left alone tends to harden into a lasting grudge."
        ),
        worked_example=(
            "Two weeks in, a volunteer coordinator and the site foreman are both directing the "
            "same helpers. It comes out at the Friday walk-through, and who directs whom is "
            "settled that day instead of being left to harden."
        ),
        pitfalls=(
            "Waiting for a conflict to disrupt the work before addressing it.",
            "Saving feedback for the end, when nothing can be done with it.",
            "Tracking the tasks closely and the people not at all.",
        ),
    ),
    "9.6": ProcessContent(
        plain_summary="Make sure the equipment, materials and facilities you secured stay available when needed.",
        why_bother=(
            "A physical resource acquired once can still be pulled away to another "
            "project or run out partway through; this is what catches that before it "
            "stalls the work."
        ),
        done_when="Actual resource use is tracked against the plan and any shortfall has been resolved.",
        first_time_tip=(
            "Check resource availability at the start of every reporting period, not only "
            "when something has already gone wrong. A shortfall is cheaper to fix early."
        ),
        worked_example=(
            "Halfway through, the scaffold's rental is about to run out while the high wall "
            "still needs a second coat. The period check catches it in time to extend the "
            "booking, rather than the morning it disappears."
        ),
        pitfalls=(
            "Checking availability only after something has already stalled.",
            "Tracking the team's time but not the equipment and materials.",
            "Assuming a resource secured once stays secured to the end.",
        ),
    ),
}
