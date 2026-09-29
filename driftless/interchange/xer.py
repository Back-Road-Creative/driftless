"""Parse a Primavera P6 XER schedule into an
:class:`~driftless.interchange.common.ImportedSchedule` — stdlib ``csv``
only, no dependency.

An XER file is tab-delimited text, one table per block: a ``%T`` line names
the table, the following ``%F`` line names its columns, each ``%R`` line is
one row, and ``%E`` ends the file. This reader only looks at two tables:
``TASK`` (``task_id``, ``task_code``, ``task_name``, ``target_drtn_hr_cnt`` —
duration in hours, converted to whole days on an 8-hour day) and
``TASKPRED`` (``task_id`` the successor, ``pred_task_id`` the predecessor,
``pred_type`` one of P6's ``PR_FS``/``PR_SS``/``PR_FF``/``PR_SF``, and
``lag_hr_cnt`` in hours, converted to whole days). Every other table in the
file is ignored.
"""

from __future__ import annotations

import csv
from pathlib import Path

from driftless.interchange.common import ImportedDependency, ImportedSchedule, ImportedTask

_PRED_KINDS = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}


def parse_xer(path: str | Path) -> ImportedSchedule:
    """Parse an XER file into an :class:`ImportedSchedule`."""
    tasks: list[ImportedTask] = []
    dependencies: list[ImportedDependency] = []
    table: str | None = None
    fields: list[str] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if not row or not row[0]:
                continue
            marker = row[0]
            if marker == "%T":
                table = row[1]
                fields = []
            elif marker == "%F":
                fields = row[1:]
            elif marker == "%R" and table is not None:
                record = dict(zip(fields, row[1:], strict=False))
                if table == "TASK":
                    hours = float(record.get("target_drtn_hr_cnt") or 0)
                    tasks.append(
                        ImportedTask(
                            external_id=record["task_id"],
                            name=record.get("task_name", ""),
                            duration_days=int(hours // 8),
                        )
                    )
                elif table == "TASKPRED":
                    kind = _PRED_KINDS.get(record.get("pred_type", ""), "FS")
                    lag_hours = float(record.get("lag_hr_cnt") or 0)
                    dependencies.append(
                        ImportedDependency(
                            predecessor=record["pred_task_id"],
                            successor=record["task_id"],
                            kind=kind,  # type: ignore[arg-type]
                            lag_days=int(lag_hours // 8),
                        )
                    )
            elif marker == "%E":
                table = None
    return ImportedSchedule(tasks=tuple(tasks), dependencies=tuple(dependencies))
