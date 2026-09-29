"""department operations: services, work queue, recurring work, service
levels, operating controls, incidents, improvements; budget_line scopes to a
department too

Seven new tables (``department_service``, ``work_request``, ``recurring_work``,
``service_level``, ``operating_control``, ``incident``, ``improvement``) for
``driftless.models.operations`` -- what a department runs day to day, mirroring
the way ``driftless.models.agile`` gave a project its own execution records.
``budget_line`` grows a nullable ``department_id`` alongside its existing
``project_id``, both now nullable, with a CHECK requiring exactly one set and a
second unique constraint scoping "one line per category" to a department the
same way the existing one scopes it to a project -- a department runs its own
operating budget rather than a twin table duplicating every column here.

The new tables are created before ``budget_line`` is altered, so the foreign
key the added column carries (``department``) already exists.
``batch_alter_table`` is dialect-conditional (``alembic/env.py``): SQLite
rebuilds ``budget_line`` copy-and-swap because it cannot ALTER a column
nullable or add a foreign key in place; Postgres alters in place.

Revision ID: 60b3833f0f32
Revises: b07e89a3a315
Create Date: 2026-08-27 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "60b3833f0f32"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "b07e89a3a315"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORK_REQUEST_STATUSES = ("requested", "queued", "in_progress", "done", "cancelled")
_WORK_REQUEST_PRIORITIES = ("low", "medium", "high", "urgent")
_CADENCES = ("weekly", "fortnightly", "monthly", "quarterly", "annual")
_INCIDENT_SEVERITIES = ("low", "medium", "high", "critical")
_INCIDENT_STATUSES = ("open", "investigating", "resolved", "closed")
_IMPROVEMENT_STATUSES = ("proposed", "in_progress", "done", "abandoned")


def upgrade() -> None:
    op.create_table(
        "department_service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_department_service_department_id", "department_service", ["department_id"])

    op.create_table(
        "work_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("requester", sa.String(length=200), nullable=False),
        sa.Column("raised_on", sa.Date(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _WORK_REQUEST_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint(
            "priority IN ({})".format(", ".join(f"'{p}'" for p in _WORK_REQUEST_PRIORITIES)),
            name="ck_priority",
        ),
        sa.CheckConstraint(
            "started_on IS NULL OR started_on >= raised_on", name="ck_work_request_started"
        ),
        sa.CheckConstraint(
            "done_on IS NULL OR done_on >= raised_on", name="ck_work_request_done_after_raised"
        ),
        sa.CheckConstraint(
            "done_on IS NULL OR started_on IS NULL OR done_on >= started_on",
            name="ck_work_request_done_after_started",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["department_service.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_request_department_id", "work_request", ["department_id"])
    op.create_index("ix_work_request_service_id", "work_request", ["service_id"])

    op.create_table(
        "recurring_work",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("last_completed_on", sa.Date(), nullable=True),
        sa.Column("next_due_on", sa.Date(), nullable=True),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "cadence IN ({})".format(", ".join(f"'{c}'" for c in _CADENCES)), name="ck_cadence"
        ),
        sa.CheckConstraint(
            "next_due_on IS NULL OR last_completed_on IS NULL OR next_due_on >= last_completed_on",
            name="ck_recurring_work_dates",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recurring_work_department_id", "recurring_work", ["department_id"])

    op.create_table(
        "service_level",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("measure", sa.String(length=200), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column("window", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            '"window" IN ({})'.format(", ".join(f"'{c}'" for c in _CADENCES)), name="ck_window"
        ),
        sa.CheckConstraint("target >= 0", name="ck_service_level_target"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["department_service.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_level_department_id", "service_level", ["department_id"])
    op.create_index("ix_service_level_service_id", "service_level", ["service_id"])

    op.create_table(
        "operating_control",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operating_control_department_id", "operating_control", ["department_id"])

    op.create_table(
        "incident",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("raised_on", sa.Date(), nullable=False),
        sa.Column("resolved_on", sa.Date(), nullable=True),
        sa.Column("root_cause", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "severity IN ({})".format(", ".join(f"'{s}'" for s in _INCIDENT_SEVERITIES)),
            name="ck_severity",
        ),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _INCIDENT_STATUSES)),
            name="ck_status",
        ),
        sa.CheckConstraint(
            "resolved_on IS NULL OR resolved_on >= raised_on", name="ck_incident_dates"
        ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["control_id"], ["operating_control.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_department_id", "incident", ["department_id"])
    op.create_index("ix_incident_control_id", "incident", ["control_id"])

    op.create_table(
        "improvement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("what", sa.String(length=2000), nullable=False),
        sa.Column("why", sa.String(length=2000), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _IMPROVEMENT_STATUSES)),
            name="ck_status",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_improvement_department_id", "improvement", ["department_id"])

    # budget_line: project_id becomes nullable, department_id is added nullable, and
    # a CHECK requires exactly one of the two -- SQLite cannot ALTER a column nullable
    # or add a foreign key in place, so batch mode rebuilds the table copy-and-move
    # (Postgres alters in place). The old unique constraint is untouched; the new one
    # gives a department the same "one line per category" scoping.
    with op.batch_alter_table("budget_line", schema=None) as batch_op:
        batch_op.alter_column("project_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_budget_line_department", "department", ["department_id"], ["id"]
        )
        batch_op.create_check_constraint(
            "ck_budget_line_one_scope",
            "(project_id IS NOT NULL) != (department_id IS NOT NULL)",
        )
        batch_op.create_unique_constraint(
            "uq_budget_line_department_category", ["department_id", "category"]
        )


def downgrade() -> None:
    with op.batch_alter_table("budget_line", schema=None) as batch_op:
        batch_op.drop_constraint("uq_budget_line_department_category", type_="unique")
        batch_op.drop_constraint("ck_budget_line_one_scope", type_="check")
        batch_op.drop_constraint("fk_budget_line_department", type_="foreignkey")
        batch_op.drop_column("department_id")
        batch_op.alter_column("project_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_improvement_department_id", table_name="improvement")
    op.drop_table("improvement")
    op.drop_index("ix_incident_control_id", table_name="incident")
    op.drop_index("ix_incident_department_id", table_name="incident")
    op.drop_table("incident")
    op.drop_index("ix_operating_control_department_id", table_name="operating_control")
    op.drop_table("operating_control")
    op.drop_index("ix_service_level_service_id", table_name="service_level")
    op.drop_index("ix_service_level_department_id", table_name="service_level")
    op.drop_table("service_level")
    op.drop_index("ix_recurring_work_department_id", table_name="recurring_work")
    op.drop_table("recurring_work")
    op.drop_index("ix_work_request_service_id", table_name="work_request")
    op.drop_index("ix_work_request_department_id", table_name="work_request")
    op.drop_table("work_request")
    op.drop_index("ix_department_service_department_id", table_name="department_service")
    op.drop_table("department_service")
