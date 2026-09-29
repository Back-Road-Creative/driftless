"""``COMPETITORS.md`` compares this product against six others, and every claim it makes
about THIS one is backed by a citation into the source. Nine of those citations addressed
a line number, and **five had drifted onto unrelated code**: the file cited a
``stamped_percent`` that had moved 210 lines, an ``is_suppressed`` that had moved 9, a
``schemas.py`` line holding a bounds validator for a claim about a create body, and a test
function two lines below the number naming it. Nothing had ever read them, so a set of true
claims quietly became a set of false addresses without anyone editing the file — the worst
place for it, since this is the document written to be read by someone deciding whether to
believe the product.

They are SYMBOL citations now — ``path.py:symbol`` names something the file defines, which
survives every insertion above it — and this reads each one. The second test forbids a line
number from coming back, because a convention nothing enforces is how the first five got in.

``docs/pmbok-mapping.md`` used to be the stated exception — a dense per-process table where
the line was argued to be the real address — and it dropped that too, once its citation
format was caught bending production code to hold a line still. Both files cite by symbol
now, and ``tests/test_docs_pmbok_mapping.py`` reads its own the way this one does.

Pointers from this file into other DOCS are file-level, naming the row in prose rather than
by number. Those are not machine-checked — there is no symbol to look up — but there is also
no number left to be wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "COMPETITORS.md"
ROOT = DOC.parent
WRITTEN = DOC.read_text()

CITATION = re.compile(r"`((?:driftless|tests|bin)/[\w/]+\.py):(\w+)`")
NUMBERED = re.compile(r"`(?:driftless|tests|docs|bin)/[\w/.-]+\.\w+:\d+")


def _defines(line: str, symbol: str) -> bool:
    """Whether ``line`` IS ``symbol``'s definition, at module level.

    Column zero on purpose, unlike a lenient ``lstrip``: a local variable that happens to
    share the name is not what a reader following the citation is being sent to.
    """
    return bool(re.match(rf"(def|class)\s+{symbol}\b", line) or re.match(rf"{symbol}\s*[:=]", line))


def test_every_citation_names_a_symbol_that_file_defines() -> None:
    cited = CITATION.findall(WRITTEN)
    assert len(cited) >= 8, f"only {len(cited)} citations — the comparison lost its grounding"
    wrong = []
    for path, symbol in cited:
        source = ROOT / path
        lines = source.read_text().splitlines() if source.exists() else []
        if not any(_defines(line, symbol) for line in lines):
            wrong.append(f"{path} defines no {symbol}")
    assert not wrong, "stale citations:\n" + "\n".join(wrong)


LANDED_FEATURE_WORDS = (
    "WBS",
    "traceability",
    "closeout",
    "Gantt",
    "kanban",
    "iCal",
    "CSV",
    "critical path",
)


def test_as_of_reflects_the_newest_landed_feature_it_names() -> None:
    """The 2026-08-02 refresh predates the features it still called gaps. A stale date is
    how a true claim quietly became false without anyone editing the file."""
    assert "**As of 2026-08-02.**" not in WRITTEN, "as-of was never moved past the stale refresh"
    assert "**As of 2026-09-22.**" in WRITTEN, "as-of has not been moved to the current refresh"


def test_gap_register_table_does_not_list_landed_features_as_gaps() -> None:
    """Only the table itself, not the "landed since the last refresh" strengths list right
    above it — that list is expected to name these, as shipped, not as gaps."""
    section = WRITTEN.split("## 2. Gap register")[1].split("## 3.")[0]
    table = section.split("| Gap (who has it) | Decision |")[1]
    hits = [w for w in LANDED_FEATURE_WORDS if w in table]
    assert not hits, f"gap register table still lists landed features as gaps: {hits}"


def test_no_citation_addresses_a_line_number() -> None:
    """The rule, not just this file's current state: a line number here is a claim that
    goes stale on the next insertion above it, in a document nobody re-reads while editing
    code. Five did exactly that. A symbol moves with the thing it names."""
    assert not NUMBERED.findall(WRITTEN), (
        f"line-numbered citations are back: {NUMBERED.findall(WRITTEN)} — "
        "cite the symbol instead, so it survives an insertion above it"
    )
