"""The Process Map: the 49-process ITTO grid for one project, each process with its
group, knowledge area and computed state (not-started / in-progress / produced /
signed-off / waived), plus the overall completeness. Project-scoped. State is
computed by ``driftless.pmbok.state`` from artifacts and the sign-off ledger, so the
map regenerates byte-identically in catalog order."""

from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.pmbok import state
from driftless.pmbok.model import Process
from driftless.report import engine

SLUG = "process-map"
TITLE = "Process Map"


def _process_rows(states: Sequence[tuple[Process, state.ProcessState]]) -> list[dict[str, Any]]:
    return [
        {
            "id": process.id,
            "name": process.name,
            "group": process.group.value,
            "area": process.area.value,
            "state": process_state.value,
        }
        for process, process_state in states
    ]


def _scope(session: Session, project: Project) -> AbstractContextManager[None]:
    """``state.prefetched`` over this one project — or a no-op when a store-wide
    caller (the report CLI's document loop) already holds a scope over every
    project, so the whole sign-off-ledger scan and the per-model resolver reads
    are not re-run once per project inside it. Detected via ``state``'s own
    session-info key because ``state.prefetched`` exposes no public "is one
    open?" surface yet; if that key ever moves, the worst case is reopening the
    nested scope — the pre-fix cost, which ``tests/test_perf_report_all.py``'s
    statement ceiling catches."""
    if session.info.get(state._SIGN_OFF_PREFETCH_KEY) is not None:
        return nullcontext()
    return state.prefetched(session, [project])


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Process Map for ``project`` as of ``as_of``."""
    # One prefetch scope for the whole render: project_process_states is computed
    # ONCE and threaded into _process_rows below instead of it re-walking the
    # store; state.completeness's own walk still rides the same cache (mirrors
    # driftless.web.pages's process_map route).
    with _scope(session, project):
        states = state.project_process_states(project, session, as_of)
        rows = _process_rows(states)
        completeness = state.completeness(project, session, as_of)
    return engine.render(
        "process_map.md",
        {
            "title": TITLE,
            "project": project,
            "as_of": as_of,
            "completeness": f"{completeness * 100:.0f}%" if completeness is not None else "n/a",
            "rows": rows,
        },
    )
