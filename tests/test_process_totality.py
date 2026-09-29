"""Coverage as a property of the tree: every ``catalog.PROCESSES`` member is
explained in plain words, walked one by one rather than sampled — mirroring
``tests/test_technique_totality.py``.

These tests also pin the plain-language gate the plan calls for:
``plain_summary`` is one sentence, at most 25 words, and free of snake_case
keys and shouting acronyms; the other three fields are one to three sentences
each. "No jargon" beyond that is a writing discipline this suite cannot
mechanically check, so it is not asserted here.

The set of processes walked is *derived* from ``catalog.PROCESSES`` rather
than a literal count, so the totality checks stay meaningful as the catalog
changes instead of quietly passing over a stale number.
"""

from __future__ import annotations

import re
from dataclasses import fields

from driftless.pmbok import catalog
from driftless.pmbok import plain_language as pl
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.model import KnowledgeArea
from driftless.pmbok.process_content import ProcessContent
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS

#: ``worked_example``/``pitfalls`` are walked by their own scoped test below
#: instead, over ``DEEPENED_AREAS`` -- which the test at the foot of this file
#: now pins to every area, so that walk skips nothing.
_DEPTH_FIELDS = frozenset({"worked_example", "pitfalls"})
CONTENT_FIELDS: tuple[str, ...] = tuple(
    field.name for field in fields(ProcessContent) if field.name not in _DEPTH_FIELDS
)

#: The areas whose processes carry ``worked_example``/``pitfalls`` today, one
#: per line so two areas being written at once never collide on the same line.
#: An area joins this set in the same change that fills its content module.
DEEPENED_AREAS: frozenset[str] = frozenset(
    {
        "communications",
        "cost",
        "integration",
        "procurement",
        "quality",
        "resource",
        "risk",
        "schedule",
        "scope",
        "stakeholder",
    }
)

#: Sentence-ending punctuation, for the non-summary fields below.
SENTENCE_END = re.compile(r"[.!?]")


def _sentence_count(text: str) -> int:
    return len(SENTENCE_END.findall(text.strip()))


def test_the_fields_being_walked_were_actually_derived() -> None:
    """Guards the derivation above: were it to yield nothing, every totality
    test below would pass vacuously over an empty field list."""
    assert CONTENT_FIELDS
    assert PROCESS_DEFINITIONS
    assert set(PROCESS_DEFINITIONS) == {process.id for process in catalog.PROCESSES}


def test_every_process_is_explained_in_every_content_field() -> None:
    gaps: list[str] = []
    for process_id, definition in sorted(PROCESS_DEFINITIONS.items()):
        for name in CONTENT_FIELDS:
            value = getattr(definition, name)
            if not value.strip():
                gaps.append(f"{process_id}.{name} is blank")
    assert not gaps, (
        "every process must be explained in plain words; write content for these in "
        "the matching driftless/pmbok/process_content/<area>.py module:\n" + "\n".join(gaps)
    )


def test_plain_summary_passes_the_plain_language_gate() -> None:
    glossary_keys = frozenset(GLOSSARY)
    gaps: list[str] = []
    for process_id, definition in sorted(PROCESS_DEFINITIONS.items()):
        gaps.extend(
            f"{process_id}: {violation}"
            for violation in pl.violations(definition.plain_summary, glossary_keys=glossary_keys)
        )
    assert not gaps, (
        "plain_summary must be one short sentence a newcomer can follow, with no "
        "acronyms and no raw identifiers:\n" + "\n".join(gaps)
    )


def test_the_other_three_fields_are_one_to_three_sentences() -> None:
    wrong: dict[str, int] = {}
    for process_id, definition in sorted(PROCESS_DEFINITIONS.items()):
        for name in ("why_bother", "done_when", "first_time_tip"):
            count = _sentence_count(getattr(definition, name))
            if not (1 <= count <= 3):
                wrong[f"{process_id}.{name}"] = count
    assert not wrong, f"why_bother/done_when/first_time_tip must be 1-3 sentences: {wrong}"


def test_deepened_areas_have_a_worked_example_and_pitfalls() -> None:
    """Every process in ``DEEPENED_AREAS`` carries a non-empty ``worked_example``
    and two to four ``pitfalls``. Processes outside these areas are untouched
    here; a change that fills another area's content module widens
    ``DEEPENED_AREAS`` in the same commit."""
    gaps: list[str] = []
    for process in sorted(catalog.PROCESSES, key=lambda p: p.id):
        if process.area.value not in DEEPENED_AREAS:
            continue
        definition = PROCESS_DEFINITIONS[process.id]
        if not definition.worked_example.strip():
            gaps.append(f"{process.id}.worked_example is blank")
        if not (2 <= len(definition.pitfalls) <= 4):
            gaps.append(f"{process.id}.pitfalls needs 2-4 entries, has {len(definition.pitfalls)}")
        gaps.extend(
            f"{process.id}.pitfalls[{i}] is blank"
            for i, pitfall in enumerate(definition.pitfalls)
            if not pitfall.strip()
        )
    assert not gaps, (
        f"every process in {'/'.join(sorted(DEEPENED_AREAS))} needs a worked_example "
        "and 2-4 pitfalls:\n" + "\n".join(gaps)
    )


def test_every_area_is_deepened_so_the_scoped_walk_skips_nothing() -> None:
    """``DEEPENED_AREAS`` was a rollout allowance: the walk above skips any area
    whose content module was not written yet. Every area is written now, so the
    allowance has nothing left to excuse. Pinning it closed is what stops the
    skip outliving its reason -- an eleventh area, or an area dropped from the
    set, fails here instead of passing by being quietly stepped over."""
    assert DEEPENED_AREAS == {area.value for area in KnowledgeArea}
