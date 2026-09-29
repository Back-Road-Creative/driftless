"""The one-line proof: every process, technique, artifact kind and method practice
is reachable, explained, launchable (or honestly excused), and crosswalked.

Pure and store-free, like ``pmbok.support`` and ``pmbok.graph`` before it — every fact
here is a property of the product's registries, not of any one project's history, so
it takes no session, no project and no as-of date. Nothing here re-derives a rule a
totality test already owns; it reads the same live registries those tests read
(``tt.py``, ``artifacts.py``, ``reasons.py``, ``methods.py``, ``crosswalk.py``,
``tailoring.py``, ``assess.model``, ``wizard.cli``) and reports the
same four gap shapes those tests assert are empty, in one place a reader (or a script)
can ask without stitching together eight imports first.

Four categories, one predicate each, always the counter-example:

* **orphan** — a catalog member no process, and no honest exemption, ever names.
* **unexplained** — a registry member with no plain-language summary.
* **unlaunchable** — a technique or artifact kind with neither a launcher nor a
  documented reason it cannot have one.
* **uncrosswalked** — a Scrum/Kanban practice, an agile model, or a Monitoring &
  Controlling process a tailoring profile leaves unmapped, with no PMBOK reading
  and no reason it lacks one.

A fifth fact rides beside the four gap shapes rather than inside them:
``skipped_processes`` — every process ``wizard.engine.next_step`` would pass over
entirely. Since every catalog process now resolves to a ``form``, ``derived`` or
``reference`` step (``WizardStep.kind`` — no process is ever a dead end any more),
``next_step``'s only remaining skip clause is ``not state.is_assessable(process)``, a
static fact about the catalog this module can read without a store. It is asserted
EMPTY, exactly like the other four counts:
``tests/test_totality_proof.py`` reuses ``tests/test_wizard_totality.py``'s own
lifecycle-order/waive strategy, by import, to prove that live claim against a real
session rather than trusting the static one alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from driftless.assess.model import ASSISTANT_ROUTES
from driftless.pmbok import catalog, crosswalk, state, tailoring
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.artifacts import ARTIFACT_KINDS, COMPONENT_OF
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.methods import METHODS
from driftless.pmbok.model import ProcessGroup
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS
from driftless.pmbok.reasons import GUIDE_ONLY_REASONS, UNTRACKED_REASONS
from driftless.pmbok.tt import EXTENSIONS, TT_CATALOG
from driftless.wizard.cli import producible_kinds


@dataclass(frozen=True)
class GapShape:
    """One gap shape as a reader meets it: the :class:`Proof` member it counts,
    the heading it is listed under, and what a count above zero would mean."""

    field: str
    label: str
    explanation: str


@dataclass(frozen=True)
class Proof:
    """Named counts plus the offending members, for each of the four gap shapes."""

    orphan_techniques: tuple[str, ...] = ()
    orphan_artifacts: tuple[str, ...] = ()
    orphan_method_practices: tuple[str, ...] = ()

    unexplained_processes: tuple[str, ...] = ()
    unexplained_techniques: tuple[str, ...] = ()
    unexplained_artifacts: tuple[str, ...] = ()

    unlaunchable_techniques: tuple[str, ...] = ()
    unlaunchable_artifacts: tuple[str, ...] = ()

    uncrosswalked_method_practices: tuple[str, ...] = ()
    uncrosswalked_agile_models: tuple[str, ...] = ()
    uncrosswalked_tailoring_gaps: tuple[str, ...] = ()

    skipped_processes: tuple[str, ...] = ()

    def gaps(self) -> tuple[tuple[GapShape, tuple[str, ...]], ...]:
        """Every gap shape paired with its own offending members, in the order
        ``GAP_SHAPES`` lists them -- the one walk the page and the command both
        render, so neither can name a shape the other does not."""
        return tuple((shape, getattr(self, shape.field)) for shape in GAP_SHAPES)

    @property
    def orphan_count(self) -> int:
        return (
            len(self.orphan_techniques)
            + len(self.orphan_artifacts)
            + len(self.orphan_method_practices)
        )

    @property
    def unexplained_count(self) -> int:
        return (
            len(self.unexplained_processes)
            + len(self.unexplained_techniques)
            + len(self.unexplained_artifacts)
        )

    @property
    def unlaunchable_count(self) -> int:
        return len(self.unlaunchable_techniques) + len(self.unlaunchable_artifacts)

    @property
    def uncrosswalked_count(self) -> int:
        return (
            len(self.uncrosswalked_method_practices)
            + len(self.uncrosswalked_agile_models)
            + len(self.uncrosswalked_tailoring_gaps)
        )

    @property
    def total_gaps(self) -> int:
        """Every count that must be zero for the proof to hold — ``skipped_processes``
        included now that ``next_step`` never has a documented reason to skip one."""
        return (
            self.orphan_count
            + self.unexplained_count
            + self.unlaunchable_count
            + self.uncrosswalked_count
            + len(self.skipped_processes)
        )

    @property
    def is_total(self) -> bool:
        """Whether every process, technique, artifact and practice is accounted for."""
        return self.total_gaps == 0


#: Every member of :class:`Proof`, in declaration order, worded for a reader who
#: has met none of the registries behind it. ``tests/test_totality_proof.py``
#: pins this set to the dataclass field by field, so a count added there cannot
#: reach the page or the command as a bare label nobody explained.
GAP_SHAPES: tuple[GapShape, ...] = (
    GapShape(
        "orphan_techniques",
        "Orphan techniques",
        "Techniques no process lists among its tools, and that are not marked as deliberate "
        "extensions. Anything here is a technique nothing in the method would ever lead a "
        "reader to.",
    ),
    GapShape(
        "orphan_artifacts",
        "Orphan artifact kinds",
        "Document kinds no process takes in or produces, and that are not part of a larger "
        "document that is used — whether the store can save one back is a separate question. "
        "Anything here is a document the method never asks for.",
    ),
    GapShape(
        "orphan_method_practices",
        "Orphan method practices",
        "Scrum and Kanban practices whose recorded reading points at a process or technique "
        "that does not exist. Anything here is a practice pointing readers toward something "
        "the method never defined.",
    ),
    GapShape(
        "unexplained_processes",
        "Unexplained processes",
        "Processes whose plain-language summary is blank. Anything here is a process a reader "
        "meets with nothing but its name and number.",
    ),
    GapShape(
        "unexplained_techniques",
        "Unexplained techniques",
        "Techniques whose one-sentence summary is blank. Anything here is a technique page that "
        "opens with no plain words about what the technique is for.",
    ),
    GapShape(
        "unexplained_artifacts",
        "Unexplained artifact kinds",
        "Document kinds whose plain-language summary is blank. Anything here is a document the "
        "method names but never says anything about.",
    ),
    GapShape(
        "unlaunchable_techniques",
        "Unlaunchable techniques",
        "Techniques with neither a page that walks you through them nor a recorded reason they "
        "can only be read about. Anything here is a technique the product offers no way to "
        "start.",
    ),
    GapShape(
        "unlaunchable_artifacts",
        "Unlaunchable artifact kinds",
        "Document kinds the guided walkthrough cannot produce and that carry no recorded reason "
        "they are not tracked. Anything here is a document the method asks for but gives no way "
        "to make.",
    ),
    GapShape(
        "uncrosswalked_method_practices",
        "Uncrosswalked method practices",
        "Scrum and Kanban practices with no reading recorded against the standard process they "
        "stand in for, and no note saying why. Anything here is a practice a team could not "
        "trace back to the wider method.",
    ),
    GapShape(
        "uncrosswalked_agile_models",
        "Uncrosswalked agile models",
        "Kinds of agile record the product stores that nothing ties to the standard vocabulary "
        "and that are not listed as having no equivalent. Anything here is stored data the "
        "method cannot account for.",
    ),
    GapShape(
        "uncrosswalked_tailoring_gaps",
        "Uncrosswalked tailoring gaps",
        "Pairs of a tailoring profile and a monitoring process that profile leaves out. Anything "
        "here is a profile that would quietly stop watching part of the work.",
    ),
    GapShape(
        "skipped_processes",
        "Skipped processes",
        "Processes the guided walkthrough would pass over entirely, because nothing recorded "
        "about them can be judged. Anything here is a process the walkthrough would never offer "
        "as a next step.",
    ),
)


def _orphan_techniques() -> tuple[str, ...]:
    referenced = {t for p in catalog.PROCESSES for t in p.tools_techniques}
    return tuple(sorted(TT_CATALOG - referenced - EXTENSIONS))


def _orphan_artifacts() -> tuple[str, ...]:
    """An artifact kind no process names as an input or output, and is not a named
    component of a kind that IS named (the WBS inside the scope baseline —
    ``artifacts.COMPONENT_OF``, the graph's ``part_of`` tie): a component reaches
    the method through its whole, so it is not orphaned even though no process
    lists it by name.

    Whether the STORE can resolve a kind (``mapping.is_tracked`` /
    ``UNTRACKED_DISPOSITIONS``) is a different question from whether any PROCESS
    names it as an input or output, so a tracked-versus-untracked disposition is
    never consulted here — it answers "can the store read this back", not "does
    the method ask for it", and cannot excuse a kind from this check."""
    referenced = {a for p in catalog.PROCESSES for a in (*p.inputs, *p.outputs)}
    referenced |= {part for part, whole in COMPONENT_OF.items() if whole in referenced}
    return tuple(sorted(ARTIFACT_KINDS - referenced))


def _uncrosswalked_method_practices() -> tuple[str, ...]:
    return tuple(
        f"{method_key}:{practice.key}"
        for method_key, profile in sorted(METHODS.items())
        for practice in profile.practices
        if not practice.crosswalk and not practice.crosswalk_reason
    )


def _orphan_method_practices() -> tuple[str, ...]:
    """A practice whose ``crosswalk`` names an id that is neither a real
    process nor a real technique -- a DANGLING crosswalk, not the same check
    as ``_uncrosswalked_method_practices`` (that one flags an EMPTY crosswalk
    with no excuse). ``methods.Practice.crosswalk`` may name either a PMBOK
    process id or a ``TT_CATALOG`` key (see ``methods.py``'s own module
    docstring), so both sets count as real here, exactly as
    ``tests/test_methods.py::test_every_crosswalk_entry_names_a_real_process_
    or_technique`` already checks at the registry's own level."""
    process_ids = {p.id for p in catalog.PROCESSES}
    return tuple(
        f"{method_key}:{practice.key}"
        for method_key, profile in sorted(METHODS.items())
        for practice in profile.practices
        if any(entry not in process_ids and entry not in TT_CATALOG for entry in practice.crosswalk)
    )


def _unexplained_processes() -> tuple[str, ...]:
    return tuple(
        pid for pid, d in sorted(PROCESS_DEFINITIONS.items()) if not d.plain_summary.strip()
    )


def _unexplained_techniques() -> tuple[str, ...]:
    return tuple(key for key, d in sorted(TECHNIQUES.items()) if not d.summary.strip())


def _unexplained_artifacts() -> tuple[str, ...]:
    return tuple(key for key, d in sorted(ARTIFACTS.items()) if not d.plain_summary.strip())


def _unlaunchable_techniques() -> tuple[str, ...]:
    return tuple(sorted(TT_CATALOG - set(ASSISTANT_ROUTES) - set(GUIDE_ONLY_REASONS)))


def _unlaunchable_artifacts() -> tuple[str, ...]:
    offered = frozenset(producible_kinds())
    return tuple(sorted(ARTIFACT_KINDS - offered - set(UNTRACKED_REASONS)))


def _uncrosswalked_agile_models() -> tuple[str, ...]:
    from driftless.models import agile as agile_models

    mapped = {
        value
        for value in vars(agile_models).values()
        if isinstance(value, type)
        and getattr(value, "__module__", "") == agile_models.__name__
        and hasattr(value, "__tablename__")
    }
    named = crosswalk.NAMED_MODELS | set(crosswalk.NO_EQUIVALENCE)
    return tuple(sorted(model.__name__ for model in mapped - named))


def _uncrosswalked_tailoring_gaps() -> tuple[str, ...]:
    """Every (profile, process) pair a Monitoring & Controlling process is missing
    from — ``tailoring.PROFILES`` is built to cover all of them by construction
    (``tests/test_pmbok_tailoring.py`` pins the totality), so this is always empty
    on a tree where that invariant holds; it is walked rather than trusted so a
    future profile that drops a process fails here too, not only in that suite."""
    mc_ids = {p.id for p in catalog.by_group(ProcessGroup.MONITORING)}
    gaps = []
    for key, profile in sorted(tailoring.PROFILES.items()):
        covered = {control.process_id for control in profile.controls}
        for missing in sorted(mc_ids - covered):
            gaps.append(f"{key}:{missing}")
    return tuple(gaps)


def _skipped_processes() -> tuple[str, ...]:
    """Every process ``next_step`` would still pass over entirely: not
    store-assessable at all — the one skip clause left in ``wizard.engine.
    next_step`` now that a process with no producible output is a ``derived`` or
    ``reference`` step instead of being skipped as a dead end."""
    return tuple(p.id for p in catalog.PROCESSES if not state.is_assessable(p))


def build_proof() -> Proof:
    """Walk every registry once and report the whole totality proof."""
    return Proof(
        orphan_techniques=_orphan_techniques(),
        orphan_artifacts=_orphan_artifacts(),
        orphan_method_practices=_orphan_method_practices(),
        unexplained_processes=_unexplained_processes(),
        unexplained_techniques=_unexplained_techniques(),
        unexplained_artifacts=_unexplained_artifacts(),
        unlaunchable_techniques=_unlaunchable_techniques(),
        unlaunchable_artifacts=_unlaunchable_artifacts(),
        uncrosswalked_method_practices=_uncrosswalked_method_practices(),
        uncrosswalked_agile_models=_uncrosswalked_agile_models(),
        uncrosswalked_tailoring_gaps=_uncrosswalked_tailoring_gaps(),
        skipped_processes=_skipped_processes(),
    )
