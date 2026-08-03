"""The onboarding wizard's pure core: what to do next, and where a project stands.

Walks the process groups in lifecycle order (Initiating → Planning → Executing →
Monitoring → Closing) and, within each, the catalog's processes in order, to find
the next process that is not yet done and that the store can actually help
complete — one with at least one output the wizard can *produce*. For that
process it reports its PMBOK inputs (and whether each input-artifact already
exists), its tools & techniques, and the outputs the wizard can produce.

Pure and as-of-parameterised — it reads the store and the clock-free process-state
engine, never the wall clock — so the same store always yields the same next
step. Writing an output is deliberately *not* here: that goes through the
validated API boundary, in ``driftless.wizard.cli``, so the wizard's read side stays
below the API in the import order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.pmbok import catalog, mapping
from driftless.pmbok import state as st
from driftless.pmbok.model import ProcessGroup

# Lifecycle order the wizard advances through.
_GROUP_ORDER = (
    ProcessGroup.INITIATING,
    ProcessGroup.PLANNING,
    ProcessGroup.EXECUTING,
    ProcessGroup.MONITORING,
    ProcessGroup.CLOSING,
)

_DONE = (st.ProcessState.PRODUCED, st.ProcessState.SIGNED_OFF, st.ProcessState.WAIVED)


@dataclass(frozen=True)
class InputStatus:
    """One PMBOK input of a process and whether it exists in the store."""

    kind: str
    present: bool


@dataclass(frozen=True)
class WizardStep:
    """The next thing to do: a process, its inputs' state, and what to produce."""

    process_id: str
    name: str
    group: str
    area: str
    state: str
    inputs: tuple[InputStatus, ...]
    tools_techniques: tuple[str, ...]
    outputs: tuple[str, ...]
    producible: tuple[str, ...]

    @property
    def inputs_ready(self) -> bool:
        """True when every input the process needs already exists."""
        return all(i.present for i in self.inputs)


def _step_for(process: object, project: Project, session: Session, as_of: date) -> WizardStep:
    from driftless.pmbok.model import Process

    assert isinstance(process, Process)
    inputs = tuple(
        InputStatus(kind, mapping.resolve(kind, project, session, as_of).present)
        for kind in process.inputs
    )
    producible = _producible(process)
    return WizardStep(
        process_id=process.id,
        name=process.name,
        group=process.group.value,
        area=process.area.value,
        state=st.process_state(process, project, session, as_of).value,
        inputs=inputs,
        tools_techniques=process.tools_techniques,
        outputs=process.outputs,
        producible=producible,
    )


def next_step(
    session: Session,
    project: Project,
    as_of: date,
    groups: Sequence[ProcessGroup] | None = None,
) -> WizardStep | None:
    """The next incomplete, store-assessable process — or ``None`` when nothing is left.

    A process the wizard can produce nothing for is skipped along with the
    unassessable ones: a step whose form offers no output is a dead end.
    ``groups`` restricts the search (e.g. just Initiating and Planning for
    onboarding); by default it walks every group in lifecycle order.
    """
    wanted = set(groups) if groups is not None else set(_GROUP_ORDER)
    for group in _GROUP_ORDER:
        if group not in wanted:
            continue
        for process in catalog.by_group(group):
            if not st.is_assessable(process):
                continue
            if not _producible(process):
                continue  # nothing to offer here — a form with no output is a dead end
            if st.process_state(process, project, session, as_of) in _DONE:
                continue
            return _step_for(process, project, session, as_of)
    return None


# Below its callers on purpose: docs/pmbok-mapping.md cites next_step by line number,
# and a test holds that citation to the line (tests/test_docs_pmbok_mapping.py).
def _producible(process: object) -> tuple[str, ...]:
    """The process's outputs the wizard can actually make, from the producer registry.

    Not from ``mapping.is_tracked``: producing goes through ``wizard.cli.produce``,
    which raises ``KeyError`` — HTTP 422 on the browser form — for a kind it has no
    producer for. A *derived* kind (resolved from stored inputs, so it has nothing of
    its own to write) is tracked yet unproducible by construction; reading the one
    registry that answers the question is what stops such a kind ever being drawn as a
    button, instead of a check bolted on after the fact. The import is function-local
    because ``wizard.cli`` imports this module: the engine's read side stays below the
    API in the module-level import order, the same idiom ``_step_for`` uses.
    """
    from driftless.pmbok.model import Process
    from driftless.wizard.cli import producible_kinds

    assert isinstance(process, Process)
    offered = frozenset(producible_kinds())
    return tuple(kind for kind in process.outputs if kind in offered)


def status(session: Session, project: Project, as_of: date) -> tuple[tuple[str, str], ...]:
    """The whole process-state map: ``(process_id, state)`` in catalog order."""
    return tuple(
        (process.id, state.value)
        for process, state in st.project_process_states(project, session, as_of)
    )
