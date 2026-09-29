"""No wizard producer invents a value its caller did not supply (F-G1).

The narrative kinds were fixed to refuse a missing body; every other producible kind still
substituted a hardcoded one. The presence checks are content-blind ``bool(rows)``, so one
fabricated row marks that output produced for good and the honest value is never asked for
again.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import mapping
from driftless.wizard import cli as wizard_cli
from driftless.wizard.cli import MissingField, produce, producible_kinds, seed_fields
from tests.conftest import AS_OF


@pytest.fixture
def bare(db: Session) -> m.Project:
    """A project with nothing on it: no baseline, so the baseline kinds reach their
    fields instead of stopping at the re-baseline guard."""
    project = m.Project(name="Bare", portfolio=m.Portfolio(name="C", business=m.Business(name="B")))
    db.add(project)
    db.commit()
    return project


@pytest.mark.parametrize("kind", producible_kinds())
def test_every_producible_kind_refuses_the_fields_it_was_not_given(
    db: Session, bare: m.Project, kind: str
) -> None:
    """Asked for with nothing, a producer refuses and writes no row — for EVERY kind, so a
    producer added later is covered by this test on the commit that adds it."""
    with pytest.raises(MissingField):
        produce(db, bare, kind, {}, AS_OF, "test")
    db.rollback()
    assert not mapping.resolve(kind, bare, db, AS_OF).present, "a refusal wrote a row"


@pytest.mark.parametrize("kind", producible_kinds())
def test_seed_fields_answers_every_producible_kind(db: Session, bare: m.Project, kind: str) -> None:
    """The placeholders live on the seeding side now, so an unattended run still converges,
    and ``seed_fields`` reads the table ``required_fields`` does: no kind can require a
    field nothing seeds."""
    produce(db, bare, kind, seed_fields(kind, AS_OF), AS_OF, "test")
    assert mapping.resolve(kind, bare, db, AS_OF).present


def test_no_producer_carries_a_fallback_value() -> None:
    """Structural, over the module's own syntax tree: a two-argument ``fields.get`` IS the
    bug — a value the caller did not choose, reaching the store under their name. The
    one-argument form stays legal (a NULL in a nullable column claims nothing). A shape,
    not a list of strings, so no new placeholder slips past it."""
    source = Path(inspect.getsourcefile(wizard_cli) or "").read_text()
    invented = [
        ast.unparse(node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and getattr(node.func.value, "id", "") == "fields"
        and len(node.args) > 1
    ]
    assert not invented, f"a producer still invents a value: {invented}"
