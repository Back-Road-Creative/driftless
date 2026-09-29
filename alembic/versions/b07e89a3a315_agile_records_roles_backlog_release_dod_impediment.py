"""agile records: roles, backlog items, releases, DoD, impediments; sprint gains a goal

Five new tables (``project_role``, ``backlog_item``, ``release``,
``definition_of_done_item``, ``impediment``) plus six columns added to the
existing ``sprint`` table -- ``goal``, ``release_id`` and the review/
retrospective evidence pair -- because an "iteration" IS a sprint
(``driftless.models.agile`` module docstring), not a parallel table.
``release`` is created before ``sprint`` gains its foreign key into it, and
dropped after that key is removed, so the chain applies and reverses cleanly.

Revision ID: b07e89a3a315
Revises: dcb8fc906970
Create Date: 2026-08-27 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b07e89a3a315"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "dcb8fc906970"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGILE_ROLES = ("product_owner", "scrum_master", "developer", "stakeholder_proxy")
_BACKLOG_ITEM_STATUSES = ("proposed", "ready", "in_progress", "done")
_BACKLOG_ITEM_PRIORITIES = ("must_have", "should_have", "could_have", "wont_have")
_RELEASE_STATUSES = ("planned", "released", "cancelled")
_IMPEDIMENT_STATUSES = ("open", "in_progress", "resolved", "closed")


def upgrade() -> None:
    op.create_table(
        "project_role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("holder", sa.String(length=200), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "role IN ({})".format(", ".join(f"'{r}'" for r in _AGILE_ROLES)), name="ck_role"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_role_project_id", "project_role", ["project_id"])

    op.create_table(
        "backlog_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("story_points", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _BACKLOG_ITEM_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint(
            "priority IN ({})".format(", ".join(f"'{p}'" for p in _BACKLOG_ITEM_PRIORITIES)),
            name="ck_priority",
        ),
        sa.CheckConstraint(
            "story_points IS NULL OR story_points >= 0", name="ck_backlog_item_points"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backlog_item_project_id", "backlog_item", ["project_id"])

    op.create_table(
        "release",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _RELEASE_STATUSES)),
            name="ck_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_release_project_id", "release", ["project_id"])

    op.create_table(
        "definition_of_done_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_definition_of_done_item_project_id", "definition_of_done_item", ["project_id"]
    )

    op.create_table(
        "impediment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("raised_by", sa.String(length=200), nullable=False),
        sa.Column("raised_on", sa.Date(), nullable=False),
        sa.Column("resolved_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _IMPEDIMENT_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint(
            "resolved_on IS NULL OR resolved_on >= raised_on", name="ck_impediment_dates"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_impediment_project_id", "impediment", ["project_id"])

    with op.batch_alter_table("sprint", schema=None) as batch_op:
        batch_op.add_column(sa.Column("goal", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("release_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("review_held_on", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("review_notes", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("retrospective_held_on", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("retrospective_notes", sa.String(length=2000), nullable=True))
        batch_op.create_foreign_key("fk_sprint_release", "release", ["release_id"], ["id"])
        batch_op.create_index("ix_sprint_release_id", ["release_id"])


def downgrade() -> None:
    with op.batch_alter_table("sprint", schema=None) as batch_op:
        batch_op.drop_index("ix_sprint_release_id")
        batch_op.drop_constraint("fk_sprint_release", type_="foreignkey")
        batch_op.drop_column("retrospective_notes")
        batch_op.drop_column("retrospective_held_on")
        batch_op.drop_column("review_notes")
        batch_op.drop_column("review_held_on")
        batch_op.drop_column("release_id")
        batch_op.drop_column("goal")

    op.drop_index("ix_impediment_project_id", table_name="impediment")
    op.drop_table("impediment")
    op.drop_index("ix_definition_of_done_item_project_id", table_name="definition_of_done_item")
    op.drop_table("definition_of_done_item")
    op.drop_index("ix_release_project_id", table_name="release")
    op.drop_table("release")
    op.drop_index("ix_backlog_item_project_id", table_name="backlog_item")
    op.drop_table("backlog_item")
    op.drop_index("ix_project_role_project_id", table_name="project_role")
    op.drop_table("project_role")
