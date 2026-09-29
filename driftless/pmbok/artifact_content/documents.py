"""Artifact explanations for the documents family (artifacts.FAMILIES["documents"]).

The working artifacts a process reads and revises day to day — logs, lists,
estimates and registers — as opposed to the frozen plans and baselines above
them.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "documents"

CONTENT: dict[str, ArtifactContent] = {
    "assumption_log": ArtifactContent(
        plain_summary="A running list of things the team is guessing are true but hasn't confirmed.",
        why_it_matters="An unstated assumption that turns out wrong is one of the most common ways plans fail quietly.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "issue_log": ArtifactContent(
        plain_summary="A running list of problems that are actually happening right now, not just risks.",
        why_it_matters="Naming a problem is the first step to fixing it; an untracked issue tends to stay unresolved.",
        what_it_looks_like_here=(
            "The project's dated issue rows, each with a status; healthy only once none of "
            "them are still open or in progress."
        ),
    ),
    "change_log": ArtifactContent(
        plain_summary="A running list of every request to change the plan, and what happened to it.",
        why_it_matters="It is how anyone can later answer 'why does the plan look different from the original?'.",
        what_it_looks_like_here="The project's dated change-request rows.",
    ),
    "lessons_learned_register": ArtifactContent(
        plain_summary="Notes on what worked and what didn't, written down so the next project can use them.",
        why_it_matters="Without it, every project relearns the same hard lessons the last one already paid for.",
        what_it_looks_like_here="Stored as one dated row per lesson, each naming what happened and what to do next time.",
    ),
    "milestone_list": ArtifactContent(
        plain_summary="The short list of major checkpoints the project is aiming to hit, and when.",
        why_it_matters="It gives everyone a small number of dates to rally around instead of tracking every task.",
        what_it_looks_like_here=(
            "The project's milestone rows; healthy only while none of them have been missed."
        ),
    ),
    "project_schedule": ArtifactContent(
        plain_summary="The actual plan of when work happens, built from milestones and work cycles.",
        why_it_matters="It turns a list of tasks into a plan anyone can follow day to day.",
        what_it_looks_like_here="Read from the project's milestones and sprints together.",
    ),
    "schedule_data": ArtifactContent(
        plain_summary="The supporting numbers behind the schedule, like planned start and finish windows.",
        why_it_matters="It is the detail a reader checks when a date on the schedule looks wrong.",
        what_it_looks_like_here=(
            "Not stored separately: the project's timeline view draws directly from the "
            "approved baseline's planned windows rather than a computed extra copy."
        ),
    ),
    "activity_list": ArtifactContent(
        plain_summary="The full list of individual pieces of work the project is broken into.",
        why_it_matters="Without an enumerated list, nobody can say the plan actually covers everything.",
        what_it_looks_like_here=(
            "Not counted separately: it is exactly the count Activity Attributes already "
            "keeps, read rather than duplicated."
        ),
    ),
    "activity_attributes": ArtifactContent(
        plain_summary="The details behind each piece of work, like how big it is and who owns it.",
        why_it_matters="A task nobody has sized cannot be scheduled or weighed against how much time is available.",
        what_it_looks_like_here=(
            "The project's tasks themselves — name, status, size estimate, actual effort "
            "and owner; healthy only once every task has been sized."
        ),
    ),
    "project_schedule_network_diagram": ArtifactContent(
        plain_summary="A picture of which pieces of work have to happen before others can start.",
        why_it_matters="It shows where a delay in one place will ripple into delays somewhere else.",
        what_it_looks_like_here="Not tracked: tasks here carry no recorded links to each other, so there is no diagram to draw.",
    ),
    "duration_estimates": ArtifactContent(
        plain_summary="How long each piece of work is expected to take.",
        why_it_matters="Without an estimate for each piece, the schedule is a guess dressed up as a plan.",
        what_it_looks_like_here="The single size estimate recorded on each task, rather than a separate range document.",
    ),
    "basis_of_estimates": ArtifactContent(
        plain_summary="A short note on how an estimate was actually worked out, not just the number itself.",
        why_it_matters="An estimate nobody can explain cannot be trusted, checked, or improved next time.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "cost_estimates": ArtifactContent(
        plain_summary="How much each piece of the project is expected to cost.",
        why_it_matters="It is what the whole budget gets built up from, one piece at a time.",
        what_it_looks_like_here="The single planned amount recorded on each budget line, rather than a separate document.",
    ),
    "project_calendars": ArtifactContent(
        plain_summary="The working days and hours the schedule assumes people are actually available.",
        why_it_matters="A schedule that ignores holidays and weekends will always run late in practice.",
        what_it_looks_like_here=(
            "Not tracked as a calendar record: the plan's dates come straight from the "
            "approved baseline's windows."
        ),
    ),
    "requirements_documentation": ArtifactContent(
        plain_summary="A written record of what people actually need the project to deliver.",
        why_it_matters="Without it, 'what was asked for' becomes a matter of memory and opinion.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "requirements_traceability_matrix": ArtifactContent(
        plain_summary="A table linking each need back to the piece of work that satisfies it.",
        why_it_matters="It lets anyone check that every requirement is actually covered by something, not dropped.",
        what_it_looks_like_here="Not tracked: there is no individual requirement row to trace, so the approved scope baseline stands in for it.",
    ),
    "project_scope_statement": ArtifactContent(
        plain_summary="A written description of exactly what is, and is not, included in the project.",
        why_it_matters="It is the reference that ends 'is this in scope?' arguments before they start.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "work_breakdown_structure": ArtifactContent(
        plain_summary="A tree that breaks the whole project down into smaller and smaller pieces of work.",
        why_it_matters="It is how a huge, vague goal becomes a set of small, assignable pieces of work.",
        what_it_looks_like_here="Not tracked as its own tree: the project's own workstream and task hierarchy plays that role.",
    ),
    "risk_register": ArtifactContent(
        plain_summary="A running list of things that could go wrong, and how likely and serious each one is.",
        why_it_matters="A risk nobody wrote down is a risk nobody is watching for.",
        what_it_looks_like_here=(
            "The project's risk rows; healthy only while none of them have actually happened yet."
        ),
    ),
    "risk_report": ArtifactContent(
        plain_summary="A summary of the project's overall risk picture, not just the individual entries.",
        why_it_matters="It answers 'how worried should we be overall?' rather than making a reader add it up themselves.",
        what_it_looks_like_here="Not stored separately: read the risk register directly for the same picture.",
    ),
    "quality_metrics": ArtifactContent(
        plain_summary="The specific numbers and targets the team uses to judge whether work is good enough.",
        why_it_matters="Without agreed numbers, 'good enough' is decided by opinion after the fact.",
        what_it_looks_like_here="Not stored separately: each measurement row already carries its own target value.",
    ),
    "quality_control_measurements": ArtifactContent(
        plain_summary="The actual readings taken while checking whether work meets its target.",
        why_it_matters="It is the evidence behind a claim that quality was checked, not just assumed.",
        what_it_looks_like_here="The project's dated measurement rows themselves — read the quality report for the summary.",
    ),
    "quality_report": ArtifactContent(
        plain_summary="A current summary of how well the work is meeting its quality targets.",
        why_it_matters="It turns individual measurements into one answer to 'are we on target right now?'.",
        what_it_looks_like_here=(
            "The most recent measurement for the project; healthy only when it is both "
            "recent and within its target."
        ),
    ),
    "resource_requirements": ArtifactContent(
        plain_summary="What people and other resources the project needs, and how much of each.",
        why_it_matters="Without it, staffing decisions are made by feel instead of by comparing need to capacity.",
        what_it_looks_like_here="Not stored separately: implied by comparing task assignments against available capacity.",
    ),
    "resource_breakdown_structure": ArtifactContent(
        plain_summary="A tree that organizes the project's people and resources into groups.",
        why_it_matters="It makes it easier to see where capacity is thin before it becomes a crisis.",
        what_it_looks_like_here="Not tracked as its own tree: people here sit directly under departments instead.",
    ),
    "resource_calendars": ArtifactContent(
        plain_summary="When each specific person or resource is actually available to work.",
        why_it_matters="A plan that ignores who is actually free will keep assigning work to people who are already busy.",
        what_it_looks_like_here="Not tracked as a calendar record: capacity here is shown as weekly hours instead.",
    ),
    "team_charter": ArtifactContent(
        plain_summary="A short written agreement on how the team will work together.",
        why_it_matters="It heads off conflict by settling working norms before people are annoyed by each other.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "project_team_assignments": ArtifactContent(
        plain_summary="A record of exactly which person is doing which piece of work.",
        why_it_matters="Work with nobody clearly responsible for it tends to quietly not get done.",
        what_it_looks_like_here=(
            "Each task's named owner; healthy only once every single task has one."
        ),
    ),
    "physical_resource_assignments": ArtifactContent(
        plain_summary="A record of which equipment, materials or other non-person resources are assigned to the work.",
        why_it_matters="Work that needs equipment nobody has reserved tends to stall waiting for it.",
        what_it_looks_like_here="Not tracked: people are the only kind of resource this system follows.",
    ),
    "stakeholder_register": ArtifactContent(
        plain_summary="A list of everyone with a stake in the project, and what matters to them.",
        why_it_matters="A stakeholder nobody wrote down is a stakeholder nobody planned to keep informed.",
        what_it_looks_like_here="The project's recorded stakeholder rows.",
    ),
    "test_and_evaluation_documents": ArtifactContent(
        plain_summary="Written plans and results for formally testing whether the work actually meets its targets.",
        why_it_matters="Without a written test plan, checking quality becomes an informal habit instead of a repeatable process.",
        what_it_looks_like_here="Not tracked as its own document: the dated quality measurements stand in as the evidence.",
    ),
    "project_communications": ArtifactContent(
        plain_summary="A record of what was actually told to people, not just that a report was filed.",
        why_it_matters="Filing a status number nobody reads is not the same as keeping people informed.",
        what_it_looks_like_here=(
            "The project's status updates that actually carry a written note; healthy only "
            "while the most recent noted update is still fresh."
        ),
    ),
    "cost_forecasts": ArtifactContent(
        plain_summary="A projection of how much the project will end up costing if trends continue.",
        why_it_matters="It gives an early warning about a budget problem before the money is actually gone.",
        what_it_looks_like_here="Not stored: computed on the fly from the project's cost snapshot rather than kept as a saved copy.",
    ),
    "schedule_forecasts": ArtifactContent(
        plain_summary="A projection of when the project is likely to actually finish, based on recent pace.",
        why_it_matters="It replaces hoping a schedule will hold with an honest, evidence-based estimate.",
        what_it_looks_like_here="Not stored: computed on the fly from recent work-cycle pace rather than kept as a saved copy.",
    ),
    "project_funding_requirements": ArtifactContent(
        plain_summary="How much money is needed, and when, to keep the project funded on schedule.",
        why_it_matters="It keeps the project from running out of approved funds mid-task.",
        what_it_looks_like_here="Not stored: worked out on the fly from the project's budget lines rather than kept as a saved copy.",
    ),
    "team_performance_assessments": ArtifactContent(
        plain_summary="A written check on how well the team is actually working together.",
        why_it_matters="A team's effectiveness is easy to assume and rarely checked; writing it down forces an honest look.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
}
