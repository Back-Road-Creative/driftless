"""Support coverage: how much of the methodology the product can actually help with.

``definitions.TECHNIQUES`` gives every technique an identity, an ``assistance_mode``
it will eventually offer, and its written explanation, composed in from one module
per family under ``technique_content``. ``catalog.PROCESSES`` gives every process its techniques
and outputs. Neither answers "how much of this do we support, and where are the
holes?" — this module does, by walking both and adding two facts already computed
elsewhere: ``state.is_assessable`` (whether the store can judge a process at all)
and the same producible/output intersection ``wizard.engine._producible`` uses (via
the public ``wizard.cli.producible_kinds`` registry, since a private name cannot be
imported across a module boundary here — ``tests/test_package.py`` enforces that).

Store-independent and clock-free by construction: nothing here takes a session, a
project or an as-of date, because a technique's explanation and a process's
producibility are properties of the product, not of any one project's history. A
process with no producible output is a hole — the wizard can walk to it but has
nothing to offer there. A technique with no explanation would be a hole too — named
and placed in the catalog, but silent on how to use it. There are none left: every
catalog member is explained, and ``tests/test_technique_totality.py`` fails the
moment one ships that is not. This module keeps counting them anyway, because the
count is what makes that a measured fact rather than a remembered one, and because
the next technique added to ``tt.py`` starts out being exactly that hole.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from driftless.assess.model import ASSISTANT_ROUTES
from driftless.pmbok import catalog, state
from driftless.pmbok.definitions import TECHNIQUES, AssistanceMode, TechniqueDefinition
from driftless.pmbok.model import KnowledgeArea, Process
from driftless.wizard.cli import producible_kinds


@dataclass(frozen=True)
class TechniqueCoverage:
    """One technique's support tier: explained yet, and what it will eventually offer."""

    key: str
    display_name: str
    explained: bool
    assistance_mode: AssistanceMode


@dataclass(frozen=True)
class ProcessCoverage:
    """One process's techniques and whether the wizard can produce any of its outputs."""

    process_id: str
    process_name: str
    area: KnowledgeArea
    assessable: bool
    producible_outputs: tuple[str, ...]
    techniques: tuple[TechniqueCoverage, ...]

    @property
    def has_producible_output(self) -> bool:
        """Whether the wizard can produce at least one of this process's outputs."""
        return bool(self.producible_outputs)


@dataclass(frozen=True)
class CoverageSummary:
    """Store-wide (project-independent) totals over every catalog process."""

    processes: tuple[ProcessCoverage, ...]
    technique_count: int
    explained_technique_count: int
    process_count: int
    assessable_process_count: int
    producible_process_count: int


def technique_coverage(definition: TechniqueDefinition) -> TechniqueCoverage:
    """One technique's coverage: a non-empty ``summary`` is what "explained" means —
    the primary explanation field a technique's family content module supplies."""
    return TechniqueCoverage(
        key=definition.key,
        display_name=definition.display_name,
        explained=bool(definition.summary),
        assistance_mode=definition.assistance_mode,
    )


def _producible_outputs(process: Process, offered: frozenset[str]) -> tuple[str, ...]:
    """The process's outputs the wizard can actually make — mirrors
    ``wizard.engine._producible``'s one-line intersection exactly, over the same
    canonical registry (``wizard.cli.producible_kinds``), because that private
    helper cannot be imported here (see the module docstring). This is a copied
    rule, not a shared one:
    ``tests/test_pmbok_support.py::test_producible_outputs_agrees_with_the_wizards_own_rule``
    pins the two in lockstep across every catalog process, so a future condition
    added to ``_producible`` fails loudly here instead of silently going stale."""
    return tuple(kind for kind in process.outputs if kind in offered)


def process_coverage(
    process: Process,
    *,
    registry: Mapping[str, TechniqueDefinition] = TECHNIQUES,
    producible: Callable[[], tuple[str, ...]] = producible_kinds,
) -> ProcessCoverage:
    """One process's coverage: reuses ``state.is_assessable`` for assessability rather
    than re-deriving which outputs count — the single rule ``state.excluded_from_completeness``
    documents as the one every completeness consumer calls."""
    offered = frozenset(producible())
    return ProcessCoverage(
        process_id=process.id,
        process_name=process.name,
        area=process.area,
        assessable=state.is_assessable(process),
        producible_outputs=_producible_outputs(process, offered),
        techniques=tuple(technique_coverage(registry[key]) for key in process.tools_techniques),
    )


def build_coverage(
    *,
    processes: Sequence[Process] = catalog.PROCESSES,
    registry: Mapping[str, TechniqueDefinition] = TECHNIQUES,
    producible: Callable[[], tuple[str, ...]] = producible_kinds,
) -> CoverageSummary:
    """Every catalog process's coverage, plus the store-wide totals over it."""
    rows = tuple(
        process_coverage(process, registry=registry, producible=producible) for process in processes
    )
    explained = sum(1 for definition in registry.values() if definition.summary)
    return CoverageSummary(
        processes=rows,
        technique_count=len(registry),
        explained_technique_count=explained,
        process_count=len(rows),
        assessable_process_count=sum(1 for row in rows if row.assessable),
        producible_process_count=sum(1 for row in rows if row.has_producible_output),
    )


@dataclass(frozen=True)
class HelpFact:
    """One way driftless already helps run a process: ``kind="technique"``
    means one of its ``tools_techniques`` has an ``ASSISTANT_ROUTES`` entry;
    ``kind="output"`` means the wizard can already produce one of its
    ``outputs``. ``key`` is the ``TT_CATALOG``/``ARTIFACT_KINDS`` member —
    never a route string — so a renderer looks up its own name and address."""

    kind: Literal["technique", "output"]
    key: str


def driftless_help(
    process: Process,
    *,
    routes: Mapping[str, str] = ASSISTANT_ROUTES,
    producible: Callable[[], tuple[str, ...]] = producible_kinds,
) -> tuple[HelpFact, ...]:
    """How driftless already helps run ``process``, from two joins rather
    than text typed per process: its techniques against ``ASSISTANT_ROUTES``,
    and its outputs against the wizard's producible kinds. Empty when neither
    join finds anything, for a caller to render as one honest line."""
    technique_facts = tuple(
        HelpFact("technique", key)
        for key in dict.fromkeys(process.tools_techniques)
        if key in routes
    )
    offered = frozenset(producible())
    output_facts = tuple(HelpFact("output", kind) for kind in process.outputs if kind in offered)
    return technique_facts + output_facts
