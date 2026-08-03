"""Every list endpoint hands back CSV as well as JSON.

The format is answered at the one registration point every list route goes
through (``api.app._reads``), so these tests walk the app's own route table
rather than naming endpoints: an entity registered later is covered with no
edit. The JSON bodies pinned below were captured *before* the parameter existed
— the point of adding it is that today's callers cannot tell it was. The last
two tests hold export and importer against each other: the columns line up kind
for kind, and the one column that cannot go back (``id``) refuses out loud.
"""

import csv
import importlib.util
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory

_IMPORTER = Path(__file__).resolve().parents[1] / "bin" / "driftless-import.py"

MASTER_TASKS = (
    b'[{"name":"Colour grade","workstream_id":1,"status":"in_progress","estimate":40.0,'
    b'"estimate_unit":"hours","actual_effort":null,"percent_complete":25,"assignee_id":null,'
    b'"id":1},{"name":"Deliver master","workstream_id":1,"status":"todo","estimate":null,'
    b'"estimate_unit":"hours","actual_effort":null,"percent_complete":0,"assignee_id":null,'
    b'"id":2}]'
)
MASTER_MILESTONES = (
    b'[{"project_id":1,"name":"Rough cut locked","target_date":"2026-08-15",'
    b'"baseline_date":null,"status":"pending","id":1}]'
)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
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


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    """The same rows the pinned bodies above were captured from."""

    def post(path: str, **body: Any) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    business = post("/businesses", name="Back Road Creative")
    portfolio = post("/portfolios", name="Content Brands", business_id=business)
    project = post("/projects", name="GMS", portfolio_id=portfolio)
    stream = post("/workstreams", name="Edit", project_id=project)
    post(
        "/tasks",
        name="Colour grade",
        workstream_id=stream,
        status="in_progress",
        estimate=40,
        estimate_unit="hours",
        percent_complete=25,
    )
    post("/tasks", name="Deliver master", workstream_id=stream, estimate_unit="hours")
    post("/milestones", project_id=project, name="Rough cut locked", target_date="2026-08-15")
    return client


def _rows(body: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body)))


def _list_routes() -> list[tuple[str, type[BaseModel]]]:
    """Every list route and its response model, read off the app's own table."""
    return [
        (route.path, get_args(route.response_model)[0])
        for route in app.routes
        if isinstance(route, APIRoute)
        and "GET" in route.methods
        and "{" not in route.path
        and get_origin(route.response_model) is list
    ]


def _importer() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_import", _IMPORTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_csv_header_is_the_response_model_fields_in_declaration_order(seeded: TestClient) -> None:
    response = seeded.get("/tasks", params={"format": "csv"})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert _rows(response.text)[0] == list(s.TaskOut.model_fields)


def test_csv_cells_render_dates_iso_and_an_unset_field_empty(seeded: TestClient) -> None:
    header, row = _rows(seeded.get("/milestones", params={"format": "csv"}).text)
    cells = dict(zip(header, row, strict=True))

    assert cells["target_date"] == "2026-08-15"  # ISO, exactly as the JSON body carries it
    assert cells["baseline_date"] == ""  # an unset optional is an empty cell, never "None"
    assert cells["name"] == "Rough cut locked"
    assert cells["id"] == "1"


def test_an_unknown_format_is_refused_by_validation(seeded: TestClient) -> None:
    assert seeded.get("/tasks", params={"format": "xml"}).status_code == 422


def test_json_is_byte_identical_to_the_body_captured_before_the_parameter(
    seeded: TestClient,
) -> None:
    for path, pinned in (("/tasks", MASTER_TASKS), ("/milestones", MASTER_MILESTONES)):
        assert seeded.get(path).content == pinned, path
        assert seeded.get(path, params={"format": "json"}).content == pinned, path


