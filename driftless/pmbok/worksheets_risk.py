"""Printable worksheets for the risk family's guide-only techniques.

Every key here is in ``FAMILIES["risk"]`` and in ``GUIDE_ONLY_REASONS``: no
assistant runs any of them, so a sheet a person fills in by hand is the honest
shape rather than a promise of a calculator that does not exist.
"""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="decision_tree_analysis",
        title="Decision tree worksheet",
        purpose="Lay out one decision, its options, and what each ending costs or earns.",
        sections=(
            WorksheetSection(
                heading="The decision and its branches",
                prompts=(
                    "What decision are you making, and by when?",
                    "What are the real options, including doing nothing?",
                    "For each option, what could happen next, and how likely is each?",
                    "What does each ending cost or earn, in money or in weeks?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you commit",
                prompts=(
                    "Every likelihood written above has a basis someone could defend.",
                    "The expected value is read as an average, not a promise about this run.",
                ),
                kind="check",
            ),
        ),
        outputs=("A tree with a value on every branch, and the chosen option with its reason.",),
    ),
    Worksheet(
        key="influence_diagrams",
        title="Influence diagram worksheet",
        purpose="Draw what actually affects an outcome, and which way the influence runs.",
        sections=(
            WorksheetSection(
                heading="The outcome and what moves it",
                prompts=(
                    "Which single outcome are you trying to explain?",
                    "Which things genuinely move it? List them before drawing anything.",
                    "For each, what does it affect, and what does that arrow mean?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Read it back",
                prompts=(
                    "Every arrow is a real influence, not two things merely mentioned together.",
                    "The arrows are labelled as the team's assumption, not as proven cause.",
                ),
                kind="check",
            ),
        ),
        outputs=("A one-page diagram of the outcome and the few things that move it.",),
    ),
    Worksheet(
        key="prompt_lists",
        title="Prompt list worksheet",
        purpose="Walk a list of risk categories to surface risks nobody raised.",
        sections=(
            WorksheetSection(
                heading="Category by category",
                prompts=(
                    "Which category list are you using, and why does it suit this project?",
                    "For each category, what could go wrong here, specifically?",
                    "Which categories produced nothing, and is that believable?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="After the pass",
                prompts=(
                    "Every new risk found here is written into the risk register.",
                    "This ran after the team's own ideas, not instead of them.",
                ),
                kind="check",
            ),
        ),
        outputs=("New risks in the register, each naming the category that surfaced it.",),
    ),
    Worksheet(
        key="representations_of_uncertainty",
        title="Uncertainty range worksheet",
        purpose="Replace a single guessed number with a range, and say what the range means.",
        sections=(
            WorksheetSection(
                heading="The range",
                prompts=(
                    "Which number is uncertain, and what figure is being quoted today?",
                    "What is the optimistic case, and what has to go right for it?",
                    "What is the pessimistic case, and what would cause it?",
                    "Which end of the range changes what you promise the client?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you quote it",
                prompts=(
                    "The range is wide because the uncertainty is real, not as padding.",
                    "The whole range is quoted from here on, not just the middle figure.",
                ),
                kind="check",
            ),
        ),
        outputs=("A low, likely and high figure for the number, with the reasoning for each.",),
    ),
    Worksheet(
        key="risk_categorization",
        title="Risk categorisation worksheet",
        purpose="Sort open risks by where they come from, then look for a heavy category.",
        sections=(
            WorksheetSection(
                heading="Sorting",
                prompts=(
                    "Which categories will you sort by, and will the team use them again?",
                    "Which category holds the most risks, and does one source explain them?",
                    "What single action would address that source rather than each risk alone?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Keeping it honest",
                prompts=(
                    "No risk was filed under a catch-all category just to finish the pass.",
                    "The tally is used to ask why a category is heavy, not taken as the finding.",
                ),
                kind="check",
            ),
        ),
        outputs=("A tally of risks per category, and the shared source worth acting on.",),
    ),
    Worksheet(
        key="sensitivity_analysis",
        title="Sensitivity analysis worksheet",
        purpose="Find the few inputs that actually move the outcome, one input at a time.",
        sections=(
            WorksheetSection(
                heading="One input at a time",
                prompts=(
                    "Which outcome are you testing, such as total cost or the finish date?",
                    "Which uncertain inputs feed it?",
                    "Moving each input across its range alone, how far does the outcome move?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Reading the result",
                prompts=(
                    "The inputs are ranked by how far each moved the outcome, largest first.",
                    "The ranking is revisited as estimates firm up, not settled once.",
                ),
                kind="check",
            ),
        ),
        outputs=("A ranked list of inputs by how far each one moves the outcome.",),
    ),
    Worksheet(
        key="simulation",
        title="Simulation input worksheet",
        purpose="Write down what a quantitative risk model would need before anyone runs one.",
        sections=(
            WorksheetSection(
                heading="What the model needs",
                prompts=(
                    "Which outcome is being modelled, and what decision rests on it?",
                    "For each input, what range or shape describes it, and on what evidence?",
                    "Which inputs move together, and why?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before trusting an output",
                prompts=(
                    "Every range comes from evidence, not from a figure chosen to look careful.",
                    "The tool that will run this is named; Driftless does not run it.",
                ),
                kind="check",
            ),
        ),
        outputs=("An input list with ranges and correlations, ready for a tool that runs it.",),
    ),
)
