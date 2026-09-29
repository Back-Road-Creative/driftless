"""``risk_report`` is an untracked artifact kind: nothing resolves it, so its disposition
in ``driftless.pmbok.mapping.UNTRACKED_DISPOSITIONS`` and its row in
``docs/pmbok-mapping.md`` are the only two places a reader learns what the risk report
actually is. Both used to credit it with "the seeded Monte Carlo" — but
``driftless.calc.forecast.monte_carlo_completion`` is a bootstrap over *sprint velocity*
that is now wired into the Forecast Report's "Simulated completion" block, a **schedule**
output, not a risk one: no risk report document renders it. This test is grounded in the
tracked source tree rather than pinned to any particular sentence, so it goes red again the
day either statement drifts from what the product renders — and it goes red *for the right
reason* the day the Monte Carlo grows a caller outside the forecast report, or one inside a
risk output, at which point the disposition should say so and this test should be updated
to match.
"""

from __future__ import annotations

import re
from pathlib import Path

from driftless.pmbok import mapping

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "pmbok-mapping.md"
CALC_DIR = (ROOT / "driftless" / "calc").resolve()
SIMULATION_WORDS = re.compile(r"monte carlo|simulation", re.IGNORECASE)
# A sentence that mentions the Monte Carlo / simulation AND disclaims it (says it is not
# wired in / has no caller / does not run) is telling the truth, not attributing it. Only
# a mention with no such disclaimer nearby is a false claim that the risk output runs it.
DISCLAIMED = re.compile(r"not wired|no caller|not run|isn.t wired|is not run", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")


def _monte_carlo_callers_outside_calc() -> list[Path]:
    """Every tracked production file (excluding ``driftless/calc/`` itself and the test
    suite) that so much as mentions ``monte_carlo_completion`` — a caller, an import, or a
    doc reference. Empty means the function renders nowhere."""
    callers = []
    for path in (ROOT / "driftless").rglob("*.py"):
        if path.resolve().parent == CALC_DIR:
            continue
        if "monte_carlo_completion" in path.read_text():
            callers.append(path)
    return callers


def _attributes_monte_carlo(text: str) -> bool:
    """Whether ``text`` claims a Monte Carlo / simulation runs as part of what it
    describes, rather than merely mentioning that one exists elsewhere and does not."""
    return any(
        SIMULATION_WORDS.search(sentence) and not DISCLAIMED.search(sentence)
        for sentence in SENTENCE_SPLIT.split(text)
    )


def test_monte_carlo_completion_is_wired_into_the_forecast_report_only() -> None:
    """Ground truth this test relies on: the day a second caller appears, or the caller
    stops being the forecast report, the risk_report disposition and pmbok-mapping.md
    need a fresh look — this assertion is what would go red first."""
    callers = _monte_carlo_callers_outside_calc()
    relative = sorted(str(path.relative_to(ROOT)) for path in callers)
    assert relative == ["driftless/report/documents/forecast.py"], (
        f"monte_carlo_completion callers outside driftless/calc/: {relative} — expected "
        "exactly the forecast report document; update the risk_report disposition and "
        "docs/pmbok-mapping.md if this list changed for a reason that touches risk"
    )


def test_no_untracked_disposition_credits_a_risk_output_with_the_monte_carlo() -> None:
    wired = _monte_carlo_callers_outside_calc()
    offending = [
        kind
        for kind, reason in mapping.UNTRACKED_DISPOSITIONS.items()
        if "risk" in kind and not wired and _attributes_monte_carlo(reason)
    ]
    assert not offending, (
        f"UNTRACKED_DISPOSITIONS credits {offending} with a Monte Carlo / simulation that "
        "has no caller outside driftless/calc/ — reword to name what the report renders"
    )


def test_docs_do_not_attribute_the_monte_carlo_to_a_risk_output() -> None:
    wired = _monte_carlo_callers_outside_calc()
    lines = DOC.read_text().splitlines()
    offending = [
        line
        for line in lines
        if "risk_report" in line and not wired and _attributes_monte_carlo(line)
    ]
    assert not offending, (
        "docs/pmbok-mapping.md attributes a Monte Carlo / simulation to risk_report while "
        f"monte_carlo_completion has no caller outside driftless/calc/: {offending}"
    )
