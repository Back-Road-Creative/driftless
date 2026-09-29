"""A list endpoint answers a bounded window, never "every row of this table".

``GET /businesses`` used to load the whole table into memory and serialize it, and
``?format=csv`` built the entire export as one string first — so a store holding a
commercial number of rows turned one ordinary request into an unbounded allocation. The
bound is a server *default* plus a server *maximum*: a client can page through
everything, and cannot ask for the pathological read back. The numbers here are the
contract, written out rather than imported from the module under test, so a cap quietly
raised to "all rows" fails this file rather than agreeing with itself."""

import csv
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory

DEFAULT_CAP = 500  # rows a list answers when the caller asks for no window
HARD_MAX = 2000  # the ceiling a caller cannot raise, whatever ?limit says
SEEDED = DEFAULT_CAP + 3


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client over a throwaway store holding more rows than the default cap."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as seed:
        seed.add_all(m.Business(name=f"Business {n:04d}") for n in range(SEEDED))
        seed.commit()

    def _session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as bound:
        yield bound
    app.dependency_overrides.clear()


def _window(res: Any) -> tuple[int, int, int]:
    """What the answer says about itself: total rows, the window served, its offset."""
    head = res.headers
    return int(head["x-total-count"]), int(head["x-limit"]), int(head["x-offset"])


def test_a_list_answers_the_default_cap_and_says_how_many_rows_there_are(
    client: TestClient,
) -> None:
    response = client.get("/businesses")

    assert len(response.json()) == DEFAULT_CAP, "the whole table is not the answer to a bare GET"
    assert _window(response) == (SEEDED, DEFAULT_CAP, 0), "a truncated list has to say so"


def test_the_rows_past_the_cap_are_reachable_by_offset(client: TestClient) -> None:
    """Bounded, not lossy: paging reaches every row, and no row is served twice."""
    first = client.get("/businesses").json()
    rest = client.get("/businesses", params={"offset": DEFAULT_CAP})
    names = [f"Business {n:04d}" for n in range(DEFAULT_CAP, SEEDED)]

    assert [row["name"] for row in rest.json()] == names
    assert _window(rest) == (SEEDED, DEFAULT_CAP, DEFAULT_CAP)
    assert not {row["id"] for row in first} & {row["id"] for row in rest.json()}


def test_a_client_cannot_raise_the_window_past_the_server_maximum(client: TestClient) -> None:
    """The cap is the server's, not the caller's — and the clamp only ever narrows."""
    greedy = client.get("/businesses", params={"limit": HARD_MAX * 50})
    asked = client.get("/businesses", params={"limit": 2, "offset": 1})

    assert _window(greedy)[1] == HARD_MAX, "a client-supplied limit is clamped, never honoured"
    assert len(greedy.json()) == SEEDED  # the store holds fewer rows than the ceiling
    assert [row["name"] for row in asked.json()] == ["Business 0001", "Business 0002"]
    assert _window(asked) == (SEEDED, 2, 1), "under the maximum the caller decides"


def test_the_csv_export_is_bounded_by_the_same_window(client: TestClient) -> None:
    """``?format=csv`` materializes the whole answer as one string — so it is bounded too."""
    exported = client.get("/businesses", params={"format": "csv"})
    rows = list(csv.reader(io.StringIO(exported.text)))

    assert exported.headers["content-type"].startswith("text/csv")
    assert len(rows) == DEFAULT_CAP + 1, "header row plus the window, never the whole table"
    assert _window(exported) == (SEEDED, DEFAULT_CAP, 0)


def test_a_cursor_pages_through_without_repeating_or_skipping(client: TestClient) -> None:
    """Three pages walked by cursor cover exactly the rows offset would, in order."""
    walked: list[int] = []
    cursor: str | None = None
    for _ in range(3):
        query = "/businesses?limit=4" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(query)
        assert page.status_code == 200, page.text
        walked += [row["id"] for row in page.json()]
        cursor = page.headers["x-next-cursor"]

    assert walked == list(range(1, 13)), "no row seen twice, none stepped over"
    assert len(set(walked)) == len(walked)


def test_the_final_page_carries_no_next_cursor(client: TestClient) -> None:
    """Absence of the header is the end-of-collection signal, so it must not appear on a
    page that happens to come back exactly full -- the boundary a "page looks full, so
    assume there is more" implementation gets wrong."""
    final = client.get(f"/businesses?limit=5&cursor={SEEDED - 5}")

    assert len(final.json()) == 5, "an exactly-full last page is the case under test"
    assert "x-next-cursor" not in final.headers


def test_a_cursor_does_not_step_over_a_row_when_an_earlier_one_is_deleted(
    client: TestClient,
) -> None:
    """The reason a cursor exists at all. With ``?offset``, deleting a row from an
    already-read page slides every later row down one, and the next offset page steps
    straight over whatever moved into the gap. A cursor names the last row SEEN, so a
    shift behind it cannot move the boundary."""
    seen = [row["id"] for row in client.get("/businesses?limit=2").json()]
    assert client.delete(f"/businesses/{seen[0]}").status_code < 300

    by_offset = client.get("/businesses?limit=2&offset=2").json()
    by_cursor = client.get(f"/businesses?limit=2&cursor={seen[-1]}").json()

    assert by_cursor[0]["id"] == seen[-1] + 1, "the row immediately after the last one seen"
    assert by_offset[0]["id"] != by_cursor[0]["id"], (
        "offset stepped over a row once the collection shrank -- the failure cursor fixes"
    )


def test_cursor_and_offset_together_are_refused(client: TestClient) -> None:
    """Two different pagination models. Honouring one silently would answer 200 with a
    page the caller reads as the one they asked for."""
    refused = client.get("/businesses?limit=2&offset=2&cursor=2")

    assert refused.status_code == 422, refused.text
    assert "cursor" in refused.json()["detail"]
