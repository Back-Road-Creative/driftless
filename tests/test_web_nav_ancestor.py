"""Ancestor-active nav state: a page nested under a nav destination lights that
destination's own anchor, so a reader deep in the site keeps their place — a page
like ``/org/departments/{id}`` used to light nothing at all. Non-vacuous by
construction: a rule that lit every page (or the group label as a link) would fail
the boundary half below, where a page with no nav ancestor stays unlit."""

import re

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db

_GROUPED_LIST = re.compile(r"<ul\b([^>]*)>", re.I)


def test_a_descendant_page_lights_its_ancestors_anchor_and_an_orphan_page_lights_nothing(
    client: TestClient, db: Session
) -> None:
    business = db.scalars(select(m.Business)).one()
    department = m.Department(name="Post", business=business)
    db.add(department)
    db.commit()

    drill = client.get(f"/org/departments/{department.id}")
    assert drill.status_code == 200, drill.text
    assert '<a href="/org/departments" aria-current="page">' in drill.text, (
        "a department drill page must light its own list page's nav anchor"
    )

    login = client.get("/login")
    assert login.status_code == 200, login.text
    assert 'aria-current="page"' not in login.text, (
        "no nav destination is an ancestor of /login — the rule must not light it anyway"
    )


def test_a_project_process_map_lights_the_whole_business_process_status_anchor(
    client: TestClient, db: Session
) -> None:
    """``/projects/{id}/process-map`` is not nested UNDER ``/process-map``, so the prefix
    rule leaves the product's deepest process surface lighting nothing at all."""
    project = db.scalars(select(m.Project)).one()
    page = client.get(f"/projects/{project.id}/process-map")
    assert page.status_code == 200, page.text
    assert '<a href="/process-map" aria-current="page">Process status</a>' in page.text, (
        "a project's own process map must light the whole-business Process status anchor"
    )


def test_every_nav_group_names_itself_to_a_screen_reader(client: TestClient) -> None:
    """A group label beside a nested list is a *visual* grouping only. Read aloud, the
    label is loose text and the list it names is anonymous — so the grouping this PR
    exists to add would not reach the readers who most need to know where they are."""
    page = client.get("/")
    assert page.status_code == 200, page.text
    nav = page.text[page.text.index('<nav aria-label="Primary"') :]
    nav = nav[: nav.index("</nav>")]

    nested = [attrs for attrs in _GROUPED_LIST.findall(nav) if "primary-nav" not in attrs]
    assert nested, "vacuous walk: the primary nav renders no nested list, so nothing is grouped"

    for attrs in nested:
        named = re.search(r'aria-labelledby="([^"]+)"', attrs) or re.search(
            r'aria-label="([^"]+)"', attrs
        )
        assert named, f"a grouped nav list carries no accessible name: <ul{attrs}>"
        if "aria-labelledby" in attrs:
            assert f'id="{named.group(1)}"' in nav, (
                f"aria-labelledby points at {named.group(1)!r}, which the nav never defines"
            )
