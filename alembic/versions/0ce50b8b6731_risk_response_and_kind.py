"""risk: threat/opportunity kind, and the risk_response table

Two changes for response planning. ``risk`` gains ``kind`` (``threat`` or
``opportunity``, default ``threat`` so every historical row backfills to the shape
a risk always meant before opportunities were named at all). ``risk_response`` is a
new table: one filed response per row, carrying its strategy, owner, trigger,
planned action, residual probability/impact, cost, schedule impact and status.

Revision ID: 0ce50b8b6731
Revises: a1c5e8d3f647
Create Date: 2026-08-27 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0ce50b8b6731"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "a1c5e8d3f647"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RISK_KINDS = ("threat", "opportunity")
_RESPONSE_STRATEGIES = (
    "avoid",
    "mitigate",
    "transfer",
    "exploit",
    "enhance",
    "share",
    "accept",
    "escalate",
)
_RESPONSE_STATUSES = ("planned", "in_progress", "implemented", "abandoned")


def upgrade() -> None:
    with op.batch_alter_table("risk", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="threat")
        )
        batch_op.create_check_constraint(
            "ck_kind", "kind IN ({})".format(", ".join(f"'{k}'" for k in _RISK_KINDS))
        )

    op.create_table(
        "risk_response",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("risk_id", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=2000), nullable=False),
        sa.Column("planned_action", sa.String(length=2000), nullable=False),
        sa.Column("residual_probability", sa.Float(), nullable=False),
        sa.Column("residual_impact", sa.Float(), nullable=False),
        sa.Column("cost_of_response", sa.Float(), nullable=False, server_default="0"),
        sa.Column("schedule_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "strategy IN ({})".format(", ".join(f"'{s}'" for s in _RESPONSE_STRATEGIES)),
            name="ck_strategy",
        ),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _RESPONSE_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint(
            "residual_probability BETWEEN 0 AND 1", name="ck_risk_response_residual_probability"
        ),
        sa.CheckConstraint("residual_impact >= 0", name="ck_risk_response_residual_impact"),
        sa.CheckConstraint("cost_of_response >= 0", name="ck_risk_response_cost_of_response"),
        sa.CheckConstraint("schedule_days >= 0", name="ck_risk_response_schedule_days"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["risk_id"], ["risk.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_response_project_id", "risk_response", ["project_id"])
    op.create_index("ix_risk_response_risk_id", "risk_response", ["risk_id"])
    op.create_index("ix_risk_response_owner_id", "risk_response", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_response_owner_id", table_name="risk_response")
    op.drop_index("ix_risk_response_risk_id", table_name="risk_response")
    op.drop_index("ix_risk_response_project_id", table_name="risk_response")
    op.drop_table("risk_response")

    with op.batch_alter_table("risk", schema=None) as batch_op:
        batch_op.drop_constraint("ck_kind", type_="check")
        batch_op.drop_column("kind")
