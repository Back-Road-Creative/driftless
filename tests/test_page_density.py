"""Three dense pages, trimmed: a department's nine sections were nine open tables on
one screen, a hub's ten knowledge-area percentages were one long inline sentence, and
search results printed the raw internal path as their own label. None of that is a
content change -- the same figures, folded, tabulated or relabelled -- so each test
reads the rendered HTML for shape, never for new numbers."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload

Q = f"?as_of={ANCHOR.isoformat()}"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def _seed(client: TestClient) -> None:
    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        assert response.status_code == 200, response.text

    seed(post, demo_payload(ANCHOR), patch)


def test_department_operations_fold_into_one_details(client: TestClient) -> None:
    """Services, work queue, recurring work, service levels, operating controls,
    incidents and improvements sit behind one toggle; only the department's own
    headline sections -- projects and people -- stay open on the page."""
    _seed(client)
    department_id = client.get("/departments").json()[0]["id"]
    page = client.get(f"/org/departments/{department_id}").text

    details_match = re.search(
        r'<details class="figures"><summary>[^<]*</summary>(.*?)</details>',
        page,
        re.DOTALL,
    )
    assert details_match, "no folded operations block found"
    folded = details_match.group(1)
    for heading in (
        "Services",
        "Work queue",
        "Recurring work",
        "Service levels",
        "Operating controls",
        "Incidents",
        "Improvements",
    ):
        assert f"<h2>{heading}</h2>" in folded, f"{heading!r} is missing from the folded block"

    outside = page.replace(details_match.group(0), "")
    assert len(re.findall(r"<h2>", outside)) <= 4


def test_hub_knowledge_areas_render_as_a_definition_list(client: TestClient) -> None:
    """The ten knowledge-area percentages are a ``dl.kv``, one ``dt`` per area, not
    one long inline sentence."""
    _seed(client)
    project_id = client.get("/projects").json()[0]["id"]
    page = client.get(f"/projects/{project_id}/hub{Q}").text

    kv_match = re.search(r'<dl class="kv">(.*?)</dl>', page, re.DOTALL)
    assert kv_match, "no dl.kv block found on the hub"
    assert len(re.findall(r"<dt>", kv_match.group(1))) == 10


def test_search_hits_show_a_human_label_not_a_raw_path(client: TestClient) -> None:
    """The 'Where it lives' column names what the hit is, never the internal
    ``/projects/<id>/...`` path it links to."""
    _seed(client)
    page = client.get("/search?q=Fleet").text
    cells = re.findall(r"<td>(.*?)</td>", page, re.DOTALL)
    assert cells, "no search results rendered for a known demo term"
    for cell in cells:
        text = re.sub(r"<[^>]*>", "", cell).strip()
        assert not text.startswith("/projects/"), cell
