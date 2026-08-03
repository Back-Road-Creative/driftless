"""foundation: org, sign-off, and the narrative/quality/procurement records

Third revision, chained onto the records revision. It adds the models the ITTO
build-out rests on: the org tables (department, person) that the Resource
knowledge area and labour-cost rollup read; the append-only sign_off ledger the
threat feed suppresses against; and the narrative_artifact, quality_measurement
and procurement_agreement records that make the last knowledge areas real. It
also grows two existing tables by one nullable foreign key each —
``task.assignee_id`` and ``project.responsible_department_id`` — which is why
those two use ``batch_alter_table``: SQLite cannot ALTER in a foreign key, so
Alembic rebuilds the table copy-and-move there while Postgres alters in place.

The new tables are created before the two column adds so the foreign keys those
columns carry (``person`` and ``department``) already exist. Autogenerate-free
by design: this was written by hand against the models and is proven byte-for-
byte against ``Base.metadata`` by ``tests/test_migrations.py`` (CHECK constraints
included) and, at runtime, against Postgres 16.

Revision ID: f4a9c2e17b30
Revises: 7df21247c4ac
Create Date: 2026-07-22 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "f4a9c2e17b30"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "7df21247c4ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the six foundation tables, then add the two nullable FK columns."""
    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "name", name="uq_department_business_name"),
    )
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("cost_rate", sa.Float(), nullable=False),
        sa.Column("capacity_hours", sa.Float(), nullable=False),
        sa.CheckConstraint("cost_rate >= 0", name="ck_person_cost_rate"),
        sa.CheckConstraint("capacity_hours > 0", name="ck_person_capacity_hours"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "narrative_artifact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_on", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('assumption_log', 'eef', 'opa', 'lessons_learned')", name="ck_kind"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "kind", name="uq_narrative_project_kind"),
    )
    op.create_table(
        "quality_measurement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=200), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("actual_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "procurement_agreement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_agreement_amount"),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_agreement_window"
        ),
        sa.CheckConstraint("status IN ('draft', 'active', 'closed', 'disputed')", name="ck_status"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sign_off",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("subject_kind", sa.String(length=20), nullable=False),
        sa.Column("subject_ref", sa.String(length=200), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("signal", sa.Float(), nullable=True),
        sa.Column("signed_by", sa.String(length=200), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted', 'resolved', 'deferred', 'rejected', 'waived')",
            name="ck_decision",
        ),
        sa.CheckConstraint("subject_kind IN ('threat', 'process')", name="ck_subject_kind"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # SQLite cannot ALTER a foreign key in; batch rebuilds the table copy-and-move
    # (Postgres alters in place). The new tables above already exist as targets.
    # The FK is named only because batch mode requires it; the models leave it
    # unnamed and the parity test compares foreign keys by column and target, not
    # by name, so a name here does not make the migrated schema disagree.
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assignee_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_task_assignee_person", "person", ["assignee_id"], ["id"])
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.add_column(sa.Column("responsible_department_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_project_responsible_department",
            "department",
            ["responsible_department_id"],
            ["id"],
        )


def downgrade() -> None:
    """Drop the two columns, then the six tables — the exact inverse of upgrade."""
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_column("responsible_department_id")
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_column("assignee_id")
    op.drop_table("sign_off")
    op.drop_table("procurement_agreement")
    op.drop_table("quality_measurement")
    op.drop_table("narrative_artifact")
    op.drop_table("person")
    op.drop_table("department")
