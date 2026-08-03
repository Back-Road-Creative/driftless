"""Plumbing shared by more than one ``driftless`` subcommand's CLI.

Kept below the domain CLIs (``assess.cli``, ``wizard.cli``) that both need the
same project lookup, so neither implicitly depends on the other's argparse
module — this module has no argparse of its own, only the one shared helper.
``driftless.cli`` imports nothing from here but :class:`AmbiguousProject`, which it
turns into an exit code at the CLI boundary.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from driftless.models import Project


class AmbiguousProject(Exception):
    """A reference that names more than one project.

    ``Project.name`` carries no unique constraint (two projects called "Website
    Rebuild" both POST 201), so a lookup by name can legitimately match several.
    Answering with the lowest id would assess, report on or write to the wrong
    project without saying so, and the operator cannot see the difference — so the
    lookup refuses, and ``driftless.cli`` prints the ids to choose between.
    """


def resolve_project(session: Session, ref: str) -> Project | None:
    """Find a project by numeric id or by exact name.

    Raises :class:`AmbiguousProject` when ``ref`` matches more than one.
    """
    conditions = [Project.name == ref]
    if ref.isdigit():
        conditions.append(Project.id == int(ref))
    matches = list(session.scalars(select(Project).where(or_(*conditions)).order_by(Project.id)))
    if len(matches) > 1:
        ids = ", ".join(str(project.id) for project in matches)
        raise AmbiguousProject(
            f"{ref!r} names {len(matches)} projects (ids {ids}) — pass the id, not the name"
        )
    return matches[0] if matches else None
