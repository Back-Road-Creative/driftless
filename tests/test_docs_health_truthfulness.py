"""Prose about ``GET /health`` is checked against the route, not against a remembered string.

For one release the probe answered from a byte literal before auth, and three passages in two
operator documents said exactly that. The route now runs ``SELECT 1``
(:func:`driftless.api.app.health`), which made those passages false while the suite stayed
green — nothing here read the prose.

So the fence has two halves and the behavioural one runs first: point the app at a store that
cannot be opened and call ``/health``. A storeless probe answers 200 there; this one answers
503. Only a probe *proven* to depend on the store makes the storeless prose false, and the
scan runs off that finding rather than off an assumption — revert the route and this test
fails at the assertion, pointing at itself and the documents rather than at the paragraphs.

What the second half cannot do is read English. It knows the phrasings that shipped, so a
fresh way of saying the same false thing passes it, and a paragraph that *denies* the claim
trips it — write the truth affirmatively. It fences known-false prose; it does not prove a
document true.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from driftless.api.app import app, get_session
from driftless.db import new_engine, new_session_factory

ROOT = Path(__file__).resolve().parents[1]
# The claim as it shipped. Matched inside one blank-line-separated chunk, so a sentence about
# something else entirely, three paragraphs from the nearest `/health`, is not a hit.
STORELESS = re.compile(
    r"without\s+(?:ever\s+)?(?:touching|reaching|asking|querying)\s+the\s+"
    r"(?:database|store|db)\b",
    re.IGNORECASE,
)


def _health_without_a_store(tmp_path: Path) -> int:
    """``GET /health``'s status when the store cannot be opened at all.

    A real engine over a SQLite path inside a directory that does not exist — the same
    genuinely-unreachable store ``tests/test_schema_readiness.py`` uses, rather than a
    stand-in that would only prove this test's own mock was wired up.
    """
    url = f"sqlite:///{tmp_path / 'no-such-dir' / 'x.db'}"
    with new_session_factory(new_engine(url))() as session:
        app.dependency_overrides[get_session] = lambda: session
        try:
            return TestClient(app).get("/health").status_code
        finally:
            app.dependency_overrides.clear()


def _chunks(text: str) -> Iterator[tuple[int, str]]:
    """Each blank-line-separated chunk of markdown, with the line it starts on."""
    line = 1
    for chunk in text.split("\n\n"):
        yield line, chunk
        line += chunk.count("\n") + 2


def tracked_markdown(root: Path = ROOT) -> list[str]:
    """Every markdown path git tracks — the scan's scope, so nothing untracked is read."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.md"], cwd=root, capture_output=True, text=True, check=True
    )
    names = [name for name in listed.stdout.split("\0") if name]
    if gone := [name for name in names if not (root / name).is_file()]:
        pytest.fail(
            f"git tracks {gone} but the working tree has no such files — an uncommitted "
            "deletion, not false prose. Commit the deletion or restore the files; a raw "
            "FileNotFoundError mid-scan reads as a content failure and is not one."
        )
    return names


def test_no_document_says_the_health_probe_skips_the_store(tmp_path: Path) -> None:
    status = _health_without_a_store(tmp_path)
    assert status == 503, (
        f"/health answered {status} with a store that cannot be opened, so it no longer "
        "depends on one. The documents this guard fences are then the thing to rewrite — "
        "and so is this test."
    )

    tracked = tracked_markdown()
    assert tracked, "git listed no tracked markdown, so this guard scanned nothing"

    false = [
        f"{name}:{start + chunk[: found.start()].count(chr(10))} says {found.group(0)!r} of a "
        f"probe that answers 503 when the store cannot be opened"
        for name in tracked
        for start, chunk in _chunks((ROOT / name).read_text())
        if "/health" in chunk
        for found in [STORELESS.search(chunk)]
        if found
    ]
    assert not false, "documented liveness the route stopped having:\n" + "\n".join(false)


def test_an_uncommitted_deletion_fails_as_itself(tmp_path: Path) -> None:
    """A tracked-but-deleted document fails as a deletion, not as whatever read it first."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "doomed.md").write_text("gone\n")
    subprocess.run(["git", "add", "doomed.md"], cwd=tmp_path, check=True)
    (tmp_path / "doomed.md").unlink()
    with pytest.raises(pytest.fail.Exception, match="uncommitted deletion"):
        tracked_markdown(tmp_path)
