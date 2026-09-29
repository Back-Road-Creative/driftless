"""``record_run``: the one write path for ``TechniqueRun`` rows.

Refuses a run with no actor, or naming a technique/process the catalogs do
not recognize, before either becomes a stored row — robust by construction.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.records import fetch
from driftless.models import Project
from driftless.models.technique_runs import TechniqueRun
from driftless.pmbok import catalog
from driftless.pmbok.provenance import MethodContext
from driftless.pmbok.tt import TT_CATALOG


class MissingActorError(ValueError):
    """A run with nobody credited for it is not provenance."""


class UnknownTechniqueError(ValueError):
    """``technique_key`` names nothing in the closed ``TT_CATALOG``."""


class UnknownProcessError(ValueError):
    """``process_id`` names no catalog process."""


def record_run(
    db: Session,
    *,
    project_id: int,
    technique_key: str,
    process_id: str,
    actor: str | None,
    as_of: date,
    method: MethodContext,
    source_version: str,
    inputs_snapshot: dict[str, Any] | None = None,
    outputs_produced: dict[str, Any] | None = None,
) -> TechniqueRun:
    """Append one run to the ledger, or refuse it outright."""
    if not actor:
        raise MissingActorError("record_run requires an actor")
    if technique_key not in TT_CATALOG:
        raise UnknownTechniqueError(f"{technique_key!r} is not in TT_CATALOG")
    try:
        catalog.get(process_id)
    except KeyError as error:
        raise UnknownProcessError(str(error)) from error
    fetch(db, Project, project_id)
    row = TechniqueRun(
        project_id=project_id,
        technique_key=technique_key,
        process_id=process_id,
        actor=actor,
        as_of=as_of,
        method=method.value,
        source_version=source_version,
        inputs_snapshot=json.dumps(inputs_snapshot or {}, sort_keys=True),
        outputs_produced=json.dumps(outputs_produced or {}, sort_keys=True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def runs_for_project(db: Session, project_id: int, as_of: date) -> list[TechniqueRun]:
    """Every run recorded for ``project_id`` at or before ``as_of``, latest first."""
    stmt = (
        select(TechniqueRun)
        .where(TechniqueRun.project_id == project_id, TechniqueRun.as_of <= as_of)
        .order_by(TechniqueRun.as_of.desc(), TechniqueRun.id.desc())
    )
    return list(db.scalars(stmt))
