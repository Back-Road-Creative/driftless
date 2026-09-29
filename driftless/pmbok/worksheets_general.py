"""Worksheets for the general family (``tt.FAMILIES["general"]``): the
cross-cutting techniques that stay guide-only, plus ``rolling_wave_planning``,
the entry that first proved discovery needs no other module change.

A guide-only technique still gets something to work with — a title, what the
sheet is for, prompts a person can actually answer in a room, and what the
filled-in sheet produces. ``_worksheet.html`` renders one as a printable
no-script form. Nothing here asserts anything about PMBOK-6: these prompts are
practice, and the edition citations live in ``technique_content``.
"""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="rolling_wave_planning",
        title="Rolling wave planning worksheet",
        purpose="Split the horizon into a detailed near wave and summary far waves, each with a trigger.",
        sections=(
            WorksheetSection(
                heading="Near and far waves",
                prompts=(
                    "Where does the near wave end, in detail (tasks/owners/estimates)?",
                    "Name each far wave, its rough duration and owner.",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Triggers",
                prompts=("Every far-wave placeholder is labelled provisional.",),
                kind="check",
            ),
        ),
        outputs=("A schedule with detailed near-term tasks and labelled far-wave placeholders.",),
    ),
    Worksheet(
        key="communication_models",
        title="Communication model check worksheet",
        purpose="Walk one important message end to end and find where it breaks down.",
        sections=(
            WorksheetSection(
                heading="The message",
                prompts=(
                    "Which message are you checking, and who has to act on it?",
                    "What could distort it on the way — jargon, a crowded channel, bad news?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you send",
                prompts=("You named how the receiver will confirm they understood.",),
                kind="check",
            ),
        ),
        outputs=("A named message, the distortion you expect, and the check you added.",),
    ),
    Worksheet(
        key="communication_requirements_analysis",
        title="Who needs what information worksheet",
        purpose="Decide what each group is sent, how often, and who sends it.",
        sections=(
            WorksheetSection(
                heading="Each group",
                prompts=(
                    "List each group and the one decision they make with project information.",
                    "What do they need, how often, and in what form?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you commit to it",
                prompts=(
                    "Every item on the list has a named person who sends it.",
                    "Nothing is on the list only because it has always been sent.",
                ),
                kind="check",
            ),
        ),
        outputs=("A list of what is sent, to whom, how often, and by whom.",),
    ),
    Worksheet(
        key="communication_skills",
        title="Difficult conversation prep sheet",
        purpose="Plan a hard conversation before you are in the room having it.",
        sections=(
            WorksheetSection(
                heading="What you want out of it",
                prompts=(
                    "What must the other person know, and what must you learn from them?",
                    "What are your first two sentences?",
                    "What outcome would you still accept if you cannot get the best one?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you start",
                prompts=("You planned a question you do not already know the answer to.",),
                kind="check",
            ),
        ),
        outputs=("An opening, the question you will ask, and the outcome you can accept.",),
    ),
    Worksheet(
        key="data_analysis",
        title="Choosing an analysis worksheet",
        purpose="Pick a method by writing the question first, so the answer can be wrong.",
        sections=(
            WorksheetSection(
                heading="The question",
                prompts=(
                    "What are you trying to find out, in one sentence?",
                    "Which method fits it, and what would change your mind about the answer?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you start",
                prompts=("The data you already have can answer the question you wrote.",),
                kind="check",
            ),
        ),
        outputs=("A written question, the method chosen for it, and what would disprove it.",),
    ),
    Worksheet(
        key="data_gathering",
        title="Interview and brainstorm guide",
        purpose="Prepare a session that collects usable answers and writes them down.",
        sections=(
            WorksheetSection(
                heading="Before the session",
                prompts=(
                    "What do you need to find out, and who actually has it?",
                    "Write the opening question and three follow-ups you will ask everyone.",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="In the room",
                prompts=(
                    "Everyone knows why they were asked and what happens to their answers.",
                    "Someone is writing answers down as they are given.",
                ),
                kind="check",
            ),
        ),
        outputs=("A written question set, the session notes, and who said what.",),
    ),
    Worksheet(
        key="data_representation",
        title="Picking a picture worksheet",
        purpose="Choose a chart by naming the conclusion it has to support.",
        sections=(
            WorksheetSection(
                heading="What it has to show",
                prompts=(
                    "What should a reader conclude within ten seconds of looking at it?",
                    "Is that a ranking, a share of a whole, a change over time, or a relationship?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you publish it",
                prompts=(
                    "It is still readable printed in black and white.",
                    "Every axis and unit is labelled.",
                ),
                kind="check",
            ),
        ),
        outputs=("A chart shape, its labels, and the one sentence it supports.",),
    ),
    Worksheet(
        key="decision_making",
        title="Decision and vote sheet",
        purpose="Record what was decided, by whom, and under which rule.",
        sections=(
            WorksheetSection(
                heading="The decision",
                prompts=(
                    "State it as a question with a short list of options.",
                    "Who decides, who advises, and who only needs telling afterwards?",
                    "Record the count for each option.",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before the vote",
                prompts=(
                    "Each option had someone speak for it.",
                    "The rule for deciding was agreed before anyone voted.",
                ),
                kind="check",
            ),
        ),
        outputs=("The decision, the option counts, the rule used, and the date.",),
    ),
    Worksheet(
        key="expert_judgment",
        title="Expert input record",
        purpose="Capture what an expert was asked and told, not just what they concluded.",
        sections=(
            WorksheetSection(
                heading="The question",
                prompts=(
                    "Write the exact question before you contact anyone.",
                    "Who has standing on it, and what background will you give them?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you use the answer",
                prompts=(
                    "More than one person was asked, if the decision is a consequential one.",
                    "You recorded what each was told, not only what they concluded.",
                ),
                kind="check",
            ),
        ),
        outputs=("The question, who answered, what they were told, and where it was used.",),
    ),
    Worksheet(
        key="interpersonal_and_team_skills",
        title="Team working agreement worksheet",
        purpose="Agree how this team will work together before it is under pressure.",
        sections=(
            WorksheetSection(
                heading="How we work",
                prompts=(
                    "How does this team decide when it cannot agree?",
                    "How does someone raise a problem early without it sounding like a complaint?",
                    "What does this team expect of someone who is stuck?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you write it down",
                prompts=("Everyone present said something before the agreement was written.",),
                kind="check",
            ),
        ),
        outputs=("A short written agreement the team can point back at.",),
    ),
    Worksheet(
        key="project_management_information_system",
        title="Project tooling inventory worksheet",
        purpose="List the tools the project depends on, and who can get into each one.",
        sections=(
            WorksheetSection(
                heading="Each tool",
                prompts=(
                    "Which tool holds which record, and who administers it?",
                    "Who can read it today without asking someone first?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Risk check",
                prompts=(
                    "Every tool on the list has a named administrator.",
                    "Anything holding the only copy of a record is marked as such.",
                ),
                kind="check",
            ),
        ),
        outputs=("A tool-by-tool list with owners, access, and the records only it holds.",),
    ),
    Worksheet(
        key="project_reporting",
        title="Status report planning worksheet",
        purpose="Decide what a report says by naming who reads it and what they do next.",
        sections=(
            WorksheetSection(
                heading="The audience",
                prompts=(
                    "Who reads this, and what do they do differently afterwards?",
                    "What is the shortest set of facts that supports that?",
                    "How often does it go out, and who writes it?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you send it",
                prompts=("Bad news appears in the report, not only in conversation.",),
                kind="check",
            ),
        ),
        outputs=("A report outline: the audience, the facts in it, and how often it goes out.",),
    ),
)
