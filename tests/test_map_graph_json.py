"""The method graph as JSON: ``GET /map/graph.json`` (§M.5).

Contract, not content: the node id set and edge count must equal
``pmbok.graph.GRAPH``'s own (the same node set the SVG at ``/map`` draws), the
response must be byte-identical across two requests (frozen data, no as-of),
it must actually be JSON, and every node must carry enough to redraw the map
without the HTML page: ``x``/``y`` (the SVG's own ``LAYOUT`` coordinates),
``group``/``area`` on process nodes, ``family`` on technique/artifact nodes,
and ``href`` resolving to the node's own page.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import test_web_pages
from driftless.pmbok.definitions import PMBOK_SOURCE_VERSION
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.graph_layout import LAYOUT

client, db = test_web_pages.client, test_web_pages.db


def test_the_route_answers_json_with_every_node_and_edge(client: TestClient) -> None:
    response = client.get("/map/graph.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()

    assert body["source_version"] == PMBOK_SOURCE_VERSION
    assert {node["id"] for node in body["nodes"]} == {n.id for n in GRAPH.nodes}
    assert len(body["edges"]) == GRAPH.size()[1]


def test_two_requests_are_byte_identical(client: TestClient) -> None:
    first = client.get("/map/graph.json")
    second = client.get("/map/graph.json")
    assert first.content == second.content


def test_every_node_carries_position_group_area_family_and_href(client: TestClient) -> None:
    response = client.get("/map/graph.json")
    body = response.json()
    nodes = {node["id"]: node for node in body["nodes"]}

    assert nodes.keys() == {n.id for n in GRAPH.nodes}

    for node in nodes.values():
        assert isinstance(node["x"], int)
        assert isinstance(node["y"], int)
        assert isinstance(node["href"], str) and node["href"]
        if node["kind"] == "process":
            assert isinstance(node["group"], str) and node["group"]
            assert isinstance(node["area"], str) and node["area"]
            assert node["family"] is None
        else:
            assert node["group"] is None
            assert node["area"] is None
            assert isinstance(node["family"], str) and node["family"]


def test_x_y_equal_the_layout_the_svg_draws_from() -> None:
    """A sample across all three kinds: the JSON coordinates must be the exact
    ``LAYOUT.positions`` the SVG at ``/map`` reads its own ``x``/``y`` from."""
    from driftless.web.method_map_json import graph_payload

    body = graph_payload()
    nodes = {node["id"]: node for node in body["nodes"]}
    sample = [n.id for n in GRAPH.nodes][:5] + [n.id for n in GRAPH.nodes][-5:]
    for node_id in sample:
        x, y = LAYOUT.positions[node_id]
        assert (nodes[node_id]["x"], nodes[node_id]["y"]) == (x, y)


def test_every_node_href_resolves(client: TestClient) -> None:
    """A sample across all three kinds: the JSON ``href`` must be a real,
    reachable page — the same one the SVG node links to."""
    response = client.get("/map/graph.json")
    body = response.json()
    nodes = {node["id"]: node for node in body["nodes"]}
    sample = [n.id for n in GRAPH.nodes][:3] + [n.id for n in GRAPH.nodes][-3:]
    for node_id in sample:
        page = client.get(nodes[node_id]["href"])
        assert page.status_code == 200
