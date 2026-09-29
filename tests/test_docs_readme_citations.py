"""``README.md`` is the service's front door, and one line of it once cited
``api/app.py:1049-1076`` for ``create_sign_off`` — a line number, on a path
that was already wrong (the real file is ``driftless/api/app.py``). The
function had moved to line 1253 by the time anyone checked; nothing had ever
read the citation, so a true claim quietly became a false address without
anyone editing the file. That citation is a SYMBOL citation now
(``driftless/api/app.py:create_sign_off``), the same convention
``tests/test_docs_competitors.py`` and ``tests/test_docs_pmbok_mapping.py``
already enforce for their own docs — a symbol survives an insertion above it,
where a line number does not.

Whether a path defines the cited symbol is answered by parsing the file with
``ast``, not a substring search: a name that merely appears in a comment or a
docstring is not a definition, matching the distinction the other two guards'
docstrings already draw.

The citation pattern below does not require backticks. The stale citation
this file guards against was itself unbackticked before it was fixed, and the
line-number check in particular needs to catch a number whether or not
whoever typed it remembered to wrap it in code formatting.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
# The front door plus EVERY tracked document, discovered rather than listed. The list
# used to name two files, and the stale citation this suite exists to catch had already
# moved into a third: docs/decisions-superseded.md quoted a module that no longer exists,
# passing because nothing looked at that file. A discovered set cannot be behind the
# directory — a document added tomorrow is covered the day it lands, including the ones
# that cite no source symbol yet, since those are exactly where the next citation gets
# typed.
DOCS = [README, *sorted((ROOT / "docs").glob("*.md"))]

# path.py:symbol — backticks optional, so a citation typed without them is still caught.
CITATION = re.compile(r"([\w./-]+\.py):(\w+)")
# The source extensions a citation may name. One list, shared by both patterns below.
#
# It is an explicit list rather than ``\w+`` because ``\w+`` also matches a host and
# port: ``127.0.0.1:5432`` reads as extension ``1`` line ``5432``, and
# ``//example.com:8080`` as extension ``com``. These documents have no such string
# today, but they document a service that now runs Postgres locally, so a connection
# example is a likely edit — and it would fail here claiming "line-numbered citations
# are back", which is both wrong and the kind of misleading red that teaches people to
# delete a test.
SOURCE_EXT = r"(?:py|md|sh|toml|ya?ml|css|html|js|txt|cfg|ini|lock|json)"
# path.ext:123 — a line number on a source extension, backticks optional.
NUMBERED = re.compile(rf"[\w./-]+\.{SOURCE_EXT}:\d+")
# A repo-anchored path with no symbol on it: ``driftless/web/pages.py``. Only paths whose
# first segment is a real top-level directory here are read as addresses, so the relative
# shorthand these documents use throughout (``report/engine.py``, ``ci.yml``, a sibling
# ``temporal-model.md``) is left alone — it names a file relative to a context the
# sentence supplies, and resolving it would need that context, not a rule.
ANCHORED = re.compile(rf"([\w-]+(?:\.[\w-]+)*/[\w./-]+\.{SOURCE_EXT})")
TOP_LEVEL = {entry.name for entry in ROOT.iterdir() if entry.is_dir()}


def _defines(source: str, symbol: str) -> bool:
    """Whether the parsed module defines ``symbol`` as a function, class or
    assigned name — never a string match, so a symbol named in a comment or a
    docstring does not count."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == symbol
        ):
            return True
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == symbol for target in node.targets
        ):
            return True
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == symbol
        ):
            return True
    return False


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.name)
def test_every_repo_anchored_path_a_document_names_exists(doc: Path) -> None:
    """A citation with no symbol on it drifts the same way one with a symbol does, and
    nothing read it. ``docs/decisions-superseded.md`` quoted a sentence out of
    ``driftless/web/pages.py`` for months after that module was split into four; the
    symbol check never saw it, because the citation named no symbol.

    Scoped to repo-anchored paths — first segment a real directory here — so the
    relative shorthand these documents use for a file the surrounding sentence has
    already located is not mistaken for a broken address."""
    missing = sorted(
        {
            path
            for path in ANCHORED.findall(doc.read_text())
            if path.split("/")[0] in TOP_LEVEL and not (ROOT / path).exists()
        }
    )
    assert not missing, (
        f"{doc.name} names files that do not exist: {missing} — repoint them at whatever "
        "holds that contract now, or drop the address."
    )


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.name)
def test_every_citation_names_a_symbol_that_file_defines(doc: Path) -> None:
    cited = CITATION.findall(doc.read_text())
    wrong = []
    for path, symbol in cited:
        source = ROOT / path
        if not source.exists():
            wrong.append(f"{path} does not exist")
            continue
        if not _defines(source.read_text(), symbol):
            wrong.append(f"{path} defines no {symbol}")
    assert not wrong, f"stale citations in {doc.name}:\n" + "\n".join(wrong)


def test_the_readme_still_carries_a_citation_to_check() -> None:
    """The teeth of the guard above, kept where they belong. Without this, deleting the
    last citation from the README turns every check here green by having nothing to
    check — the failure mode that let the original stale citation live. The floor is on
    the README specifically: it is the front door, and it is the file the drift
    happened in."""
    assert CITATION.findall(README.read_text()), (
        "the README cites no path.py:symbol any more — the citation guard now passes "
        "vacuously; restore a citation or retire this suite deliberately"
    )


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.name)
def test_no_citation_addresses_a_line_number(doc: Path) -> None:
    """The rule, not just this file's current state: a line number here is a claim
    that goes stale on the next insertion above it, in a document nobody re-reads
    while editing code. That is exactly how the ``create_sign_off`` citation drifted
    onto unrelated code. A symbol moves with the thing it names."""
    found = NUMBERED.findall(doc.read_text())
    assert not found, f"line-numbered citations are back in {doc.name}: {found} — cite the symbol"
