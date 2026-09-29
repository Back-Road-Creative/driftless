"""The drift gate in ``.github/workflows/ci.yml`` (:mod:`test_sample_drift_gate`) reruns
``bin/driftless-sample-reports.py`` and byte-diffs the result against ``docs/samples/``.
That proves the generator is *deterministic* — never that what it emits is real content.
A generator that started writing a one-line stub for every report would go green the
moment the stub was committed, and stay green forever after.

This asks the question the gate structurally cannot: for each family of committed
sample under ``docs/samples/2026-07-01/``, does the file actually carry the sections and
bulk a document of that kind should have. Sizes are read off the current bundle, not
picked as round numbers, so the floor tracks what is really there; the margin below it
is generous enough to survive small future edits without becoming a second drift gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUNDLE = REPO / "docs" / "samples" / "2026-07-01"

PROJECTS = (
    "archive-digitization",
    "fleet-modernization",
    "route-optimization-pilot",
    "season-4-rollout",
)

#: report slug -> (H1 title prefix, required H2 headings). The H2 tuple is the
#: intersection across all four committed projects, read straight off the files —
#: some projects add an extra section (fleet-modernization's forecast) or omit an
#: optional one (route-optimization-pilot's scope-baseline has none), so only what
#: every instance actually carries is asserted.
#:
#: report type       | H1 title              | min bytes (committed) | floor (50%)
#: ------------------ | ---------------------- | ---------------------- | -----------
#: assessment         | Assessment Report      | 854                    | 427
#: charter             | Project Charter       | 290                    | 145
#: cost-evm            | Cost Report (EVM)     | 581                    | 290
#: forecast            | Forecast Report       | 470                    | 235
#: process-map         | Process Map           | 3605                   | 1802
#: risk-register       | Risk Register / RAID  | 387                    | 193
#: schedule            | Schedule Report       | 202                    | 101
#: scope-baseline      | Scope & Baseline      | 100                    | 50
#: weekly-status       | Weekly Status Report  | 365                    | 182
REPORT_TYPES = {
    "assessment": ("Assessment Report", ("Top threats", "Knowledge areas"), 427),
    "charter": ("Project Charter", ("Stakeholders", "Key milestones"), 145),
    "cost-evm": ("Cost Report (EVM)", (), 290),
    "forecast": ("Forecast Report", ("Completion forecast (EVM)", "Contingency"), 235),
    "process-map": ("Process Map", (), 1802),
    "risk-register": (
        "Risk Register / RAID Log",
        ("Risks", "Risk responses", "Issues", "Change requests"),
        193,
    ),
    "schedule": ("Schedule Report", (), 101),
    "scope-baseline": ("Scope & Baseline", (), 50),
    "weekly-status": ("Weekly Status Report", ("Status", "Earned value", "Top open risks"), 182),
}

#: portfolio-level rollups, one directory up from the per-project reports.
#: file            | H1 title           | min bytes | floor (50%)
#: business-rollup | Portfolio Rollup   | 929       | 464
#: department      | Department Report | 631       | 315
ROLLUPS = {
    "business-rollup": ("Portfolio Rollup", ("Business totals", "Portfolios"), 464),
    "department": ("Department Report", ("Operations", "Production"), 315),
}


def _display_name(slug: str) -> str:
    """``archive-digitization`` -> ``Archive Digitization``, the title every project
    report renders in its H1, matching what ``driftless/demo/data.py`` names it."""
    return slug.replace("-", " ").title()


def _assert_markdown_family(
    path: Path, title: str, required_h2: tuple[str, ...], *, has_project_suffix: bool
) -> None:
    text = path.read_text(encoding="utf-8")
    h1 = f"# {title} — " if has_project_suffix else f"# {title}\n"
    assert text.startswith(h1), text.splitlines()[0]
    for heading in required_h2:
        assert f"## {heading}" in text, f"{path}: missing '## {heading}'"


REPORT_CASES = [(project, report_type) for project in PROJECTS for report_type in REPORT_TYPES]


@pytest.mark.parametrize(
    "project,report_type", REPORT_CASES, ids=[f"{p}/{r}" for p, r in REPORT_CASES]
)
def test_project_report_has_family_appropriate_content(project: str, report_type: str) -> None:
    title_prefix, required_h2, floor = REPORT_TYPES[report_type]
    path = BUNDLE / project / f"{report_type}.md"

    size = path.stat().st_size
    assert size >= floor, f"{path} is {size} bytes, below the {floor}-byte floor"
    assert _display_name(project) in path.read_text(encoding="utf-8").splitlines()[0]
    _assert_markdown_family(path, title_prefix, required_h2, has_project_suffix=True)


@pytest.mark.parametrize("name", sorted(ROLLUPS))
def test_portfolio_rollup_has_family_appropriate_content(name: str) -> None:
    title, required_h2, floor = ROLLUPS[name]
    path = BUNDLE / f"{name}.md"

    size = path.stat().st_size
    assert size >= floor, f"{path} is {size} bytes, below the {floor}-byte floor"
    _assert_markdown_family(path, title, required_h2, has_project_suffix=False)


def test_method_map_svg_is_a_real_graph_not_a_stub() -> None:
    """Structural floor only — :mod:`test_sample_reports_method_map` already checks the
    committed file for its own identity (``aria-label``, ``viewBox``, a node per
    process). This just guards against the same class of regression the rest of this
    module guards against: a generator that starts emitting a near-empty stub."""
    path = BUNDLE / "method-map.svg"
    text = path.read_text(encoding="utf-8")

    size = path.stat().st_size
    assert size >= 39_409, f"{path} is {size} bytes, below the 39409-byte floor (half of 78819)"
    assert text.startswith("<svg")
    assert text.rstrip().endswith("</svg>")
    assert len(re.findall(r"<g\b", text)) >= 25
    assert len(re.findall(r"<path\b", text)) >= 200
