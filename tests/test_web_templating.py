"""The page environment is STRICT: a name no route passed raises, never renders blank.

Two gates. The first is the environment itself, asserted on a real page template
rendered twice — once with its whole context, once with one name withheld — so the
failure is the withheld name and nothing else. The second walks every GET page the
app registers (the route table ``test_web_csrf`` keeps) against two stores: one with
work under every row, and one with the rows and nothing under them. The empty half is
the point. A page reaches its ``{% if %}`` else-branch only when there is nothing to
draw, and under Jinja's default ``Undefined`` a name that branch alone mentions
rendered as the empty string on a page nobody re-read — which is how four of these
hid. Neither gate carries a per-template exemption: there is one environment, and it
is strict.
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jinja2 import UndefinedError
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.templating import TEMPLATES
import test_web_pages
from test_web_csrf import SAMPLE, _web_paths

WALK = f"?as_of={test_web_pages.AS_OF.isoformat()}&q=GMS"  # every page takes both, or ignores them
# What ``base.html`` asks of the request on every page: the path it marks aria-current
# from, and the cookie jar the nav reads sign-in off. Enough shell to render a page
# template directly, so the gate below turns on the ONE name it withholds.
SHELL: dict[str, Any] = {
    "request": SimpleNamespace(url=SimpleNamespace(path="/org/departments"), cookies={}),
    "csrf_token": "not-a-real-token",
}
DEPARTMENTS: dict[str, Any] = {"as_of": test_web_pages.AS_OF.isoformat(), "departments": []}


def test_a_name_no_page_passed_raises_instead_of_rendering_blank() -> None:
    """``departments`` withheld from the page that loops it: the render must STOP.

    Deliberately a name reached on the empty-state branch — ``{% if departments %}``
    is false either way, so under the default ``Undefined`` this rendered the whole
    designed page and returned 200 with nothing missing that a reader could see.
    The first render is asserted so the second one's failure can only be the
    withheld name, never a shell this test builds wrong."""
    page = TEMPLATES.env.get_template("departments.html")
    assert page.render(SHELL | DEPARTMENTS), "the full context still renders"
    with pytest.raises(UndefinedError, match="departments"):
        page.render(SHELL | {"as_of": DEPARTMENTS["as_of"]})


def _rows(session: Session, populated: bool) -> None:
    """One row of every kind the walk addresses by id, with or without work under it.

    ``populated`` reuses the seed the rest of the web suite walks (a baselined project
    overspending, so every figure-bearing surface has something to draw); the other
    half leaves the same rows bare, which is the only way an empty-state branch is
    ever rendered."""
    if populated:
        test_web_pages._seed(session)
    else:
        session.add(
            m.Project(
                name="GMS",
                portfolio=m.Portfolio(name="Content", business=m.Business(name="BRC")),
                delivery_mode="predictive",
            )
        )
        session.commit()
    project = session.scalars(select(m.Project)).one()
    project.program = m.Program(name="Reels", portfolio=project.portfolio)
    session.add(m.Department(name="Post", business=project.portfolio.business))
    session.commit()


@pytest.fixture(params=[True, False], ids=["populated", "empty"])
def browser(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[TestClient]:
    """A client over each store, https as production serves (the CSRF cookie is Secure)."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as setup:
        _rows(setup, bool(request.param))
    with factory() as session:
        real_app.dependency_overrides[get_session] = lambda: session
        with TestClient(real_app, base_url="https://testserver") as client:
            yield client
        real_app.dependency_overrides.clear()


@pytest.mark.parametrize("shape", sorted(_web_paths("GET")))
def test_every_page_renders_with_no_undefined_name(browser: TestClient, shape: str) -> None:
    """Walked off the app's own route table, so a page mounted next year is walked the
    day it is mounted — and walked on both stores, because a name only the empty-state
    branch mentions is invisible to every walk that seeds rows first."""
    assert "{}" not in shape or shape in SAMPLE, f"{shape} needs a reachable id in SAMPLE"
    page = browser.get(shape.replace("{}", SAMPLE.get(shape, "")) + WALK)
    assert page.status_code == 200, f"{shape} -> {page.status_code}"
