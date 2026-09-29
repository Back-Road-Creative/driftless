"""Filing a weekly status snapshot, for whichever surface asked."""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import fetch
from driftless.assess.percent import stamped_percent
from driftless.db.changelog import set_actor
from driftless.models import Project, StatusSnapshot


def create_status_snapshot(db: Session, payload: s.StatusSnapshotIn, actor: str) -> StatusSnapshot:
    """Create a weekly snapshot, stamping percent complete from calc.

    The client sends the RAG and note it authored; the completion figure is
    computed here from the tasks under the project — never accepted from the
    request — so the series can never hold a hand-typed number that disagrees
    with the work actually done.

    ``actor`` is required, stamped on the session
    (:func:`driftless.db.changelog.set_actor`) before the row is written. The
    JSON route and the status page pass through the identity
    ``driftless.api.deps.get_session`` already resolved
    (``driftless.api.deps.resolved_actor``) rather than this function
    re-deriving it; the wizard's producer (:mod:`driftless.services.wizard_writes`)
    sits behind no such dependency and passes its own.
    """
    set_actor(db, actor)
    project = fetch(db, Project, payload.project_id)
    row = StatusSnapshot(
        project_id=project.id,
        taken_on=payload.taken_on,
        rag_status=payload.rag_status,
        note=payload.note,
        percent_complete=stamped_percent(db, project, payload.taken_on),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
