"""Worksheets for the schedule family's guide-only techniques. Rolling wave
planning is a schedule technique whose worksheet sits in
``worksheets_general.py``; it is left there rather than moved under an open
sibling change."""

from __future__ import annotations

from driftless.pmbok.worksheets import Worksheet, WorksheetSection

ENTRIES: tuple[Worksheet, ...] = (
    Worksheet(
        key="dependency_determination",
        title="Dependency review worksheet",
        purpose="Sort each link between tasks into the ones the work forces and the ones chosen.",
        sections=(
            WorksheetSection(
                heading="Link by link",
                prompts=(
                    "For each link, what breaks if the two tasks run the other way round?",
                    "Is that a fact of the work, or a habit the team picked?",
                    "Does the link wait on anyone outside the team, and who?",
                ),
                kind="text",
            ),
            WorksheetSection(
                heading="When the plan has to get shorter",
                prompts=(
                    "Every link is marked forced or chosen, inside or outside the team.",
                    "The chosen links were re-read for ones worth overlapping.",
                ),
                kind="check",
            ),
        ),
        outputs=("Every link marked forced or chosen, with the chosen ones listed first.",),
    ),
)
