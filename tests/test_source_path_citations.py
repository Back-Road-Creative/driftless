"""Every repo path a source file names must still exist.

``driftless/web/pages.py`` was split into per-page route modules and deleted, and
eighteen docstrings and template comments went on naming it: a reader following one
of those sentences landed on a file that is not there. Nothing caught it, because a
path inside a docstring or a Jinja comment is prose to every gate the repo runs.

``tests/test_docs_readme_citations.py`` is the same guard for ``docs/*.md``. This is
its source-side counterpart: it walks every ``.py`` and ``.html`` under ``driftless/``
— discovered, never listed — pulls out anything shaped like a module path, and fails
when the named file does not exist anywhere in the tree.

A *historical* mention is legitimate and must survive: "carved out of ``web/pages.py``"
tells a reader where the module came from, and scrubbing it would delete the only
record of the split. Tense cannot be told apart by regex, so this does not try. Every
surviving mention of a deleted path is instead recorded once in ``HISTORICAL_PATHS``
with the reason it is history, and that record is asserted *exactly equal* to the
observed set — so a new stale reference fails here, and so does an entry that outlives
the sentence it covered.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "driftless"

#: Directories that hold no authored source, only build or tool output.
_SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", "node_modules", "htmlcov", ".mypy_cache"})

#: A repo-anchored module path (``web/pages.py``) or a bare module name (``pages.py``).
#: The trailing lookahead stops ``foo.pyc`` and ``foo.pyi`` from matching as ``foo.py``.
_MODULE_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.py(?![A-Za-z0-9_])")

#: Mentions of a path that no longer exists, kept because the sentence around them is
#: history — where a module came from — rather than a claim about where behaviour lives
#: now. Keyed by the file that carries the mention and the mention itself.
HISTORICAL_PATHS: dict[tuple[str, str], str] = {
    ("driftless/web/business_detail.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module."
    ),
    ("driftless/web/credentials.py", "web/pages.py"): (
        "Records where the credential vocabulary used to live, and why it moved."
    ),
    ("driftless/web/pmbok_reference.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module."
    ),
    ("driftless/web/process_map.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module."
    ),
    ("driftless/web/raid_log.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module."
    ),
    ("driftless/web/sign_off.py", "web/pages.py"): (
        "Records what still tied this route to pages.py at the moment it was carved out."
    ),
    ("driftless/web/threat_board.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module."
    ),
    ("driftless/web/wizard_form.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module."
    ),
    ("driftless/web/wizard_pages.py", "web/pages.py"): (
        "Records which slice of the pages.py split produced this module, and what "
        "had to move before it could."
    ),
}


def _tracked_paths() -> set[str]:
    """Every file in the checkout, as a repo-relative posix path."""
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPO_ROOT.rglob("*")
        if path.is_file() and not _SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts)
    }


def _resolvable() -> set[str]:
    """Every way a real file may honestly be named: its full repo path and any
    trailing run of its segments, so ``web/pages.py`` and ``pages.py`` would both
    resolve against ``driftless/web/pages.py`` were it still there."""
    suffixes: set[str] = set()
    for path in _tracked_paths():
        parts = path.split("/")
        suffixes.update("/".join(parts[index:]) for index in range(len(parts)))
    return suffixes


def _source_files() -> list[Path]:
    """The authored ``.py`` and ``.html`` files under ``driftless/`` — discovered."""
    return sorted(
        path
        for pattern in ("*.py", "*.html")
        for path in SOURCE_ROOT.rglob(pattern)
        if path.is_file() and not _SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts)
    )


def _mentions() -> list[tuple[str, int, str]]:
    """Every module path named in a source file, as (file, line number, mention)."""
    found: list[tuple[str, int, str]] = []
    for path in _source_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            found.extend((relative, number, match.group()) for match in _MODULE_PATH.finditer(line))
    return found


def test_the_walk_finds_module_paths_to_check() -> None:
    """A guard that walks nothing passes for the wrong reason."""
    files = _source_files()
    assert len(files) > 1, "no source files discovered under driftless/"
    mentions = _mentions()
    assert mentions, "no module paths found in any source file — the extraction is broken"
    resolvable = _resolvable()
    assert any(mention in resolvable for _, _, mention in mentions), (
        "not one mention resolved to a real file — the resolution rule is broken, "
        "which would make every other assertion here vacuous"
    )


def test_every_module_path_named_in_source_resolves() -> None:
    resolvable = _resolvable()
    dangling = sorted(
        f"{path}:{number} names {mention}"
        for path, number, mention in _mentions()
        if mention not in resolvable and (path, mention) not in HISTORICAL_PATHS
    )
    assert not dangling, (
        "these sentences send a reader to a file that does not exist — say where the "
        "behaviour lives now, delete the claim if it is no longer true of any module, "
        "or record the mention in HISTORICAL_PATHS if it is deliberately history:\n"
        + "\n".join(dangling)
    )


def test_no_historical_exemption_outlives_its_sentence() -> None:
    """An exemption list that only ever grows stops meaning anything."""
    resolvable = _resolvable()
    observed = {(path, mention) for path, _, mention in _mentions() if mention not in resolvable}
    stale = sorted(set(HISTORICAL_PATHS) - observed)
    assert not stale, (
        f"{stale} are recorded in HISTORICAL_PATHS but no longer appear as a dangling "
        "mention — the sentence was rewritten or the file it named came back; delete "
        "the entry"
    )


def test_every_historical_exemption_names_a_real_file_and_a_reason() -> None:
    for (path, mention), reason in sorted(HISTORICAL_PATHS.items()):
        assert (REPO_ROOT / path).is_file(), f"{path} is exempted but does not exist"
        assert reason.strip(), f"{path} exempts {mention} with no reason given"
