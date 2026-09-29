"""Declarative list filters, derived off the mapper -- never a hand-kept table.

``GET /businesses?bogus=1`` used to answer 200 with the whole table: nothing in the
package looked at the query string at all. These pin the fix branch by branch: a
foreign key column scopes to its parent, a ``status``/``rag_status`` column filters
by equality, an unrecognised name is refused rather than silently ignored, and the
filter narrows BOTH the page and the ``X-Total-Count`` header -- the one place a
half-applied filter would be invisible.

A ``Date`` column also takes an inclusive ``_from``/``_to`` pair, covered at the end
of this file. A ``DateTime`` column takes neither, and that refusal is tested too:
the exclusion is a decision about system-time stamps, so it needs to fail loudly
rather than quietly resolve to "no such parameter" for some later reader to "fix".
"""

import csv
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as bound:
        yield bound
    app.dependency_overrides.clear()


def _post(bound: TestClient, path: str, **body: Any) -> int:
    response = bound.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    """Two portfolios and two projects so a parent-scope filter has something to
    exclude at two different levels of the hierarchy, and tasks in every status a
    later test asks for."""
    business = _post(client, "/businesses", name="Back Road Creative")
    portfolio = _post(client, "/portfolios", name="Content Brands", business_id=business)
    other_portfolio = _post(client, "/portfolios", name="Other Brands", business_id=business)
    project = _post(client, "/projects", name="GMS", portfolio_id=portfolio)
    _post(client, "/projects", name="Elsewhere", portfolio_id=other_portfolio)
    stream = _post(client, "/workstreams", name="Edit", project_id=project)
    other_stream = _post(client, "/workstreams", name="Edit 2", project_id=project)
    task_kw = {"estimate_unit": "hours"}
    _post(
        client, "/tasks", name="Colour grade", workstream_id=stream, status="in_progress", **task_kw
    )
    _post(client, "/tasks", name="Deliver master", workstream_id=stream, status="done", **task_kw)
    _post(client, "/tasks", name="Other task", workstream_id=other_stream, status="done", **task_kw)
    return client


def test_an_unfiltered_list_is_unchanged(seeded: TestClient) -> None:
    """The empty-filter case must answer exactly what it always did."""
    response = seeded.get("/tasks")
    assert len(response.json()) == 3
    assert response.headers["x-total-count"] == "3"


def test_a_foreign_key_column_scopes_to_its_parent(seeded: TestClient) -> None:
    response = seeded.get("/tasks", params={"workstream_id": 1})
    assert response.status_code == 200, response.text
    assert [row["name"] for row in response.json()] == ["Colour grade", "Deliver master"]
    assert response.headers["x-total-count"] == "2", "the filtered total, never the whole table"


def test_the_same_derivation_filters_a_second_resource(seeded: TestClient) -> None:
    """Not a fact about tasks: the vocabulary comes off every model's own mapper."""
    response = seeded.get("/projects", params={"portfolio_id": 1})
    assert [row["name"] for row in response.json()] == ["GMS"]
    assert response.headers["x-total-count"] == "1"


def test_a_status_column_filters_by_equality(seeded: TestClient) -> None:
    response = seeded.get("/tasks", params={"status": "done"})
    assert [row["name"] for row in response.json()] == ["Deliver master", "Other task"]
    assert response.headers["x-total-count"] == "2"


def test_an_out_of_vocabulary_status_value_is_an_empty_page_not_a_422(
    seeded: TestClient,
) -> None:
    """The CHECK constraint guarantees no row holds a status this vocabulary refuses,
    so asking for one is a legal, empty answer -- not a validation error."""
    response = seeded.get("/tasks", params={"status": "bogus"})
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["x-total-count"] == "0"


def test_the_csv_branch_shares_the_same_filtered_window(seeded: TestClient) -> None:
    response = seeded.get("/tasks", params={"status": "done", "format": "csv"})
    rows = list(csv.reader(io.StringIO(response.text)))
    assert len(rows) == 3, "header row plus the two filtered rows, never the whole table"
    assert response.headers["x-total-count"] == "2"


def test_an_unknown_query_parameter_is_refused(seeded: TestClient) -> None:
    response = seeded.get("/tasks", params={"bogus": "1"})
    assert response.status_code == 422
    assert "bogus" in response.json()["detail"]


def test_changed_since_is_not_a_recognised_filter(seeded: TestClient) -> None:
    """No domain row carries a system-time modification stamp (docs/temporal-model.md);
    the vocabulary derived off the mapper has no such column to find, so this is exactly
    as unrecognised as any other misspelling."""
    response = seeded.get("/tasks", params={"changed_since": "2026-01-01"})
    assert response.status_code == 422


def test_a_resource_with_no_filterable_columns_still_lists_and_still_refuses_unknown(
    seeded: TestClient,
) -> None:
    assert seeded.get("/businesses").status_code == 200
    refused = seeded.get("/businesses", params={"bogus": "1"})
    assert refused.status_code == 422
    assert "bogus" in refused.json()["detail"]


@pytest.fixture
def dated(client: TestClient) -> TestClient:
    """Three issues raised on three different days, so a range has a row to exclude
    beyond each end and one strictly inside."""
    business = _post(client, "/businesses", name="Back Road Creative")
    portfolio = _post(client, "/portfolios", name="Content Brands", business_id=business)
    project = _post(client, "/projects", name="GMS", portfolio_id=portfolio)
    for day in ("2026-01-01", "2026-01-15", "2026-01-31"):
        _post(client, "/issues", project_id=project, description=f"Raised {day}", raised_on=day)
    return client


def test_a_date_range_includes_both_ends(dated: TestClient) -> None:
    """Inclusive is the reading a caller asks for, and the end an exclusive bound would
    drop is the one they would never notice missing."""
    response = dated.get("/issues?raised_on_from=2026-01-01&raised_on_to=2026-01-31")

    assert response.status_code == 200, response.text
    assert [row["raised_on"] for row in response.json()] == [
        "2026-01-01",
        "2026-01-15",
        "2026-01-31",
    ]


def test_a_date_range_narrows_the_page_and_the_count_together(dated: TestClient) -> None:
    """Pulled in by one day at each end, so the rows an off-by-one would keep are the
    exact rows this drops. ``X-Total-Count`` must narrow with the page: a filtered list
    reporting the unfiltered total is a truncated answer that looks complete."""
    response = dated.get("/issues?raised_on_from=2026-01-02&raised_on_to=2026-01-30")

    assert [row["raised_on"] for row in response.json()] == ["2026-01-15"]
    assert response.headers["X-Total-Count"] == "1"


def test_one_bound_leaves_the_other_end_open(dated: TestClient) -> None:
    later = dated.get("/issues?raised_on_from=2026-01-15")
    earlier = dated.get("/issues?raised_on_to=2026-01-15")

    assert [row["raised_on"] for row in later.json()] == ["2026-01-15", "2026-01-31"]
    assert [row["raised_on"] for row in earlier.json()] == ["2026-01-01", "2026-01-15"]


def test_a_timestamp_column_takes_no_range_at_all(dated: TestClient) -> None:
    """``signed_at`` records when the system wrote the row, not when anything happened,
    and a ``date`` bound against it compares to midnight -- so a ``_to`` would silently
    drop the last day it named. Excluded by column TYPE rather than by a list of names,
    and refused like any other unrecognised parameter."""
    refused = dated.get("/sign-offs?signed_at_from=2026-01-01")

    assert refused.status_code == 422, refused.text
    assert "signed_at_from" in refused.json()["detail"]
