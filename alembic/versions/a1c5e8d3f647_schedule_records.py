"""schedule records: typed task dependencies, project calendars and calendar
exceptions, estimate scenarios

Four new tables for ``driftless.models.schedule`` -- the network and
duration-estimation layer PMBOK's Schedule Management knowledge area asks
for. ``task_dependency`` is a typed, self-referential precedence edge over
``task`` (``predecessor_task_id``/``successor_task_id``); ``project_calendar``
and ``calendar_exception`` carry a project's working pattern and its dated
exceptions; ``estimate_scenario`` is the stored form of one estimate a PM
ran, optionally naming the task it targets.

Revision ID: a1c5e8d3f647
Revises: 60b3833f0f32
Create Date: 2026-08-27 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c5e8d3f647"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "60b3833f0f32"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEPENDENCY_KINDS = ("FS", "SS", "FF", "SF")
_ESTIMATE_TARGETS = ("duration", "cost", "resource")
_ESTIMATE_KINDS = ("analogous", "parametric", "three_point", "bottom_up")


def upgrade() -> None:
    op.create_table(
        "task_dependency",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("predecessor_task_id", sa.Integer(), nullable=False),
        sa.Column("successor_task_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=2), nullable=False),
        sa.Column("lag_days", sa.Integer(), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{k}'" for k in _DEPENDENCY_KINDS)), name="ck_kind"
        ),
        sa.CheckConstraint(
            "predecessor_task_id != successor_task_id", name="ck_task_dependency_not_self"
        ),
        sa.ForeignKeyConstraint(["predecessor_task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["successor_task_id"], ["task.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_dependency_predecessor_task_id", "task_dependency", ["predecessor_task_id"]
    )
    op.create_index(
        "ix_task_dependency_successor_task_id", "task_dependency", ["successor_task_id"]
    )

    op.create_table(
        "project_calendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("working_days", sa.Integer(), nullable=False, server_default="31"),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_calendar_project_id", "project_calendar", ["project_id"])

    op.create_table(
        "calendar_exception",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("calendar_id", sa.Integer(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("working", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("calendar_id", "on_date", name="uq_calendar_exception_date"),
        sa.ForeignKeyConstraint(["calendar_id"], ["project_calendar.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_exception_calendar_id", "calendar_exception", ["calendar_id"])

    op.create_table(
        "estimate_scenario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=20), nullable=False),
        sa.Column("subject_task_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("inputs", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("basis", sa.String(length=2000), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "target IN ({})".format(", ".join(f"'{t}'" for t in _ESTIMATE_TARGETS)),
            name="ck_target",
        ),
        sa.CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{k}'" for k in _ESTIMATE_KINDS)), name="ck_kind"
        ),
        sa.CheckConstraint("low IS NULL OR low <= value", name="ck_estimate_scenario_low"),
        sa.CheckConstraint("high IS NULL OR high >= value", name="ck_estimate_scenario_high"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["subject_task_id"], ["task.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_estimate_scenario_project_id", "estimate_scenario", ["project_id"])
    op.create_index(
        "ix_estimate_scenario_subject_task_id", "estimate_scenario", ["subject_task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_estimate_scenario_subject_task_id", table_name="estimate_scenario")
    op.drop_index("ix_estimate_scenario_project_id", table_name="estimate_scenario")
    op.drop_table("estimate_scenario")
    op.drop_index("ix_calendar_exception_calendar_id", table_name="calendar_exception")
    op.drop_table("calendar_exception")
    op.drop_index("ix_project_calendar_project_id", table_name="project_calendar")
    op.drop_table("project_calendar")
    op.drop_index("ix_task_dependency_successor_task_id", table_name="task_dependency")
    op.drop_index("ix_task_dependency_predecessor_task_id", table_name="task_dependency")
    op.drop_table("task_dependency")
