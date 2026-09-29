"""Filing a risk response, for whichever surface asks.

The web assist page's POST calls this directly, exactly the shape
``driftless.services.status_snapshots`` and ``driftless.services.sign_offs`` already
use — the row lands through the same validated ``RiskResponseIn`` schema and the
same cross-row rule (``driftless.api.rules.risk_response_lands_valid``) the JSON
``POST /risk-responses`` route runs, so the two write paths are one.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import insert
from driftless.api.rules import risk_response_lands_valid
from driftless.models import Person, Project, Risk, RiskResponse


def file_risk_response(db: Session, payload: s.RiskResponseIn) -> RiskResponse:
    """Validate and append one response plan against a risk.

    ``insert`` is the same parent-existence check ``creates(app, "/risk-responses", ...)``
    runs for the JSON route — a 404 naming the missing owner/risk/project rather than a
    raw FK failure — so this write is not a second, looser path to the same table.
    """
    risk_response_lands_valid(db, payload)
    return insert(db, RiskResponse, payload, project_id=Project, risk_id=Risk, owner_id=Person)
