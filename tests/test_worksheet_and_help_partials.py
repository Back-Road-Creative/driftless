"""Pins ``_worksheet.html`` and ``_help.html`` against the app's own strict
Jinja environment: a11y (bound labels), no-JS. Neither is adopted yet."""

from __future__ import annotations

import re
from typing import Any

from markupsafe import Markup

from driftless.pmbok.worksheets import Worksheet, WorksheetSection
from driftless.web.templating import TEMPLATES

_LABEL_FOR = re.compile(r'<label for="([^"]+)"')
_INPUT_ID = re.compile(r'id="([^"]+)"')

SHEET = Worksheet(
    key="rolling_wave_planning",
    title="Rolling wave planning worksheet",
    purpose="Split the horizon into near and far waves.",
    sections=(
        WorksheetSection(heading="Near wave", prompts=("List near-wave tasks.",), kind="text"),
        WorksheetSection(heading="Triggers", prompts=("Name each trigger.",), kind="check"),
    ),
    outputs=("A mixed-granularity schedule.",),
)


def _module(name: str) -> Any:
    return TEMPLATES.env.get_template(name).module


def test_worksheet_renders_bound_labels_kinds_hint_and_no_js() -> None:
    html = str(_module("_worksheet.html").worksheet(SHEET))
    assert html.count("<fieldset") == 2
    assert "<legend>Near wave</legend>" in html and "<legend>Triggers</legend>" in html
    labels, ids = _LABEL_FOR.findall(html), _INPUT_ID.findall(html)
    assert labels, "no <label for> found"
    for label_id in labels:
        assert label_id in ids, f"label points at {label_id!r}, which no control carries"
    assert '<textarea id="ws-rolling_wave_planning-0-0"' in html
    assert '<input type="checkbox" id="ws-rolling_wave_planning-1-0">' in html
    assert "<script" not in html and "onclick" not in html and "<form" not in html
    assert "Print this page to use it on paper." in html
    assert "A mixed-granularity schedule." in html


def test_steps_checklist_renders_one_bound_checkbox_per_step() -> None:
    html = str(
        _module("_worksheet.html").steps_checklist("rolling_wave_planning", ("Do X.", "Do Y."))
    )
    assert html.count("<li>") == 2
    labels, ids = _LABEL_FOR.findall(html), _INPUT_ID.findall(html)
    assert len(labels) == 2
    for label_id in labels:
        assert label_id in ids


def test_how_to_read_wraps_caller_output_and_takes_a_custom_title() -> None:
    how_to_read = _module("_help.html").how_to_read
    html = str(how_to_read(caller=lambda: Markup("<p>Body copy.</p>")))
    assert '<details class="how-to-read">' in html
    assert "<summary>How to read this page</summary>" in html
    assert "<p>Body copy.</p>" in html
    assert "<script" not in html and "onclick" not in html

    custom = str(how_to_read(title="What this shows", caller=lambda: Markup("x")))
    assert "<summary>What this shows</summary>" in custom
