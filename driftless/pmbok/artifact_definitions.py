"""``ARTIFACTS``: the artifact-kind registry, one ``ArtifactDefinition`` per member
of ``driftless.pmbok.artifacts.ARTIFACT_KINDS``. Adding a kind to a family in
``artifacts.py`` automatically gives it a definition here; there is no second
list to update.

The identity fields — ``key``, ``display_name`` and ``family`` — are populated
by this module directly, for every catalog member. ``display_name`` is
``driftless.naming.humanize`` called on the key, with ``_DISPLAY_NAME_OVERRIDES``
naming the few terms of art that rule gets wrong; the rule itself is never
restated here. The plain-language explanation fields come from
``driftless.pmbok.artifact_content``, which composes them out of one module per
family — see that package's docstring. Every catalog member has content today,
and ``tests/test_artifact_totality.py`` walks the whole catalog and fails on the
first key and field that does not; structurally, though, a key no content
module claims still gets an ``ArtifactDefinition`` with those fields empty, so
a kind added to ``artifacts.py`` appears here immediately and is caught there
rather than crashing a page.

``produced_by`` and ``read_by`` are never typed by hand: they are derived by
walking ``driftless.pmbok.catalog.PROCESSES`` for every process naming this
kind in its ``outputs`` or ``inputs``, so a process's ITTO table is the one
place that fact can drift from. ``tracked_by`` is likewise derived, from
``driftless.pmbok.mapping.is_tracked`` — the resolver table that already
partitions ``ARTIFACT_KINDS`` into what the store can answer for and what it
cannot — so "not tracked" here is a computed fact, not a claim this module
could get out of step with the resolver it describes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from driftless.naming import humanize
from driftless.pmbok.artifact_content import ArtifactContent, collect_content
from driftless.pmbok.artifacts import ARTIFACT_KINDS, FAMILIES
from driftless.pmbok.catalog import PROCESSES
from driftless.pmbok.mapping import is_tracked


class ArtifactFamily(str, Enum):
    """The artifact-kind groupings ``artifacts.py``'s ``FAMILIES`` names
    directly — one member here per key there, which
    ``tests/test_artifact_definitions.py`` walks."""

    PLANS = "plans"
    BASELINES = "baselines"
    DOCUMENTS = "documents"
    PERFORMANCE = "performance"
    PROCUREMENT = "procurement"
    DELIVERABLES = "deliverables"
    CHANGES = "changes"
    ENVIRONMENT = "environment"


@dataclass(frozen=True)
class ArtifactDefinition:
    """One artifact kind's identity plus its plain-language explanation and
    its derived process/tracking facts."""

    key: str
    display_name: str
    family: ArtifactFamily
    plain_summary: str = ""
    why_it_matters: str = ""
    what_it_looks_like_here: str = ""
    produced_by: tuple[str, ...] = ()
    read_by: tuple[str, ...] = ()
    tracked_by: bool = False


#: The keys ``driftless.naming.humanize`` gets wrong, and what they should read
#: as. That rule is title-case over the words of a snake_case key, which
#: mishandles a couple of PMBOK terms of art. Every other key takes the rule
#: unaltered — so this table is the exception list, never a second naming
#: scheme.
_DISPLAY_NAME_OVERRIDES = {
    "work_breakdown_structure": "Work Breakdown Structure (WBS)",
}


def _display_name(key: str) -> str:
    """This artifact kind's visible name: the one word-shaping rule, unless
    this key is one of the few the rule gets wrong."""
    return _DISPLAY_NAME_OVERRIDES.get(key, humanize(key))


#: Explanation content, keyed by artifact kind, composed from every family
#: content module ``artifact_content`` can discover. A key absent here (no
#: content module has claimed it yet) yields an all-empty ``ArtifactContent``.
_CONTENT: dict[str, ArtifactContent] = collect_content()

_EMPTY_CONTENT = ArtifactContent()


def _produced_by(key: str) -> tuple[str, ...]:
    """Every process id that names ``key`` in its ``outputs`` — the closed set
    of processes that can raise this artifact, read off the ITTO table itself
    rather than typed a second time here."""
    return tuple(process.id for process in PROCESSES if key in process.outputs)


def _read_by(key: str) -> tuple[str, ...]:
    """Every process id that names ``key`` in its ``inputs`` — the closed set
    of processes that consume this artifact, read off the ITTO table itself."""
    return tuple(process.id for process in PROCESSES if key in process.inputs)


def _definition(key: str, family: str) -> ArtifactDefinition:
    content = _CONTENT.get(key, _EMPTY_CONTENT)
    return ArtifactDefinition(
        key=key,
        display_name=_display_name(key),
        family=ArtifactFamily(family),
        plain_summary=content.plain_summary,
        why_it_matters=content.why_it_matters,
        what_it_looks_like_here=content.what_it_looks_like_here,
        produced_by=_produced_by(key),
        read_by=_read_by(key),
        tracked_by=is_tracked(key),
    )


#: One entry per ``ARTIFACT_KINDS`` member, keyed by that member's name.
ARTIFACTS: dict[str, ArtifactDefinition] = {
    key: _definition(key, family) for family, keys in FAMILIES.items() for key in keys
}

assert set(ARTIFACTS) == ARTIFACT_KINDS  # FAMILIES partitions ARTIFACT_KINDS; belt and braces.
