"""Resource knowledge-area evaluator: over-allocation of the people on this project.

Signal: for every person who is the assignee of a not-done, hour-estimated task
in this project, sum their remaining hours ACROSS EVERY PROJECT and weigh that
against ``Person.capacity_hours``. A ratio over 1.0 means the person is on the
hook for more hours than they have to give; red when anyone crosses that line,
amber when someone is close (over 0.8) but nobody has crossed it yet, green
otherwise — including when there are no assigned, hour-estimated tasks to
measure. Actions point at the PMBOK resource-levelling techniques. Pure and
as-of-parameterised — reads no wall clock.

Store-wide because capacity is the PERSON's, which is what every surface that
prints "Capacity (hrs/wk)" beside ``person_task_loads``'s store-wide total
already means. Scoped to one project it divided a slice by the whole, so nobody
could ever be flagged: the demo seed's two people sit at 150 % and 135 % and one
of them held the only work on a project rendering green with "No live threats".
The overload is reported on every project holding some of those hours and no
other — each of those is a cause and can level its own share, while a project
the person holds no open work on is neither — and the threat prints the
store-wide total beside the hours booked here, so the ratio reconciles against
the project's own board instead of reading as an error.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import Person, Project, Task, Workstream
from driftless.pmbok.state import threat_subject_ref

KIND = "resource"

_AMBER_RATIO = 0.8
_RED_RATIO = 1.0

# Open (not done) and hour-estimated: a task without an hours estimate cannot
# be weighed against capacity_hours — shared by person_task_load below.
_OPEN_HOUR_TASK = (Task.status != "done", Task.estimate_unit == "hours")


def _assigned_tasks(session: Session, project_id: int) -> list[Task]:
    """This project's open, hour-estimated, assigned tasks, ``assignee`` loaded.

    ``Task`` hangs off ``Workstream``, not ``Project``, so batching needs the join
    and ``Workstream.project_id`` as the grouping key — hence ``project_grouped``
    rather than ``project_rows``. ``selectinload`` brings the people in on the
    same batched pass, so the capacity figures below cost no query of their own:
    the weak identity map evicts a ``Person`` the moment nothing holds a
    reference, so even an ``IN`` query per project charged a store-wide walk once
    per PROJECT.
    """

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Task]]:
        stmt = (
            select(Workstream.project_id, Task)
            .join(Task, Task.workstream_id == Workstream.id)
            .where(Workstream.project_id.in_(ids), Task.assignee_id.is_not(None), *_OPEN_HOUR_TASK)
            .order_by(Task.id)
            .options(selectinload(Task.assignee))
        )
        return ((pid, task) for pid, task in session.execute(stmt))

    return adapters.project_grouped(session, _assigned_tasks, load, project_id)


def _load_view(session: Session, project_id: int) -> tuple[list[Task], dict[int, float]]:
    """This project's assigned tasks, and the STORE-WIDE remaining hours of
    everyone holding one — :func:`person_task_loads`, never a second summation.

    Batched through the same :func:`adapters.project_grouped` scope, so the extra
    read costs ONE statement for the whole walk rather than one per project: the
    grouped payload is computed once inside ``load`` and handed to every project
    in the scope, and ``_assigned_tasks`` is already cached by the time it runs.
    """

    def load(ids: Sequence[int]) -> Iterable[tuple[int, tuple[list[Task], dict[int, float]]]]:
        per_project = {pid: _assigned_tasks(session, pid) for pid in ids}
        assignees = sorted(
            {t.assignee_id for tasks in per_project.values() for t in tasks if t.assignee_id}
        )
        hours = {pid: load_[1] for pid, load_ in person_task_loads(session, assignees).items()}
        return ((pid, (tasks, hours)) for pid, tasks in per_project.items())

    view = adapters.project_grouped(session, _load_view, load, project_id)
    return view[0] if view else ([], {})


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's resource-allocation health as of ``as_of``."""
    tasks, store_wide = _load_view(session, project.id)
    here: dict[int, float] = {}
    people: dict[int, Person] = {}
    for task in tasks:
        assignee = task.assignee
        if assignee is None:  # pragma: no cover - filtered by the query above
            continue
        here[assignee.id] = here.get(assignee.id, 0.0) + (task.estimate or 0.0)
        people[assignee.id] = assignee

    # Whose hours: this project's assignees. How many: all of theirs, everywhere.
    # Same skip-on-missing/non-positive-capacity semantics as the per-assignee
    # read this replaces: no person, or no capacity to weigh against, no ratio.
    ratios: dict[int, float] = {
        pid: store_wide[pid] / people[pid].capacity_hours
        for pid in here
        if people[pid].capacity_hours > 0
    }

    if not ratios:
        return Assessment(KIND, as_of, 0.0, "green")

    max_ratio = max(ratios.values())
    over_allocated = {pid: r for pid, r in ratios.items() if r > _RED_RATIO}
    red = bool(over_allocated)
    amber = not red and max_ratio > _AMBER_RATIO

    if not (red or amber):
        return Assessment(KIND, as_of, 0.0, "green")

    severity: RagStatus = "red" if red else "amber"
    score = round(
        max(r - _RED_RATIO for r in over_allocated.values())
        if red
        else max(0.0, max_ratio - _AMBER_RATIO),
        4,
    )

    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    count = len(over_allocated)
    if red:
        who_text = f"{count} {'person' if count == 1 else 'people'} over-allocated"
    else:
        who_text = "allocation getting tight"
    # Highest ratio, lowest id on a tie — the peak is one person, deterministically.
    peak = max(ratios, key=lambda pid: (ratios[pid], -pid))
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        f"{who_text} (peak ratio {max_ratio:.2f} — {store_wide[peak]:g} h in all, "
        f"{here[peak]:g} h of it on this project).",
        ref,
    )
    actions = (
        Action(
            f"resource:level:{project.id}",
            "Level or smooth the resource assignments",
            "resource_optimization",
            "Re-sequence or re-assign tasks so no one's remaining hours exceed their capacity.",
            ref,
        ),
        Action(
            f"resource:negotiate:{project.id}",
            "Negotiate for more capacity",
            "negotiation",
            "Secure additional hours or headcount for the over-committed assignees.",
            ref,
        ),
        Action(
            f"resource:preassign:{project.id}",
            "Revisit pre-assignments",
            "pre_assignment",
            "Check whether upcoming work was pre-assigned to people already at capacity.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)


def person_task_load(session: Session, person_id: int) -> tuple[int, float]:
    """One person's open, hour-estimated task count and remaining hours — the
    same ``_OPEN_HOUR_TASK`` filter :func:`evaluate` applies per project,
    across every project the person is assigned to. Reused by
    ``driftless.web.departments`` so a capacity figure never drifts from this."""
    tasks = session.scalars(
        select(Task).where(Task.assignee_id == person_id, *_OPEN_HOUR_TASK)
    ).all()
    return len(tasks), sum(task.estimate or 0.0 for task in tasks)


def person_task_loads(session: Session, person_ids: Sequence[int]) -> dict[int, tuple[int, float]]:
    """:func:`person_task_load` for every id in ``person_ids``, batched into one
    query instead of one per person — the department drill page's per-row
    capacity figures, which would otherwise cost a statement per person shown.
    Same ``_OPEN_HOUR_TASK`` filter and per-person maths, just grouped.

    Two columns, not whole ``Task`` rows: this is a counting read, and
    :func:`evaluate` now makes it on a page scoped to ONE project, where
    materialising every open task of that project's assignees would pull the rest
    of the store into the session for a sum. Ordered by id so the float
    accumulation is the same on any backend."""
    counts: dict[int, int] = dict.fromkeys(person_ids, 0)
    hours: dict[int, float] = dict.fromkeys(person_ids, 0.0)
    rows = session.execute(
        select(Task.assignee_id, Task.estimate)
        .where(Task.assignee_id.in_(person_ids), *_OPEN_HOUR_TASK)
        .order_by(Task.id)
    )
    for assignee_id, estimate in rows:
        if assignee_id is None:  # pragma: no cover - filtered by the query above
            continue
        counts[assignee_id] += 1
        hours[assignee_id] += estimate or 0.0
    return {pid: (counts[pid], hours[pid]) for pid in person_ids}
