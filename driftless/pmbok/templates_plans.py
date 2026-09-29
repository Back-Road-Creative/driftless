"""Printable templates for the plans family (``artifacts.FAMILIES["plans"]``).

One ``Template`` per kind: the sections and fields that document really holds, a
line of guidance per field, and the record a filled-in copy is read back from.
Every kind here is a subsidiary management plan (``mapping.SUBSIDIARY_PLANS``), so
each has a stored body; the ones still to write are named in the test module.
"""

from __future__ import annotations

from driftless.pmbok.worksheets import Template, TemplateField, TemplateSection


def _s(heading: str, *fields: tuple[str, str]) -> TemplateSection:
    return TemplateSection(heading, tuple(TemplateField(*field) for field in fields))


#: What a filled-in copy is read back from: the prose body the store keeps per plan.
_PROSE = "the written plan stored on this project"

ENTRIES: tuple[Template, ...] = (
    Template(
        key="scope_management_plan",
        sections=(
            _s(
                "Setting the scope",
                ("How the scope statement is written", "Say who drafts it and what it covers."),
                ("How the work is broken down", "Say how far the deliverable tree goes."),
            ),
            _s("Holding it", ("How a change is approved", "Name who signs one off.")),
        ),
        filled_from=_PROSE,
    ),
    Template(
        key="schedule_management_plan",
        sections=(
            _s(
                "Building the timeline",
                ("How work is split into activities", "Say how small a piece of work gets."),
                ("How long each piece will take", "Say where the estimate comes from."),
            ),
            _s("Holding dates", ("How a date change is approved", "Name who can move one.")),
        ),
        filled_from=_PROSE,
    ),
    Template(
        key="cost_management_plan",
        sections=(
            _s(
                "Setting the budget",
                ("How costs are estimated", "Say what the figures are built from."),
                ("How the budget is put together", "Say how estimates roll up into one."),
            ),
            _s("Watching spend", ("What gap forces a response", "Give the size of miss.")),
        ),
        filled_from=_PROSE,
    ),
    Template(
        key="quality_management_plan",
        sections=(
            _s(
                "What good work means here",
                ("The standards this work must meet", "Name them, or say who sets them."),
                ("How quality is measured", "Say what gets measured, and how often."),
            ),
            _s("Checking it", ("What happens when a check fails", "Say who is told.")),
        ),
        filled_from=_PROSE,
    ),
)