def test_every_list_route_answers_both_formats(client: TestClient) -> None:
    """Registered once, exportable everywhere — including entities added later."""
    routes = _list_routes()
    assert len(routes) > 20

    for path, out in routes:
        assert client.get(path).content == b"[]", path  # empty JSON, untouched
        exported = client.get(path, params={"format": "csv"})
        assert exported.headers["content-type"].startswith("text/csv"), path
        assert _rows(exported.text) == [list(out.model_fields)], path


def test_exported_columns_match_every_importer_kind() -> None:
    """Export and import meet: the exported columns minus ``id`` are the kind's own."""
    out_for = dict(_list_routes())

    for kind, spec in _importer().CSV_KINDS.items():
        exported = set(out_for[spec.path].model_fields) - {"id"}
        assert exported == set(spec.required) | set(spec.optional), kind


def test_an_export_imports_once_its_id_column_is_dropped(seeded: TestClient) -> None:
    """Values survive the trip readably: ISO date in, ISO date out, blank cell omitted."""
    exported = seeded.get("/milestones", params={"format": "csv"}).text
    rows = [
        {k: v for k, v in row.items() if k != "id"} for row in csv.DictReader(io.StringIO(exported))
    ]
    calls: list[tuple[str, dict[str, Any]]] = []

    def post(path: str, body: dict[str, Any]) -> int:
        calls.append((path, body))
        return 1

    assert _importer().import_csv(post, "milestones", rows) == {"milestones": 1}
    assert calls == [
        (
            "/milestones",
            {
                "project_id": 1,
                "name": "Rough cut locked",
                "target_date": "2026-08-15",
                "status": "pending",
            },
        )
    ]


def test_the_importers_payloads_round_trip_through_the_real_api(seeded: TestClient) -> None:
    """The dict-level test above proves the payloads; this proves the door.

    Handing the payloads to a fake ``post`` left the actual route out of the
    loop — a ``/milestones`` route that quietly dropped ``status`` or
    ``baseline_date`` shipped green. Here the importer POSTs into the real API,
    the result is re-exported, and every column is compared field by field, on
    a row whose every optional column sits away from its schema default — so a
    dropped field cannot hide behind the default it would fall back to."""
    body = {
        "project_id": 1,
        "name": "Final delivery",
        "target_date": "2026-09-30",
        "baseline_date": "2026-09-01",
        "status": "at_risk",
    }
    created = seeded.post("/milestones", json=body)
    assert created.status_code == 201, created.text
    assert {k: created.json()[k] for k in body} == body, "the setup row must land as posted"
    exported = seeded.get("/milestones", params={"format": "csv"}).text
    originals = list(csv.DictReader(io.StringIO(exported)))
    rows = [{k: v for k, v in row.items() if k != "id"} for row in originals]

    def post(path: str, payload: dict[str, Any]) -> int:
        response = seeded.post(path, json=payload)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    assert _importer().import_csv(post, "milestones", rows) == {"milestones": len(originals)}

    final = seeded.get("/milestones", params={"format": "csv"}).text
    landed = sorted(csv.DictReader(io.StringIO(final)), key=lambda row: int(row["id"]))
    for original, copy in zip(originals, landed[len(originals) :], strict=True):
        assert copy["id"] != original["id"], "the importer creates rows, never updates them"
        for field in (name for name in original if name != "id"):
            assert copy[field] == original[field], f"{field} did not survive the round trip"


def test_importing_an_export_unchanged_names_the_id_column_and_why(seeded: TestClient) -> None:
    """The one asymmetry, refused out loud: the importer only ever creates rows."""
    exported = seeded.get("/milestones", params={"format": "csv"}).text
    rows = list(csv.DictReader(io.StringIO(exported)))

    with pytest.raises(ValueError) as caught:
        _importer().import_csv(lambda path, body: 1, "milestones", rows)

    assert str(caught.value) == (
        "row 2: column 'id' comes from an export — drop it before importing, because this "
        "importer only ever creates rows, so ids would duplicate what they name, not update it"
    )
