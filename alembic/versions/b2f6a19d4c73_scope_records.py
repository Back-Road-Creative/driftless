"""scope records: requirements, requirement traces, deliverables (the WBS
tree) and the acceptance ledger

Four new tables for ``driftless.models.scope`` -- the Scope Management
knowledge area's own rows. ``requirement`` is one stated need; ``deliverable``
IS the WBS node, addressed by ``wbs_code`` and a self-referential
``parent_id``; ``requirement_trace`` links a requirement to exactly one of a
deliverable, a task or a backlog item; ``acceptance_record`` is the
append-only verify/accept ledger against a deliverable.

Revision ID: b2f6a19d4c73
Revises: 0ce50b8b6731
Create Date: 2026-08-27 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2f6a19d4c73"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "0ce50b8b6731"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIREMENT_CATEGORIES = (
    "business",
    "stakeholder",
    "functional",
    "nonfunctional",
    "quality",
    "transition",
)
_REQUIREMENT_PRIORITIES = ("must_have", "should_have", "could_have", "wont_have")
_REQUIREMENT_STATUSES = ("proposed", "approved", "traced", "verified", "withdrawn")
_DELIVERABLE_STATUSES = ("planned", "in_progress", "verified", "accepted", "rejected")


def upgrade() -> None:
    op.create_table(
        "deliverable",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("wbs_code", sa.String(length=50), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("acceptance_criteria", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("accepted_on", sa.Date(), nullable=True),
        sa.Column("accepted_by", sa.String(length=200), nullable=True),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{v}'" for v in _DELIVERABLE_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint("parent_id != id", name="ck_deliverable_not_own_parent"),
        sa.UniqueConstraint("project_id", "wbs_code", name="uq_deliverable_project_wbs_code"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["deliverable.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deliverable_project_id", "deliverable", ["project_id"])
    op.create_index("ix_deliverable_parent_id", "deliverable", ["parent_id"])

    op.create_table(
        "requirement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("statement", sa.String(length=2000), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False, server_default="functional"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="should_have"),
        sa.Column("source_stakeholder_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "category IN ({})".format(", ".join(f"'{v}'" for v in _REQUIREMENT_CATEGORIES)),
            name="ck_category",
        ),
        sa.CheckConstraint(
            "priority IN ({})".format(", ".join(f"'{v}'" for v in _REQUIREMENT_PRIORITIES)),
            name="ck_priority",
        ),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{v}'" for v in _REQUIREMENT_STATUSES)),
            name="ck_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["source_stakeholder_id"], ["stakeholder.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requirement_project_id", "requirement", ["project_id"])
    op.create_index(
        "ix_requirement_source_stakeholder_id", "requirement", ["source_stakeholder_id"]
    )

    op.create_table(
        "requirement_trace",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("deliverable_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("backlog_item_id", sa.Integer(), nullable=True),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "(CASE WHEN deliverable_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN backlog_item_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_requirement_trace_one_target",
        ),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirement.id"]),
        sa.ForeignKeyConstraint(["deliverable_id"], ["deliverable.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["backlog_item_id"], ["backlog_item.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requirement_trace_requirement_id", "requirement_trace", ["requirement_id"])
    op.create_index("ix_requirement_trace_deliverable_id", "requirement_trace", ["deliverable_id"])
    op.create_index("ix_requirement_trace_task_id", "requirement_trace", ["task_id"])
    op.create_index(
        "ix_requirement_trace_backlog_item_id", "requirement_trace", ["backlog_item_id"]
    )

    op.create_table(
        "acceptance_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deliverable_id", sa.Integer(), nullable=False),
        sa.Column("verified_on", sa.Date(), nullable=True),
        sa.Column("accepted_on", sa.Date(), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "verified_on IS NOT NULL OR accepted_on IS NOT NULL",
            name="ck_acceptance_record_has_date",
        ),
        sa.CheckConstraint(
            "accepted_on IS NULL OR verified_on IS NULL OR accepted_on >= verified_on",
            name="ck_acceptance_record_order",
        ),
        sa.ForeignKeyConstraint(["deliverable_id"], ["deliverable.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_acceptance_record_deliverable_id", "acceptance_record", ["deliverable_id"])


def downgrade() -> None:
    op.drop_index("ix_acceptance_record_deliverable_id", table_name="acceptance_record")
    op.drop_table("acceptance_record")
    op.drop_index("ix_requirement_trace_backlog_item_id", table_name="requirement_trace")
    op.drop_index("ix_requirement_trace_task_id", table_name="requirement_trace")
    op.drop_index("ix_requirement_trace_deliverable_id", table_name="requirement_trace")
    op.drop_index("ix_requirement_trace_requirement_id", table_name="requirement_trace")
    op.drop_table("requirement_trace")
    op.drop_index("ix_requirement_source_stakeholder_id", table_name="requirement")
    op.drop_index("ix_requirement_project_id", table_name="requirement")
    op.drop_table("requirement")
    op.drop_index("ix_deliverable_parent_id", table_name="deliverable")
    op.drop_index("ix_deliverable_project_id", table_name="deliverable")
    op.drop_table("deliverable")
