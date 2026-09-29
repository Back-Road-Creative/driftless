"""Coverage as a property of the tree: every ``ARTIFACT_KINDS`` member is
explained in plain language, walked one by one rather than sampled.

The list of explanation fields is *derived* from ``ArtifactContent``'s own
dataclass fields rather than restated, so a field added to the content record
is required of every kind in the catalog the moment it exists — there is no
second list to keep in sync.

The plain-language gate lives here too: ``plain_summary`` must read as one
sentence, twenty-five words or fewer, and carry none of the acronyms or
snake_case identifiers this whole registry otherwise traffics in — a person
who has never heard of project management has to be able to follow it.
"""

from __future__ import annotations

from dataclasses import fields

from driftless.pmbok import plain_language as pl
from driftless.pmbok.artifact_content import ArtifactContent
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.glossary import GLOSSARY

#: Every ``ArtifactContent`` field, read off the dataclass itself.
EXPLANATION_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(ArtifactContent))


def test_the_fields_being_walked_were_actually_derived() -> None:
    """Guards the derivation above: were it to yield nothing, every totality
    test below would pass vacuously over an empty field list."""
    assert EXPLANATION_FIELDS
    assert ARTIFACTS


def test_every_artifact_is_explained_in_every_content_field() -> None:
    gaps: list[str] = []
    for key, definition in sorted(ARTIFACTS.items()):
        for name in EXPLANATION_FIELDS:
            value = getattr(definition, name)
            if not value.strip():
                gaps.append(f"{key}.{name} is blank")
    assert not gaps, (
        "every artifact kind must be explained; write content for these in the "
        "matching driftless/pmbok/artifact_content/<family>.py module:\n" + "\n".join(gaps)
    )


def test_every_artifact_has_the_derived_process_and_tracking_facts() -> None:
    """``produced_by``/``read_by``/``tracked_by`` are computed, never typed —
    this only guards that the computation actually ran and left something to
    show, not any particular value."""
    for key, definition in sorted(ARTIFACTS.items()):
        assert isinstance(definition.produced_by, tuple)
        assert isinstance(definition.read_by, tuple)
        assert isinstance(definition.tracked_by, bool)


def test_every_plain_summary_is_one_short_jargon_free_sentence() -> None:
    glossary_keys = frozenset(GLOSSARY)
    violations: list[str] = []
    for key, definition in sorted(ARTIFACTS.items()):
        violations.extend(
            f"{key}: {violation}"
            for violation in pl.violations(definition.plain_summary, glossary_keys=glossary_keys)
        )
    assert not violations, (
        "plain_summary must be one short sentence a newcomer can follow, with no "
        "acronyms and no raw identifiers:\n" + "\n".join(violations)
    )
