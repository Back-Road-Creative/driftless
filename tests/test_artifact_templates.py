"""Pins the printable artifact-template registry and the plans family's slice of it.

``ARTIFACT_TEMPLATES`` is a SECOND registry beside ``WORKSHEETS``: a ``Worksheet.key``
is a technique key and a ``Template.key`` is an artifact kind, so one registry could
hold both only by loosening whichever check makes each real. Catalog-wide totality is
deliberately NOT asserted while sibling families are still being written — what is
walked is what shipped, and the plans still to come are pinned BY NAME.
"""

from __future__ import annotations

import html
import importlib
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import test_web_pages
from driftless.pmbok import templates_plans
from driftless.pmbok.artifacts import FAMILIES
from driftless.pmbok.mapping import SUBSIDIARY_PLANS, is_tracked
from driftless.pmbok.worksheets import ARTIFACT_TEMPLATES, Template, _discover_templates
from driftless.web.templating import artifact_slug

client, db = test_web_pages.client, test_web_pages.db

_ENTRY = (
    "from driftless.pmbok.worksheets import Template\n"
    "ENTRIES = (Template(key={key!r}, sections=()),)\n"
)
_BLOCK = re.compile(r'<div class="worksheet">.*?</div>', re.S)
_LABEL_FOR = re.compile(r'<label for="([^"]+)"')
_INPUT_ID = re.compile(r'id="([^"]+)"')

#: The subsidiary plans this chunk leaves untemplated, named so the walk below
#: fails the day they land rather than quietly passing over a partial family.
STILL_TO_COME = {
    "requirements_management_plan",
    "resource_management_plan",
    "communications_management_plan",
    "risk_management_plan",
    "procurement_management_plan",
    "stakeholder_engagement_plan",
}


@pytest.fixture
def pkg(tmp_path: Path) -> Iterator[Path]:
    sys.path.insert(0, str(tmp_path))
    (tmp_path / "fx").mkdir()
    (tmp_path / "fx" / "__init__.py").write_text("")
    yield tmp_path / "fx"
    sys.path.remove(str(tmp_path))
    for name in [n for n in sys.modules if n.startswith("fx")]:
        del sys.modules[name]


def _find(pkg: Path, **modules: str) -> dict[str, Template]:
    """Discovery over EXACTLY ``modules``; earlier ones are cleared first."""
    for stale in pkg.glob("templates_*.py"):
        stale.unlink()
    for name, source in modules.items():
        (pkg / f"{name}.py").write_text(source)
    importlib.invalidate_caches()
    return _discover_templates(package_name="fx", package_path=[str(pkg)])


def test_discovery_takes_a_sibling_module_and_refuses_every_malformed_claim(pkg: Path) -> None:
    (pkg / "not_templates.py").write_text("ENTRIES = ('ignored: no templates_ prefix',)")
    found = _find(pkg, templates_ok=_ENTRY.format(key="project_charter"))
    assert set(found) == {"project_charter"}

    with pytest.raises(ValueError, match="unknown artifact kind"):
        _find(pkg, templates_u=_ENTRY.format(key="not_a_real_kind"))
    with pytest.raises(TypeError, match="must define ENTRIES"):
        _find(pkg, templates_t="ENTRIES = ['not a tuple']\n")
    with pytest.raises(TypeError, match="only Template instances"):
        _find(pkg, templates_v="ENTRIES = ('not a Template',)\n")
    with pytest.raises(ValueError, match="claimed by both"):
        _find(
            pkg,
            templates_d1=_ENTRY.format(key="project_charter"),
            templates_d2=_ENTRY.format(key="project_charter"),
        )


def test_every_template_is_complete_and_the_plans_left_over_are_named() -> None:
    """Also pins "Filled here from" as a claim about the store's own resolvers."""
    assert ARTIFACT_TEMPLATES, "vacuous walk: no templates at all"
    covered = {template.key for template in templates_plans.ENTRIES}
    assert covered <= FAMILIES["plans"], f"claims outside the plans family: {covered}"
    assert set(SUBSIDIARY_PLANS) - covered == STILL_TO_COME
    for key, template in sorted(ARTIFACT_TEMPLATES.items()):
        assert template.sections, key
        assert bool(template.filled_from.strip()) is is_tracked(key), key
        for section in template.sections:
            assert section.heading.strip() and section.fields, key
            for field in section.fields:
                assert field.label.strip() and field.guidance.strip(), key


def test_the_detail_page_prints_the_template_as_a_scriptless_bound_form(
    client: TestClient,
) -> None:
    """base.html loads the site's own script on every page, so "needs no scripting"
    is asserted of the rendered BLOCK — the part that has to work on paper."""
    page = html.unescape(client.get(f"/artifacts/{artifact_slug('cost_management_plan')}").text)
    found = _BLOCK.search(page)
    assert found is not None, "the artifact page rendered no template block"
    printed = found.group(0)
    template = ARTIFACT_TEMPLATES["cost_management_plan"]
    for section in template.sections:
        assert section.heading in printed
        for field in section.fields:
            assert field.label in printed and field.guidance in printed
    assert template.filled_from in printed
    labels, ids = _LABEL_FOR.findall(printed), _INPUT_ID.findall(printed)
    wanted = sum(len(section.fields) for section in template.sections)
    assert len(labels) == wanted, f"want one bound label per field, got {len(labels)}"
    for label_id in labels:
        assert label_id in ids, f"label points at {label_id!r}, which no control carries"
    assert "<script" not in printed and "onclick" not in printed and "<form" not in printed
