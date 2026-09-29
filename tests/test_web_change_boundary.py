"""The one change boundary: driftless.web.change_boundary, and the invariant that
no template offers a second approval path for changing a plan (a baseline never
gets its own approve form — only ChangeRequest -> Baseline does)."""

from __future__ import annotations

import re
from pathlib import Path

from driftless.web.change_boundary import change_boundary

_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless" / "web" / "templates"


def test_change_boundary_names_the_origin_process_and_project() -> None:
    link = change_boundary(1, "7.4")
    assert link.origin_process_id == "7.4"
    assert "7.4" in link.instruction
    assert "1" in link.instruction
    assert link.href == "/projects/1/raid#changes"
    assert link.label == "Raise a change request"


def test_no_template_offers_a_second_baseline_approval_form() -> None:
    # The only way a plan changes is ChangeRequest -> Baseline (POST /change-requests,
    # approval produces a new Baseline). No page may add its own form that POSTs or
    # PATCHes a baseline directly — that would be a second, competing approval path.
    offenders = []
    for html in _TEMPLATES.glob("*.html"):
        text = html.read_text()
        for form in re.findall(r"<form\b[^>]*action=\"([^\"]*)\"", text):
            if "baseline" in form.lower():
                offenders.append((html.name, form))
    assert offenders == []
