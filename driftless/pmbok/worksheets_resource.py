"""Worksheets for the resource family's guide-only techniques: two relational
skills no launcher can run, where the help worth giving is preparation before
the conversation rather than a computed answer."""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="influencing",
        title="Influencing worksheet",
        purpose="Plan an ask to someone who does not report to you, before you make it.",
        sections=(
            WorksheetSection(
                heading="Whose help you need",
                prompts=(
                    "Whose cooperation does the plan actually depend on here?",
                    "What does that person get, or avoid, by helping?",
                    "What evidence shows them what saying no costs — a date, a queue?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="Before you ask",
                prompts=(
                    "This is not the first conversation you have ever had with them.",
                    "Anything you promised them last time has been delivered.",
                ),
                kind="check",
            ),
        ),
        outputs=("One named ask per person, the evidence to bring, and what you offer back.",),
    ),
    Worksheet(
        key="negotiation",
        title="Resource negotiation worksheet",
        purpose="Settle what you need, what you can live with and what you can trade first.",
        sections=(
            WorksheetSection(
                heading="Before the conversation",
                prompts=(
                    "Exactly what do you need — whose time, how many hours, which weeks?",
                    "What is the least that still leaves the plan workable?",
                    "What can you offer back: a later start, a shared cost, another person?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="After you agree",
                prompts=(
                    "The other side's own capacity problem was asked about, not assumed.",
                    "The agreed hours and dates are written down and in the plan.",
                ),
                kind="check",
            ),
        ),
        outputs=("Agreed hours and dates in writing, and a plan that matches what was promised.",),
    ),
)
