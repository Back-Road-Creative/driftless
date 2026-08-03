"""``docs/pmbok-mapping.md`` is checked, not just written — the reference-doc form of the
guides' executable convention. It is a table, not a script, so there is nothing to *run*; what
makes it un-rottable is that every claim in it is a claim about code this test reads. A
``path:line symbol`` citation must name that symbol defined at that line, the counts must be
the live catalog's own, and the supported/absent boundary must be the store's: a kind named in
the supported half resolves, a kind named under **Not implemented** does not. Implement one of
the declared non-goals and this goes red until the document says so. The guides' rule that a
fence with no run marker fails is inherited too, so nobody can slip an unrun command in later.
"""

from __future__ import annotations

import re
from pathlib import Path

from test_docs_agent_guide import FENCED

from driftless.pmbok import catalog, mapping
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.state import is_assessable

DOC = Path(__file__).resolve().parents[1] / "docs" / "pmbok-mapping.md"
ROOT = DOC.parents[1]
CITATION = re.compile(r"`(driftless/[\w/]+\.py):(\d+) (\w+)`")
SPAN = re.compile(r"`([^`\n]+)`")
BOUNDARY = "## Not implemented"

WRITTEN = DOC.read_text()
FLAT = " ".join(WRITTEN.split())  # phrase checks survive a re-wrap of the prose


def _defines(line: str, symbol: str) -> bool:
    """Whether ``line`` IS ``symbol``'s definition: a def, a class, or a module constant."""
    return bool(re.match(rf"(def|class)\s+{symbol}\b", line) or re.match(rf"{symbol}\s*[:=]", line))


def _kinds(section: str) -> set[str]:
    """The artifact kinds named in ``section`` — a code span IS the whole name.

    The vocabulary is the catalog's plus the resolvers', because ``status_report`` is a
    resolver key no process names as an output, and the doc has to be able to say so.
    """
    vocabulary = ARTIFACT_KINDS | set(mapping.RESOLVERS)
    return {span for span in SPAN.findall(section) if span in vocabulary}


def test_every_citation_names_that_symbol_at_that_line() -> None:
    cited = CITATION.findall(WRITTEN)
    assert len(cited) >= 30, f"only {len(cited)} citations — the mapping lost its grounding"
    wrong = []
    for path, number, symbol in cited:
        lines = (ROOT / path).read_text().splitlines() if (ROOT / path).exists() else []
        line = lines[int(number) - 1] if 0 < int(number) <= len(lines) else "<past end of file>"
        if not _defines(line, symbol):
            wrong.append(f"{path}:{number} does not define {symbol}: {line.strip()!r}")
    assert not wrong, "stale citations:\n" + "\n".join(wrong)


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


def test_a_fence_with_no_run_marker_still_fails() -> None:
    unmarked = [
        WRITTEN[: fence.start()].count("\n") + 1
        for fence in FENCED.finditer(WRITTEN)
        if not WRITTEN[: fence.start()].endswith("-->\n")
    ]
    assert not unmarked, f"pmbok-mapping.md lines {unmarked}: a fenced block with no run marker"
