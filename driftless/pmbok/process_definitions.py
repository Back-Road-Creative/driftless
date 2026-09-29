"""``PROCESS_DEFINITIONS``: the process explanation registry, one
``ProcessDefinition`` per member of ``driftless.pmbok.catalog.PROCESSES``.
Adding a process to a knowledge area module automatically gives it a
definition here; there is no second list to update.

Every definition wraps the catalog's own ``Process`` object by reference
rather than by copy — ``process_definitions.py`` composes plain-language
content *onto* ``Process``, it never widens the dataclass itself, so
``tests/test_pmbok_catalog.py`` keeps pinning ``Process`` byte-unchanged. The
explanation fields (plain_summary, why_bother, done_when, first_time_tip)
come from ``driftless.pmbok.process_content``, which composes them out of one
module per knowledge area — see that package's docstring. Every catalog
process has content today, and ``tests/test_process_totality.py`` walks the
whole catalog and fails on the first id and field that does not;
structurally, though, an id no content module claims still gets a
``ProcessDefinition`` with those fields empty, so a process added to a
knowledge area module appears here immediately and is caught there rather
than crashing a page.
"""

from __future__ import annotations

from dataclasses import dataclass

from driftless.pmbok import catalog
from driftless.pmbok.model import Process
from driftless.pmbok.process_content import ProcessContent, collect_content


@dataclass(frozen=True)
class ProcessDefinition:
    """One process's identity — the exact frozen ``Process`` the catalog
    holds — plus the plain-language content ``process_content``'s per-area
    modules supply."""

    process: Process
    plain_summary: str = ""
    why_bother: str = ""
    done_when: str = ""
    first_time_tip: str = ""
    worked_example: str = ""
    pitfalls: tuple[str, ...] = ()


#: Explanation content, keyed by process id, composed from every area content
#: module ``process_content`` can discover. An id absent here (no content
#: module has claimed it yet) yields an all-empty ``ProcessContent``.
_CONTENT: dict[str, ProcessContent] = collect_content()

_EMPTY_CONTENT = ProcessContent()


def _definition(process: Process) -> ProcessDefinition:
    content = _CONTENT.get(process.id, _EMPTY_CONTENT)
    return ProcessDefinition(
        process=process,
        plain_summary=content.plain_summary,
        why_bother=content.why_bother,
        done_when=content.done_when,
        first_time_tip=content.first_time_tip,
        worked_example=content.worked_example,
        pitfalls=content.pitfalls,
    )


#: One entry per ``catalog.PROCESSES`` member, keyed by that member's id.
PROCESS_DEFINITIONS: dict[str, ProcessDefinition] = {
    process.id: _definition(process) for process in catalog.PROCESSES
}


def get(process_id: str) -> ProcessDefinition:
    """The definition for the process with ``process_id``, or ``KeyError``."""
    try:
        return PROCESS_DEFINITIONS[process_id]
    except KeyError:
        raise KeyError(f"no process with id {process_id!r}") from None
