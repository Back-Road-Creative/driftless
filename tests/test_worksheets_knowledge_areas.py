"""Totality for the knowledge-area worksheets: every guide-only technique of
the families below carries a printable worksheet, walked from the registries
rather than from a typed list, so a technique with no assistant is answered
rather than left blank. Integration is not among them yet, and the
catalogue-wide version of this check belongs to the change that finishes the
remaining families."""

from __future__ import annotations

from driftless.pmbok import plain_language as pl
from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
from driftless.pmbok.tt import FAMILIES
from driftless.pmbok.worksheets import WORKSHEETS

#: The technique families whose guide-only members are covered here.
COVERED_FAMILIES = ("scope", "schedule", "cost", "quality", "resource")


def _guide_only_keys() -> frozenset[str]:
    """Every guide-only technique of the covered families, derived."""
    members = frozenset[str]().union(*(FAMILIES[family] for family in COVERED_FAMILIES))
    return members & frozenset(GUIDE_ONLY_REASONS)


def test_the_families_being_walked_really_hold_guide_only_techniques() -> None:
    """Guards the derivation: were it to yield nothing, the checks below would
    pass over an empty key set."""
    assert set(COVERED_FAMILIES) <= set(FAMILIES)
    assert _guide_only_keys()


def test_every_guide_only_technique_in_these_families_has_a_worksheet() -> None:
    missing = sorted(_guide_only_keys() - set(WORKSHEETS))
    assert not missing, (
        f"{missing} have no assistant and no worksheet either — write one in the "
        "matching driftless/pmbok/worksheets_<family>.py module"
    )


def test_each_worksheet_asks_something_a_person_could_answer_in_a_room() -> None:
    flaws: list[str] = []
    for key in sorted(_guide_only_keys() & set(WORKSHEETS)):
        sheet = WORKSHEETS[key]
        if not (sheet.title.strip() and sheet.purpose.strip() and sheet.outputs and sheet.sections):
            flaws.append(f"{key}: title, purpose, sections and outputs are all required")
        for section in sheet.sections:
            if not (section.heading.strip() and section.prompts):
                flaws.append(f"{key}: a section needs a heading and at least one prompt")
            flaws += [
                f"{key}: {prompt!r} leaks a raw identifier or is an unfinished line"
                for prompt in section.prompts
                if pl.snake_identifiers(prompt) or not prompt.rstrip().endswith((".", "?"))
            ]
    assert not flaws, "\n".join(flaws)
