"""Every foreign key in the schema must be visible to the delete guard.

``driftless.api.app._delete`` names what blocks a delete by reading the parent
mapper's ONETOMANY relationships. A foreign key with no covering relationship on
the parent is therefore invisible to it: the delete falls through to the generic
``IntegrityError`` handler and answers an opaque "constraint violation" instead
of naming the child an operator has to clear. Nothing is lost — SQLite FK
enforcement is on — but the guard's claim to name every child is false, and the
operator is left guessing.

The first test closes the class rather than the five instances that prompted it:
it enumerates the FK edges off ``Base.metadata`` and asserts each one is covered
by a relationship the guard can see, so a model added later without a
parent-side back-reference fails here rather than in front of an operator. The
two that follow prove the message that operator actually reads.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.orm.interfaces import ONETOMANY

import driftless.models  # noqa: F401 — importing registers every table on the metadata
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory

Edge = tuple[str, str, str]  # (child table, child column, parent table)

# Edges deliberately left unguarded, each with the reason it is safe to lose
# sight of. Empty on purpose: every FK in this schema is a real parent/child
# link whose loss is data loss. If one ever legitimately should not block a
# delete, name it here with its reason — never widen the assertion below.
UNGUARDED: frozenset[Edge] = frozenset()


def _named(column: Any) -> tuple[str, str]:
    """A column's ``(table name, column name)``.

    Typed ``Any`` deliberately: SQLAlchemy widens both the FK target and a
    relationship's local/remote pairs to ``ColumnElement``, which declares
    neither attribute, though every column here is a real ``Column``.
    """
    return str(column.table.name), str(column.name)


def _fk_edges() -> set[Edge]:
    """Every foreign key in the schema, read straight off the metadata."""
    edges: set[Edge] = set()
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                parent, _ = _named(foreign_key.column)
                edges.add((table.name, column.name, parent))
    return edges


def _guarded_edges() -> set[Edge]:
    """Every edge some parent mapper exposes as a ONETOMANY relationship.

    This is exactly what ``_delete`` reflects over, so an edge missing from
    here is an edge the refusal cannot name.
    """
    edges: set[Edge] = set()
    for mapper in Base.registry.mappers:
        for rel in mapper.relationships:
            if rel.direction is not ONETOMANY:
                continue
            for local, remote in rel.local_remote_pairs or ():  # typed optional, never None here
                child, child_column = _named(remote)
                parent, _ = _named(local)
                edges.add((child, child_column, parent))
    return edges


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client over a throwaway SQLite file — FK enforcement is on, as in production."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_every_foreign_key_is_visible_to_the_delete_guard() -> None:
    """No FK may hide from the guard — the next model without a back-reference fails here."""
    found = _fk_edges()
    assert found, "the enumeration found no foreign keys — the helper is broken, not the schema"

    uncovered = sorted(found - _guarded_edges() - UNGUARDED)

    assert not uncovered, (
        "these (child table, child column, parent table) edges have no ONETOMANY "
        "relationship on the parent, so deleting that parent answers an opaque "
        f"'constraint violation' instead of naming the child: {uncovered}"
    )


def test_a_business_with_a_department_is_refused_by_name(client: TestClient) -> None:
    business = _create(client, "/businesses", name="Back Road Creative")
    _create(client, "/departments", name="Production", business_id=business)

    refused = client.delete(f"/businesses/{business}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Business {business} still has departments", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_a_risk_with_an_issue_is_refused_by_name(client: TestClient) -> None:
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    project = _create(client, "/projects", name="GoMoveShift 2026", portfolio_id=portfolio)
    risk = _create(
        client,
        "/risks",
        project_id=project,
        description="Lead editor turnover mid-season",
        probability=0.5,
        impact=1000.0,
    )
    _create(
        client,
        "/issues",
        project_id=project,
        description="The lead editor left",
        raised_on="2026-01-05",
        risk_id=risk,
    )

    refused = client.delete(f"/risks/{risk}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Risk {risk} still has issues", (
        "an issue born of a risk blocks the risk, and the refusal says so"
    )
