"""Parse and write Microsoft Project XML (MSPDI) schedules — stdlib
``xml.etree.ElementTree`` only, no dependency.

**Import** (:func:`parse_msproject_xml`) reads the subset of the MSPDI schema
(``http://schemas.microsoft.com/project``) that names a schedule: each
``<Task>``'s ``<UID>``, ``<Name>`` and ``<Duration>`` (an xsd:duration string,
e.g. ``PT16H0M0S`` — hours, converted to whole days on an 8-hour day), plus
each ``<PredecessorLink>``'s ``<PredecessorUID>``, ``<Type>`` (MSPDI's own
vocabulary: ``0`` finish-to-finish, ``1`` finish-to-start, ``2``
start-to-finish, ``3`` start-to-start) and ``<LinkLag>`` (tenths of a day in
this reader — the field MSPDI defines in tenths of minutes for elapsed lag is
not modelled; a lag of ``0`` is the common case and every hand-authored
sample uses it). A task with no ``<Name>`` or a duration MSPDI cannot express
is skipped, never guessed at.

**Export** (:func:`export_msproject_xml`) is the inverse encoding over a
:class:`~driftless.pmbok.schedule_facts.ScheduleFacts` — the same
approved-baseline read ``web.gantt`` and ``pmbok.schedule_facts`` already do —
so ``driftless export msproject`` writes exactly the tasks and links
:func:`parse_msproject_xml` would read back. Activities and links are sorted
by id before writing (never trusting caller order), and the file carries no
timestamp of its own, so two exports of the same ``as_of`` are byte-identical.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, cast

from driftless.calc.network import Dependency
from driftless.interchange.common import ImportedDependency, ImportedSchedule, ImportedTask

if TYPE_CHECKING:
    from driftless.pmbok.schedule_facts import ScheduleFacts

_NS = {"p": "http://schemas.microsoft.com/project"}
_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
# MSPDI's four link types, positional per the schema — index is the ``<Type>`` value.
_LINK_KINDS = ("FF", "FS", "SF", "SS")


def _tag(name: str) -> str:
    return f"{{{_NS['p']}}}{name}"


def _duration_days(text: str | None) -> int:
    """An xsd:duration like ``PT16H0M0S`` to whole days on an 8-hour day."""
    if not text:
        return 0
    match = _DURATION.match(text)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    return hours // 8


def parse_msproject_xml(path: str | Path) -> ImportedSchedule:
    """Parse an MSPDI file into an :class:`ImportedSchedule`."""
    root = ET.parse(path).getroot()
    tasks: list[ImportedTask] = []
    dependencies: list[ImportedDependency] = []
    for task_el in root.iter(_tag("Task")):
        uid_el = task_el.find(_tag("UID"))
        name_el = task_el.find(_tag("Name"))
        if uid_el is None or uid_el.text is None or name_el is None or not name_el.text:
            continue
        uid = uid_el.text
        duration_el = task_el.find(_tag("Duration"))
        tasks.append(
            ImportedTask(
                external_id=uid,
                name=name_el.text,
                duration_days=_duration_days(duration_el.text if duration_el is not None else None),
            )
        )
        for link_el in task_el.findall(_tag("PredecessorLink")):
            pred_el = link_el.find(_tag("PredecessorUID"))
            if pred_el is None or pred_el.text is None:
                continue
            type_el = link_el.find(_tag("Type"))
            lag_el = link_el.find(_tag("LinkLag"))
            type_index = int(type_el.text) if type_el is not None and type_el.text else 1
            kind = _LINK_KINDS[type_index] if 0 <= type_index < len(_LINK_KINDS) else "FS"
            lag_tenths = int(lag_el.text) if lag_el is not None and lag_el.text else 0
            dependencies.append(
                ImportedDependency(
                    predecessor=pred_el.text,
                    successor=uid,
                    kind=kind,  # type: ignore[arg-type]
                    lag_days=lag_tenths // 10,
                )
            )
    return ImportedSchedule(tasks=tuple(tasks), dependencies=tuple(dependencies))


def export_msproject_xml(facts: "ScheduleFacts") -> bytes:
    """Render ``facts``' schedule network as MSPDI XML bytes.

    Round-trips through :func:`parse_msproject_xml`: each activity becomes a
    ``<Task>`` named by ``facts.task_names``, its duration in whole days
    widened back to hours on the same 8-hour day the importer narrows by, and
    each dependency a ``<PredecessorLink>`` on the successor task, typed and
    lagged the same way the importer reads them. No wall clock, no random
    ordering — activities sort by numeric id, a task's links by predecessor
    id — so calling this twice for the same ``facts`` writes identical bytes.
    """
    root = ET.Element(_tag("Project"))
    tasks_el = ET.SubElement(root, _tag("Tasks"))
    by_successor: dict[str, list[Dependency]] = {}
    for dep in facts.network.dependencies:
        by_successor.setdefault(dep.successor, []).append(dep)
    for activity in sorted(facts.network.activities, key=lambda a: int(a.id)):
        task_el = ET.SubElement(tasks_el, _tag("Task"))
        ET.SubElement(task_el, _tag("UID")).text = activity.id
        ET.SubElement(task_el, _tag("Name")).text = facts.task_names[activity.id]
        ET.SubElement(task_el, _tag("Duration")).text = f"PT{activity.duration * 8}H0M0S"
        for dep in sorted(by_successor.get(activity.id, ()), key=lambda d: d.predecessor):
            link_el = ET.SubElement(task_el, _tag("PredecessorLink"))
            ET.SubElement(link_el, _tag("PredecessorUID")).text = dep.predecessor
            ET.SubElement(link_el, _tag("Type")).text = str(_LINK_KINDS.index(dep.kind))
            ET.SubElement(link_el, _tag("LinkLag")).text = str(dep.lag * 10)
    ET.indent(root)
    return cast(bytes, ET.tostring(root, encoding="UTF-8", xml_declaration=True))
