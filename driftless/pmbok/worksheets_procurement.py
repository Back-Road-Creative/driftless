"""Printable worksheets for the procurement family's guide-only techniques
(``tt.FAMILIES["procurement"]`` ∩ ``reasons.GUIDE_ONLY_REASONS``).

None of the five has a calculator behind it, and none could honestly get one:
they are a meeting, a market-facing notice, and three judgment calls about a
supplier's work. Driftless also stores nothing to compute them from — the only
procurement record it keeps is one signed ``ProcurementAgreement`` — so a
worksheet a person fills in is the honest shape rather than a stand-in for a
calculation.

Each sheet asks; it does not advise. Where the answer depends on the contract
or on the law, the prompt asks what the agreement says and who confirmed it,
rather than telling the reader what is true of their contract.
"""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="advertising",
        title="Advertising and solicitation notice worksheet",
        purpose="Plan a notice that reaches capable vendors you do not already know.",
        sections=(
            WorksheetSection(
                heading="What you are buying",
                prompts=(
                    "Describe the work in the words a vendor outside your contact list would "
                    "need to judge whether they can do it.",
                    "What must a vendor already hold or be able to do to be worth hearing from?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Where the notice runs",
                prompts=(
                    "Which journals, industry boards or portals does this vendor market read?",
                    "If a public body is buying, what publication rules apply, and who confirmed "
                    "them?",
                    "Who answers questions, and by when must questions arrive?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you publish",
                prompts=(
                    "The purchase is large or specialised enough that unknown vendors are worth "
                    "surfacing.",
                    "The notice describes the work without detail that would advantage whoever "
                    "helped write it.",
                    "The response deadline gives a new vendor time to respond, and says the date.",
                ),
                kind="check",
            ),
        ),
        outputs=("A published notice and the list of vendors who responded to it.",),
    ),
    Worksheet(
        key="bidder_conferences",
        title="Bidder conference agenda worksheet",
        purpose="Run one meeting where every bidder hears the same answers at the same time.",
        sections=(
            WorksheetSection(
                heading="Who is coming",
                prompts=(
                    "Who was invited, and how was every vendor that received the request told?",
                    "Who from your side attends, and which of them answers on scope, and on "
                    "contract terms?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Agenda",
                prompts=(
                    "Who walks through the work, and how long does that take?",
                    "Which parts of the request do you expect the questions to land on?",
                    "How are questions taken — live, in writing, or both — and when do answers go "
                    "out?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Same answers for everyone",
                prompts=(
                    "Every bidder was offered the same session, or a session with the same "
                    "content.",
                    "Questions and answers will be written up and sent to every bidder, including "
                    "those who did not attend.",
                    "Nobody received an answer privately that the others did not get.",
                    "Anything said in the room that changes the request will be reissued in "
                    "writing.",
                ),
                kind="check",
            ),
        ),
        outputs=("An agenda, and one written question-and-answer record sent to every bidder.",),
    ),
    Worksheet(
        key="claims_administration",
        title="Claims log worksheet",
        purpose="Record one disputed change and follow the route the agreement already sets.",
        sections=(
            WorksheetSection(
                heading="The disputed change",
                prompts=(
                    "What work is in dispute, and who asked for it?",
                    "When was it asked for, and is there anything in writing from that time?",
                    "What is being claimed — payment, more time, or something else?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="The route the agreement sets",
                prompts=(
                    "What does the signed agreement say about how disputes are settled?",
                    "Which step of that route are you at now, and what is the next one?",
                    "Who on each side can actually settle this?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Keeping the record",
                prompts=(
                    "The dispute is written down, including anything that began as a verbal "
                    "instruction.",
                    "Both sides have been told in writing that the claim is open.",
                    "The outcome will be recorded against the agreement, not only in "
                    "correspondence.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A dated claim record, and the agreement updated if the outcome changes its terms.",
        ),
    ),
    Worksheet(
        key="inspections_and_audits",
        title="Inspection and audit checklist worksheet",
        purpose="Decide what gets checked on a supplier's work, how often, and against what.",
        sections=(
            WorksheetSection(
                heading="What gets checked",
                prompts=(
                    "Which deliverables can be inspected, and against which stated requirement?",
                    "Which process or compliance obligations need auditing rather than inspecting?",
                    "What would a passing deliverable hide that only an audit would find?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="How often, and by whom",
                prompts=(
                    "How often does each check happen, and who carries it out?",
                    "What access does the checker need, and does the agreement already grant it?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before the first check",
                prompts=(
                    "What is checked, and on what schedule, was settled when the agreement was "
                    "signed.",
                    "Each check names the requirement it tests, not an informal expectation.",
                    "Findings will be recorded against the agreement and followed up through its "
                    "own remedy route.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A dated record of findings tied to the agreement, with the follow-up on each failure.",
        ),
    ),
    Worksheet(
        key="procurement_performance_reviews",
        title="Supplier performance review worksheet",
        purpose="Check one live agreement against its terms at a set interval, and read the trend.",
        sections=(
            WorksheetSection(
                heading="This review",
                prompts=(
                    "What period does this review cover, and what is today's date?",
                    "Against the agreement's terms: what was delivered, what did it cost, and was "
                    "it on time?",
                    "What did the supplier raise that you have not answered?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="The trend",
                prompts=(
                    "What did the previous reviews say, and is this one better, worse or flat?",
                    "What will you raise with the supplier now rather than at the next review?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you close the review",
                prompts=(
                    "The comparison is against the written terms, not a general sense of how it "
                    "is going.",
                    "The review is dated and filed where the earlier ones can be read beside it.",
                    "The review interval matches how long the agreement runs.",
                ),
                kind="check",
            ),
        ),
        outputs=(
            "A dated record of the agreement's cost, schedule and scope performance at this "
            "review point.",
        ),
    ),
)
