"""person: kind and agent binding, sign_off: signed_by_kind

Three columns. ``person.kind`` ("human", the default, or "agent") gets a named CHECK,
matching the ``one_of`` idiom every other vocabulary in this schema uses.
``person.agent_token_id`` is a nullable FK to ``api_token.id``: the credential an agent
Person writes through, so a sign-off traces "agent, not human" back to a bound token
rather than a name match. ``sign_off.signed_by_kind`` mirrors ``person.kind`` on the
ledger row itself, stamped once at write time by
``driftless.services.sign_offs.create_sign_off``, so the ledger's own actor class
survives independent of whatever the Person table says later.

Existing rows backfill to ``"human"`` before either CHECK is added, so an upgraded
store never fails its own new constraint.

Revision ID: 7b8f97e1c973
Revises: d9c3b6a8e1f2
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b8f97e1c973"  # pragma: allowlist secret
down_revision: str | None = "d9c3b6a8e1f2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="human")
        )
        batch_op.add_column(sa.Column("agent_token_id", sa.Integer(), nullable=True))
        batch_op.create_check_constraint("ck_kind", "kind IN ('human', 'agent')")
        batch_op.create_foreign_key(
            "fk_person_agent_token_id_api_token", "api_token", ["agent_token_id"], ["id"]
        )
        batch_op.create_index("ix_person_agent_token_id", ["agent_token_id"], unique=False)

    with op.batch_alter_table("sign_off", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "signed_by_kind", sa.String(length=20), nullable=False, server_default="human"
            )
        )
        batch_op.create_check_constraint(
            "ck_signed_by_kind", "signed_by_kind IN ('human', 'agent')"
        )


def downgrade() -> None:
    with op.batch_alter_table("sign_off", schema=None) as batch_op:
        batch_op.drop_constraint("ck_signed_by_kind", type_="check")
        batch_op.drop_column("signed_by_kind")

    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_index("ix_person_agent_token_id")
        batch_op.drop_constraint("fk_person_agent_token_id_api_token", type_="foreignkey")
        batch_op.drop_constraint("ck_kind", type_="check")
        batch_op.drop_column("agent_token_id")
        batch_op.drop_column("kind")
