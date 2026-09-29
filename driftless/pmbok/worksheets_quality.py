"""Worksheets for the quality family's guide-only techniques: five judgment
calls no calculator can make, each turned into the questions a person answers
in the room while the work is still changeable."""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="design_for_x",
        title="Design for one concern worksheet",
        purpose="Name the later concern this design must serve, and rules a reviewer can check.",
        sections=(
            WorksheetSection(
                heading="The concern and its rules",
                prompts=(
                    "Which later concern matters most — making it, fixing it, cost, safety?",
                    "Who owns that concern, and are they reading the draft while it is a draft?",
                    "Write two or three rules a reviewer can check without asking you.",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before the design is signed off",
                prompts=(
                    "The draft has been read against each rule, one at a time.",
                    "Where two concerns pulled apart, the winner and the reason are written down.",
                ),
                kind="check",
            ),
        ),
        outputs=("A named concern, a few checkable rules, and a record of any trade-off made.",),
    ),
    Worksheet(
        key="problem_solving",
        title="Problem solving worksheet",
        purpose="Get from something is wrong to a fix you can tell actually worked.",
        sections=(
            WorksheetSection(
                heading="State it, then solve it",
                prompts=(
                    "Write the problem so everyone in the room would describe it the same way.",
                    "What says this is the problem itself and not a symptom of another one?",
                    "List at least two ways forward before judging any of them.",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you call it fixed",
                prompts=(
                    "The choice was judged against the constraints, not against who suggested it.",
                    "You wrote down in advance what would show the fix is working.",
                ),
                kind="check",
            ),
        ),
        outputs=("A written problem, the options weighed, the choice, and the signal to watch.",),
    ),
    Worksheet(
        key="quality_improvement_methods",
        title="Improvement cycle worksheet",
        purpose="Run one small measured change instead of a rewrite, and keep it if it works.",
        sections=(
            WorksheetSection(
                heading="Baseline and change",
                prompts=(
                    "What are you measuring, and what does it read today?",
                    "Which single change do you think moves it, and why that one?",
                    "How small can the trial be and still tell you something?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="After the trial",
                prompts=(
                    "The same measurement was taken again, the same way.",
                    "A change that worked is now how the work is normally done.",
                ),
                kind="check",
            ),
        ),
        outputs=("A before and after reading, and either a new normal or the next thing to try.",),
    ),
    Worksheet(
        key="test_and_inspection_planning",
        title="Test and inspection plan worksheet",
        purpose="Decide what gets checked, how, when and by whom, while the plan can still hold it.",
        sections=(
            WorksheetSection(
                heading="Per deliverable",
                prompts=(
                    "What must be true of this before anyone accepts it?",
                    "How is that checked — every one, a sample, a test, a signature?",
                    "When is a fault cheapest to catch, before later work hides it?",
                    "Who does the check, and who is allowed to reject?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before the plan is agreed",
                prompts=(
                    "Pass and fail are written down, not judged in the moment.",
                    "Each check sits in the schedule as real work with time against it.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A check per acceptance rule, with a method, a moment, an owner and a pass mark.",
        ),
    ),
    Worksheet(
        key="testing_product_evaluations",
        title="Product evaluation worksheet",
        purpose="Check the thing itself against what it was promised to do, and by how much.",
        sections=(
            WorksheetSection(
                heading="The run",
                prompts=(
                    "Which written rule is this evaluation checking?",
                    "Under what conditions — how close are they to real use?",
                    "What was the reading, and how far is it from the target?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="After the run",
                prompts=(
                    "A failure went back to the owner naming the exact rule missed.",
                    "A pass is recorded with its margin, not only as a pass.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A dated record per rule with the reading, the margin, and where a failure went.",
        ),
    ),
)
