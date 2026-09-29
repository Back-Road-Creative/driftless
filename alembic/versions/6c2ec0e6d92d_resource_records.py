"""resource records: resource types and the RBS tree, the stored RACI,
acquisitions, training, team assessments, conflicts and their actions

Eight new tables for ``driftless.models.team`` -- the Resource Management
knowledge area's own rows. ``resource_type`` is the catalog a project draws
from; ``resource_breakdown`` is the tree built over it (the RBS), addressed
the same self-referential way ``deliverable``'s WBS tree already is.
``responsibility_assignment`` is the stored RACI: a person's role against
exactly one of a deliverable or a task. ``acquisition`` is one staffing event
against a resource type. ``training_record`` is a person's own ledger, not
project-scoped. ``team_assessment`` is the append-only assessment ledger.
``conflict_record`` is current state, like risk/issue; ``conflict_action`` is
its follow-up ledger.

Revision ID: 6c2ec0e6d92d
Revises: b2f6a19d4c73
Create Date: 2026-08-27 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c2ec0e6d92d"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "b2f6a19d4c73"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESOURCE_KINDS = ("people", "equipment", "material")
_RACI_ROLES = ("responsible", "accountable", "consulted", "informed")
_ACQUISITION_SOURCES = ("internal", "external")
_ACQUISITION_STATUSES = ("requested", "approved", "fulfilled", "cancelled")
_CONFLICT_APPROACHES = ("withdraw", "smooth", "compromise", "force", "collaborate")


def upgrade() -> None:
    op.create_table(
        "resource_type",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False, server_default="each"),
        sa.Column("rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{v}'" for v in _RESOURCE_KINDS)), name="ck_kind"
        ),
        sa.CheckConstraint("rate >= 0", name="ck_resource_type_rate"),
        sa.UniqueConstraint("project_id", "name", name="uq_resource_type_project_name"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resource_type_project_id", "resource_type", ["project_id"])

    op.create_table(
        "resource_breakdown",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("resource_type_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("parent_id != id", name="ck_resource_breakdown_not_own_parent"),
        sa.CheckConstraint("quantity > 0", name="ck_resource_breakdown_quantity"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["resource_type_id"], ["resource_type.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["resource_breakdown.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resource_breakdown_project_id", "resource_breakdown", ["project_id"])
    op.create_index(
        "ix_resource_breakdown_resource_type_id", "resource_breakdown", ["resource_type_id"]
    )
    op.create_index("ix_resource_breakdown_parent_id", "resource_breakdown", ["parent_id"])

    op.create_table(
        "responsibility_assignment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("deliverable_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "role IN ({})".format(", ".join(f"'{v}'" for v in _RACI_ROLES)), name="ck_role"
        ),
        sa.CheckConstraint(
            "(CASE WHEN deliverable_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_responsibility_assignment_one_target",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["deliverable_id"], ["deliverable.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_responsibility_assignment_project_id", "responsibility_assignment", ["project_id"]
    )
    op.create_index(
        "ix_responsibility_assignment_deliverable_id",
        "responsibility_assignment",
        ["deliverable_id"],
    )
    op.create_index(
        "ix_responsibility_assignment_task_id", "responsibility_assignment", ["task_id"]
    )
    op.create_index(
        "ix_responsibility_assignment_person_id", "responsibility_assignment", ["person_id"]
    )

    op.create_table(
        "acquisition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("resource_type_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("requested_on", sa.Date(), nullable=False),
        sa.Column("fulfilled_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="requested"),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "source IN ({})".format(", ".join(f"'{v}'" for v in _ACQUISITION_SOURCES)),
            name="ck_source",
        ),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{v}'" for v in _ACQUISITION_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint(
            "fulfilled_on IS NULL OR fulfilled_on >= requested_on", name="ck_acquisition_dates"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["resource_type_id"], ["resource_type.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_acquisition_project_id", "acquisition", ["project_id"])
    op.create_index("ix_acquisition_resource_type_id", "acquisition", ["resource_type_id"])

    op.create_table(
        "training_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_record_person_id", "training_record", ["person_id"])

    op.create_table(
        "team_assessment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("assessed_on", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_team_assessment_score"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_assessment_project_id", "team_assessment", ["project_id"])

    op.create_table(
        "conflict_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("raised_on", sa.Date(), nullable=False),
        sa.Column("parties", sa.String(length=2000), nullable=False),
        sa.Column("approach", sa.String(length=20), nullable=False, server_default="collaborate"),
        sa.Column("resolved_on", sa.Date(), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "approach IN ({})".format(", ".join(f"'{v}'" for v in _CONFLICT_APPROACHES)),
            name="ck_approach",
        ),
        sa.CheckConstraint(
            "resolved_on IS NULL OR resolved_on >= raised_on", name="ck_conflict_record_dates"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conflict_record_project_id", "conflict_record", ["project_id"])

    op.create_table(
        "conflict_action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conflict_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["conflict_id"], ["conflict_record.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conflict_action_conflict_id", "conflict_action", ["conflict_id"])
    op.create_index("ix_conflict_action_owner_id", "conflict_action", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_conflict_action_owner_id", table_name="conflict_action")
    op.drop_index("ix_conflict_action_conflict_id", table_name="conflict_action")
    op.drop_table("conflict_action")
    op.drop_index("ix_conflict_record_project_id", table_name="conflict_record")
    op.drop_table("conflict_record")
    op.drop_index("ix_team_assessment_project_id", table_name="team_assessment")
    op.drop_table("team_assessment")
    op.drop_index("ix_training_record_person_id", table_name="training_record")
    op.drop_table("training_record")
    op.drop_index("ix_acquisition_resource_type_id", table_name="acquisition")
    op.drop_index("ix_acquisition_project_id", table_name="acquisition")
    op.drop_table("acquisition")
    op.drop_index("ix_responsibility_assignment_person_id", table_name="responsibility_assignment")
    op.drop_index("ix_responsibility_assignment_task_id", table_name="responsibility_assignment")
    op.drop_index(
        "ix_responsibility_assignment_deliverable_id", table_name="responsibility_assignment"
    )
    op.drop_index("ix_responsibility_assignment_project_id", table_name="responsibility_assignment")
    op.drop_table("responsibility_assignment")
    op.drop_index("ix_resource_breakdown_parent_id", table_name="resource_breakdown")
    op.drop_index("ix_resource_breakdown_resource_type_id", table_name="resource_breakdown")
    op.drop_index("ix_resource_breakdown_project_id", table_name="resource_breakdown")
    op.drop_table("resource_breakdown")
    op.drop_index("ix_resource_type_project_id", table_name="resource_type")
    op.drop_table("resource_type")
