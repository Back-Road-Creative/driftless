"""Pins the integration family's printable worksheets: every technique in
``tt.FAMILIES["integration"]`` that has no assistant route (so it sits in
``reasons.GUIDE_ONLY_REASONS``) carries a worksheet, and each one is shaped the
way a printable form needs — a heading, prompts, and never a mixed kind.

Scoped to this one family deliberately. The catalogue-wide version of the first
assertion belongs to whichever change lands the last family's worksheets; other
families are being served by their own changes, and asserting over all of them
here would fail on work that has not landed yet.
"""

from __future__ import annotations

import pytest

from driftless.pmbok.plain_language import snake_identifiers
from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
from driftless.pmbok.tt import FAMILIES
from driftless.pmbok.worksheets import WORKSHEETS

#: The integration techniques no assistant can run, and so the ones a printable
#: worksheet is the honest offer for. Derived, never typed.
GUIDE_ONLY_INTEGRATION = frozenset(FAMILIES["integration"]) & frozenset(GUIDE_ONLY_REASONS)


def test_every_guide_only_integration_technique_has_a_worksheet() -> None:
    assert GUIDE_ONLY_INTEGRATION, "the integration family has no guide-only techniques to serve"
    missing = sorted(GUIDE_ONLY_INTEGRATION - set(WORKSHEETS))
    assert not missing, f"guide-only integration techniques with no worksheet: {missing}"


@pytest.mark.parametrize("key", sorted(GUIDE_ONLY_INTEGRATION))
def test_each_integration_worksheet_is_fully_shaped(key: str) -> None:
    sheet = WORKSHEETS[key]
    assert sheet.title and sheet.purpose and sheet.outputs
    assert len(sheet.sections) >= 2, "a worksheet worth printing asks for more than one thing"
    for section in sheet.sections:
        assert section.heading and section.prompts
        assert section.kind in ("check", "text")
        if section.kind == "text":
            assert all(prompt.endswith("?") for prompt in section.prompts), (
                f"{key}: a text prompt is a question a person answers in the room"
            )
        else:
            assert not any(prompt.endswith("?") for prompt in section.prompts), (
                f"{key}: a checkbox is a statement to tick, not a question"
            )


@pytest.mark.parametrize("key", sorted(GUIDE_ONLY_INTEGRATION))
def test_no_integration_worksheet_prose_leaks_a_raw_identifier(key: str) -> None:
    sheet = WORKSHEETS[key]
    prose = [sheet.title, sheet.purpose, *sheet.outputs]
    for section in sheet.sections:
        prose.extend([section.heading, *section.prompts])
    leaked = sorted({token for text in prose for token in snake_identifiers(text)})
    assert not leaked, f"{key} worksheet prose names raw identifiers: {leaked}"
