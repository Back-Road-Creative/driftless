"""row_revision: an optimistic-concurrency token on every PATCH/DELETE-able table

One integer column, defaulting to 1, on every table the API's generic PATCH and
DELETE reach (``driftless.api.app._writes``). The API bumps it on every
successful write and compares it against the caller's ``If-Match`` header before
applying one (``driftless.api.app._apply``, ``_delete``, ``_check_revision``), so
a stale write is refused with 409 rather than silently overwriting a concurrent
edit. Named ``row_revision``, not ``version``: ``baseline.version`` already names
something unrelated, the domain re-baselining count a PM chooses by hand, and
this is an unrelated, server-managed token no client ever sets directly.

Not added to the create-only or append-only tables (``cost_entry``,
``status_snapshot``, ``sign_off``, ``scorecard_metric_observation``,
``quality_measurement``, ``app_user``, ``api_token``) -- none of those accept a
PATCH or DELETE, so a concurrency token on them would guard nothing.

Revision ID: 7cbe3c7ed36e
Revises: f9b52e7d3a06
Create Date: 2026-08-13 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7cbe3c7ed36e"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "f9b52e7d3a06"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every table whose rows accept a PATCH or DELETE through the generic write path.
_REVISIONED: tuple[str, ...] = (
    "business",
    "portfolio",
    "program",
    "project",
    "workstream",
    "task",
    "department",
    "person",
    "strategic_objective",
    "scorecard_source",
    "scorecard_contribution",
    "scorecard_metric_definition",
    "baseline",
    "baseline_line",
    "milestone",
    "sprint",
    "risk",
    "issue",
    "change_request",
    "budget_line",
    "stakeholder",
    "narrative_artifact",
    "quality_metric",
    "procurement_agreement",
)


def upgrade() -> None:
    for table in _REVISIONED:
        op.add_column(
            table,
            sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    for table in reversed(_REVISIONED):
        op.drop_column(table, "row_revision")
