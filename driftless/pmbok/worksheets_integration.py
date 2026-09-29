"""Printable worksheets for the integration family (``tt.FAMILIES["integration"]``).

All three of its techniques are guide-only for the same recorded reason: each
names whatever tooling the organisation already runs
(``reasons.GUIDE_ONLY_REASONS``), so there is nothing for Driftless to compute
and no assistant it could honestly offer. A worksheet is the honest offer
instead — a page a team fills in about their own tooling and habits.

The prompts stay deliberately close to what ``technique_content/integration.py``
already teaches, so a reader who follows the technique page into the worksheet
meets the same distinctions: impact assessed downstream before a decision, one
findable home per fact, and knowledge moving between people rather than being
filed.
"""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="change_control_tools",
        title="Change control worksheet",
        purpose=(
            "Decide how a proposed change to an already-approved plan gets assessed, decided "
            "and recorded in the tools this organisation already runs."
        ),
        sections=(
            WorksheetSection(
                heading="What is being asked for",
                prompts=(
                    "What is the change, in one sentence someone outside the project would follow?",
                    "Which approved dates, costs or pieces of scope would it move?",
                    "Who raised it, and on what date?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Impact, worked out before anyone decides",
                prompts=(
                    "Which other work depends on the task named, and how far does the knock-on "
                    "effect reach?",
                    "What is the cost and the time, once that downstream work is counted?",
                    "What happens if the change is refused, or simply left undecided?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Who decides, and where it is written",
                prompts=(
                    "Who is the change authority for a change this size, by name?",
                    "By when is the decision needed, and what happens to the work in the meantime?",
                    "Which tool holds the request, and where does the new plan version live?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before the decision is recorded",
                prompts=(
                    "The request is written down, with the date it was raised.",
                    "The impact covers the work downstream, not only the task the requester named.",
                    "The decision names a person, not a committee in general.",
                    "A refused or withdrawn request is kept, with the reasoning that closed it.",
                    "Everyone who reads the plan has been told a new version exists.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A logged request carrying its assessed impact and the decision made on it.",
            "A new plan version, kept alongside the one it supersedes rather than replacing it.",
            "A record of what was asked for and refused, not only of what was approved.",
        ),
    ),
    Worksheet(
        key="information_management",
        title="Information management worksheet",
        purpose=(
            "Give each fact the project keeps re-answering one findable home, one owner and a "
            "refresh habit, so looking it up beats asking around."
        ),
        sections=(
            WorksheetSection(
                heading="The fact and its home",
                prompts=(
                    "Which fact does this project keep answering from memory, or by searching?",
                    "Where will the one current copy of it live, and who can reach that place?",
                    "Is it structured enough to be a record with fields, or is it prose?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Owner and refresh",
                prompts=(
                    "Who updates it, and how often?",
                    "What tells a reader the copy in front of them is the current one?",
                    "What happens to the old version when it is replaced?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before calling it managed",
                prompts=(
                    "Something downstream actually reads this record.",
                    "There is one home for it, not a copy per person.",
                    "A superseded version is replaced openly, rather than edited in place.",
                    "No figure here is also typed somewhere else by hand.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A named home, owner and refresh cadence for one category of project information.",
            "A record whatever needs it downstream can actually read.",
        ),
    ),
    Worksheet(
        key="knowledge_management",
        title="Knowledge management worksheet",
        purpose=(
            "Plan how know-how moves from the person who holds it to the person who will need "
            "it, while both are still on the project."
        ),
        sections=(
            WorksheetSection(
                heading="Who holds what",
                prompts=(
                    "Who here has judgment nobody else on the project has, and about what?",
                    "Who will need that judgment, and roughly when?",
                    "Which recent decision would a later reader misjudge knowing only its outcome?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="How it moves",
                prompts=(
                    "What standing habit puts those two people in the same conversation?",
                    "Where are lessons written down as they happen, and who opens that page?",
                    "What would a successor need walked through, beyond the documents left behind?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before anyone rolls off",
                prompts=(
                    "Lessons are captured as they happen, not saved for the closing meeting.",
                    "Each one carries the reasoning behind the call, not only what was decided.",
                    "The page is attached to work it should inform, not filed and forgotten.",
                    "Someone leaving has walked a successor through the calls they made.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A growing record of lessons that carries the reasoning behind decisions.",
            "A standing habit — pairing, or a short regular review — that keeps knowledge moving.",
        ),
    ),
)
