"""The Cost Report (EVM): one project's earned-value figures as Markdown. Every
figure comes from ``gather.project_evm``; the template formats, this does no maths."""

from datetime import date

from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.report import engine, gather

SLUG = "cost-evm"
TITLE = "Cost Report (EVM)"


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Cost/EVM document for ``project`` as of ``as_of``."""
    costs = gather.project_costs(session).get(project.id, [])
    snapshot = gather.project_evm(project, costs, as_of)
    return engine.render(
        "cost_evm.md", {"title": TITLE, "project": project.name, "as_of": as_of, "s": snapshot}
    )
