"""``docs/pmbok-mapping.md`` is checked, not just written — the reference-doc form of the
guides' executable convention. It is a table, not a script, so there is nothing to *run*; what
makes it un-rottable is that every claim in it is a claim about code this test reads.

This file used to check ``path:line symbol`` citations against the line, on the stated
argument that a dense per-process table needs the line as the address. That argument held
right up until an agent needed to add a module-level import to
``driftless/assess/scorecard.py`` and instead wrote it inside the function body — comment and
all — to avoid shifting ``evaluate_metric`` off the line this file cited. There was no import
cycle; a citation format bent production code into a worse shape to keep itself green. Every
citation already names the symbol, so the line number was carrying no information the symbol
didn't — it was pure liability. This file now resolves ``path:symbol`` the way
``tests/test_docs_competitors.py`` resolves its own citations into ``COMPETITORS.md``, for the
same reason that test does: a symbol survives an insertion above it, a line number does not.

The counts must still be the live catalog's own, and the supported/absent boundary must still
be the store's: a kind named in the supported half resolves, a kind named under **Not
implemented** does not. Implement one of the declared non-goals and this goes red until the
document says so. The guides' rule that a fence with no run marker fails is inherited too, so
nobody can slip an unrun command in later.
"""

from __future__ import annotations

import re
from pathlib import Path

from test_docs_agent_guide import FENCED

from driftless.pmbok import catalog, crosswalk, mapping
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.state import is_assessable

DOC = Path(__file__).resolve().parents[1] / "docs" / "pmbok-mapping.md"
ROOT = DOC.parents[1]
CITATION = re.compile(r"`(driftless/[\w/]+\.py):(\w+)`")
NUMBERED = re.compile(r"`driftless/[\w/.-]+\.py:\d+")
SPAN = re.compile(r"`([^`\n]+)`")
BOUNDARY = "## Not implemented"
EQUIVALENCES_HEADING = "## Agile equivalences"

WRITTEN = DOC.read_text()
FLAT = " ".join(WRITTEN.split())  # phrase checks survive a re-wrap of the prose


def _defines(line: str, symbol: str) -> bool:
    """Whether ``line`` IS ``symbol``'s definition, at module level.

    Column zero on purpose, unlike a lenient ``lstrip``: a local variable that happens to
    share the name is not what a reader following the citation is being sent to.
    """
    return bool(re.match(rf"(def|class)\s+{symbol}\b", line) or re.match(rf"{symbol}\s*[:=]", line))


def _kinds(section: str) -> set[str]:
    """The artifact kinds named in ``section`` — a code span IS the whole name.

    The vocabulary is the catalog's plus the resolvers', because ``status_report`` is a
    resolver key no process names as an output, and the doc has to be able to say so.
    """
    vocabulary = ARTIFACT_KINDS | set(mapping.RESOLVERS)
    return {span for span in SPAN.findall(section) if span in vocabulary}


def test_every_citation_names_a_symbol_that_file_defines() -> None:
    cited = CITATION.findall(WRITTEN)
    assert len(cited) >= 30, f"only {len(cited)} citations — the mapping lost its grounding"
    wrong = []
    for path, symbol in cited:
        source = ROOT / path
        lines = source.read_text().splitlines() if source.exists() else []
        if not any(_defines(line, symbol) for line in lines):
            wrong.append(f"{path} defines no {symbol}")
    assert not wrong, "stale citations:\n" + "\n".join(wrong)


def test_no_citation_addresses_a_line_number() -> None:
    """The rule, not just this file's current state: a line number is a claim that goes
    stale on the next insertion above it, in a document nobody re-reads while editing code.
    A symbol moves with the thing it names."""
    assert not NUMBERED.findall(WRITTEN), (
        f"line-numbered citations are back: {NUMBERED.findall(WRITTEN)} — "
        "cite the symbol instead, so it survives an insertion above it"
    )


def test_the_counts_are_the_catalogs_own() -> None:
    unassessable = [p for p in catalog.PROCESSES if not is_assessable(p)]
    resolvable = ARTIFACT_KINDS & set(mapping.RESOLVERS)
    facts = (
        f"catalog holds {len(catalog.PROCESSES)} processes naming {len(ARTIFACT_KINDS)} "
        f"artifact kinds, of which {len(resolvable)} resolve against the store",
        f"{len(unassessable)} of the {len(catalog.PROCESSES)} processes have no tracked output",
    )
    missing = [fact for fact in facts if fact not in FLAT]
    assert not missing, f"pmbok-mapping.md no longer states: {missing}"


def test_the_supported_half_resolves_and_the_absent_half_does_not() -> None:
    supported, boundary, absent = WRITTEN.partition(BOUNDARY)
    assert boundary, f"pmbok-mapping.md lost its {BOUNDARY!r} section — the point of the doc"

    claimed = _kinds(supported)
    assert claimed == set(mapping.RESOLVERS), (
        "the supported half must name every tracked kind and no other; "
        f"missing {sorted(set(mapping.RESOLVERS) - claimed)}, "
        f"untracked but claimed {sorted(claimed - set(mapping.RESOLVERS))}"
    )

    denied = _kinds(absent)
    assert denied, "the non-goals name no artifact kind — the boundary is unevidenced"
    tracked = sorted(kind for kind in denied if mapping.is_tracked(kind))
    assert not tracked, f"listed as not implemented but the store resolves it: {tracked}"


def test_the_agile_equivalences_table_is_walked_from_the_code_it_describes() -> None:
    """The table names every ``crosswalk.EQUIVALENCES`` entry's own ``native_source``
    and ``rule_in_plain_words`` — a doc test walking the code, never a restatement a
    later edit to ``crosswalk.py`` could leave stale."""
    section, boundary, _ = WRITTEN.partition(BOUNDARY)
    equivalences_start = section.find(EQUIVALENCES_HEADING)
    assert equivalences_start != -1, f"pmbok-mapping.md lost its {EQUIVALENCES_HEADING!r} section"
    table = section[equivalences_start:]
    missing = []
    for kind, equivalence in crosswalk.EQUIVALENCES.items():
        if f"`{kind}`" not in table:
            missing.append(f"{kind}: kind not named")
        if equivalence.native_source not in table:
            missing.append(f"{kind}: native_source not named verbatim")
        if equivalence.rule_in_plain_words not in table:
            missing.append(f"{kind}: rule_in_plain_words not named verbatim")
    assert not missing, "\n".join(missing)


def test_a_fence_with_no_run_marker_still_fails() -> None:
    unmarked = [
        WRITTEN[: fence.start()].count("\n") + 1
        for fence in FENCED.finditer(WRITTEN)
        if not WRITTEN[: fence.start()].endswith("-->\n")
    ]
    assert not unmarked, f"pmbok-mapping.md lines {unmarked}: a fenced block with no run marker"
