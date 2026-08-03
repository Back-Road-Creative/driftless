"""Report-engine contract: documents are discovered not registered, every render
is threaded through an explicit as-of, and the same inputs render byte-identically."""

from datetime import date

import pytest
from jinja2 import UndefinedError
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import gather, iter_documents, render_document
from driftless.report.engine import render

AS_OF = date(2026, 3, 31)  # matches the conftest seed's baseline finish
EARLY = date(2025, 12, 1)  # before the baseline accrues and before any spend


def test_documents_are_discovered_not_registered() -> None:
    assert "cost-evm" in [doc.SLUG for doc in iter_documents()]


def test_the_same_inputs_render_byte_identically(db: Session, project: m.Project) -> None:
    assert render_document("cost-evm", db, project, AS_OF) == render_document(
        "cost-evm", db, project, AS_OF
    )


def test_the_as_of_date_is_threaded_not_read_from_the_clock(
    db: Session, project: m.Project
) -> None:
    now = render_document("cost-evm", db, project, AS_OF)
    earlier = render_document("cost-evm", db, project, EARLY)
    assert now != earlier, "a different as-of must change the report"
    assert AS_OF.isoformat() in now
    assert "n/a" in earlier, "CPI/SPI are undefined before any spend or accrual"


def test_a_name_no_document_passed_raises_instead_of_rendering_blank(project: m.Project) -> None:
    """A template variable nobody supplied must stop the render, not print ``''``.

    With Jinja's default ``Undefined`` a misspelt ``{{ completness }}`` rendered
    ``**Completeness:** `` and every test in the suite still passed — the figure
    simply vanished. Pinning one document's figure would only catch that document;
    the environment catches every template, including ones not written yet."""
    context = {"title": "Process Map", "project": project, "as_of": AS_OF, "rows": []}
    with pytest.raises(UndefinedError, match="completeness"):
        render("process_map.md", context)  # the one name the context withholds


def test_every_document_renders_with_no_undefined_name(db: Session, project: m.Project) -> None:
    """Walk every document the way ``report all`` does, dispatching on ``SCOPE``.

    A template reached only through the CLI is exactly where a withheld name would
    hide, so strictness is proved against the whole set, not the tested few."""
    for module in iter_documents():
        rendered = (
            module.render(db, AS_OF)
            if getattr(module, "SCOPE", "project") == "business"
            else module.render(db, project, AS_OF)
        )
        assert rendered.startswith("# "), f"{module.SLUG} rendered no heading"


def test_portfolio_nodes_mirror_the_dashboard_tree(db: Session, project: m.Project) -> None:
    tree = gather.portfolio_nodes(db, AS_OF)
    assert [node.name for node in tree] == ["Content Brands"]
    (leaf,) = tree[0].children
    assert leaf.name == "GMS"
    assert leaf.metrics is not None and leaf.metrics.budget == 1000  # calc's BAC on the leaf
