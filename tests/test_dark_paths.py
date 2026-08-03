"""Three load-bearing fallbacks the rest of the suite never walks.

Each one only runs when something ordinary has already gone sideways, so nothing
in the happy path touches it: a refactor could delete any of the three and every
other test would still pass. What each protects is worth a test on its own — the
gate must answer JSON rather than 500 when it cannot read the app's own page
routes, the report engine must name a slug no document claims rather than hand
back nothing, and the program guard must let an ordinary edit through instead of
refusing every program that has projects.

Each is driven through its public surface — a request through the test client,
or the exported function — so what is pinned is the behaviour, not a line number.
"""

import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from driftless.api import secure
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Project
from driftless.report import render_document

TOKEN = "s3cr3t-token"
PAGE = "/"  # the dashboard: a real page route, which is what makes the walk matter
# The gate's JSON body, spelled out rather than read off the module, so a refactor
# that changes what a script parses has to change this literal to stay green.
UNAUTHENTICATED = b'{"detail":"missing or invalid bearer token"}'
AS_OF = date(2026, 3, 31)


class _UnreadableRoutes:
    """An inner app whose route table the gate's walk cannot read.

    Stands in for the shape this actually guards against: a Starlette or FastAPI
    version that renames or re-wraps the route table under the gate. The gate
    cannot tell that apart from this, and has to answer both the same way.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner

    @property
    def routes(self) -> object:
        raise RuntimeError("a route-table shape this walk does not know")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._inner(scope, receive, send)  # type: ignore[operator]


def test_a_route_table_that_cannot_be_walked_answers_json_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A gate that raises is worse than a gate that does not know the surface.

    The walk runs once, at construction, so a shape it cannot read would otherwise
    500 every request that follows — including the sign-in redirect a browser needs
    to recover. It must cost exactly one warning and a refusal in JSON instead.
    """
    seeing = TestClient(secure.TokenGate(app, TOKEN), follow_redirects=False)
    assert seeing.get(PAGE).status_code == 303, "control: a readable table sends a page to /login"

    with caplog.at_level(logging.WARNING, logger="driftless.secure"):
        blind = TestClient(secure.TokenGate(_UnreadableRoutes(app), TOKEN), follow_redirects=False)
    refused = blind.get(PAGE)
    assert (refused.status_code, refused.content) == (401, UNAUTHENTICATED)
    assert "refusals will answer JSON" in caplog.text, "a gate flying blind has to say so"


def test_an_unknown_report_slug_names_it_rather_than_rendering_nothing(
    db: Session, project: Project
) -> None:
    """Documents are discovered, not registered, so a slug nothing claims can only be
    found by exhausting the walk. Falling off the end quietly would return ``None`` —
    the CLI would write an empty report file and exit 0, which is worse than a crash.
    """
    assert render_document("schedule", db, project, AS_OF).strip(), "the walk finds real documents"
    with pytest.raises(KeyError, match="no report document with slug 'schedul'"):
        render_document("schedul", db, project, AS_OF)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client over a throwaway SQLite file — a file, not memory, because TestClient
    serves the request on another thread that would otherwise see an empty database."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as bound:
        yield bound
    app.dependency_overrides.clear()


def _created(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_an_edit_that_does_not_move_a_program_keeps_its_projects(client: TestClient) -> None:
    """The guard refuses a *move*, never an edit.

    Renaming a program changes no portfolio, so the rule has nothing to check and the
    409 that protects the rollup must not fire — without the early exit every ordinary
    edit to a program that has projects would be refused. Restating the portfolio the
    program already lives in is the same non-move, spelled with the key present.
    """
    business = _created(client, "/businesses", name="Back Road Creative")
    home = _created(client, "/portfolios", name="Home", business_id=business)
    program = _created(client, "/programs", name="Video", portfolio_id=home)
    project = _created(client, "/projects", name="GMS", portfolio_id=home, program_id=program)

    renamed = client.patch(f"/programs/{program}", json={"name": "Video Ops"})
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["name"], renamed.json()["portfolio_id"]) == ("Video Ops", home)

    restated = client.patch(f"/programs/{program}", json={"portfolio_id": home})
    assert restated.status_code == 200, "the portfolio it already lives in is not a move"
    assert client.get(f"/projects/{project}").json()["program_id"] == program
