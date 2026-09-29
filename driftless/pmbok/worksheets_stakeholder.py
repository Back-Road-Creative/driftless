"""Printable worksheets for the stakeholder family's guide-only techniques.

``ground_rules`` is guide-only because the technique IS the kickoff conversation
(``GUIDE_ONLY_REASONS["ground_rules"]``); a sheet the team fills in together is
the most a tool can honestly offer it.
"""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="ground_rules",
        title="Ground rules worksheet",
        purpose="Agree how the team will work together, in words specific enough to enforce.",
        sections=(
            WorksheetSection(
                heading="The rules",
                prompts=(
                    "What behaviour has caused friction before, or is likely to here?",
                    "Write each rule as something a person could be seen doing, or not doing.",
                    "Who speaks up when a rule is broken, and how soon?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before the kickoff ends",
                prompts=(
                    "Every rule came from the team, not handed down for sign-off.",
                    "No rule is so general that nobody could point to a breach.",
                ),
                kind="check",
            ),
        ),
        outputs=("A short list of rules the team agreed, and who holds each one.",),
    ),
)
