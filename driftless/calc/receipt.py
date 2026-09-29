"""Pure reproducibility-receipt primitives shared by every rendered surface: the
web HTML footer (``driftless.web.receipt``), the CLI markdown report trailer
(``driftless.report.receipt``) and the CSV export header (``driftless.api.export``).

The git SHA resolution and the sha256 digest live here ONCE so no caller
reimplements hashing or the git-sha fallback chain — see ``read_git_sha``'s
docstring for why it never raises, and ``GIT_SHA``'s for why it is read once at
import rather than per call.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from datetime import date
from pathlib import Path

from driftless.db.schema_version import EXPECTED_REVISION

#: Set by a deployment that knows its own build SHA (e.g. baked in at image build
#: time) so a packaged install with no ``.git`` working tree can still report one.
GIT_SHA_ENV = "DRIFTLESS_GIT_SHA"
_REPO_ROOT = Path(__file__).resolve().parents[2]
UNKNOWN = "unknown"
_DIGEST_RE = re.compile(r"sha256 ([0-9a-f]{64})")


def read_git_sha() -> str:
    """The running build's git SHA: the env override, else ``git rev-parse HEAD``
    against this checkout, else ``"unknown"`` — never raises."""
    override = os.environ.get(GIT_SHA_ENV)
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    sha = result.stdout.strip()
    return sha or UNKNOWN


#: Read once at import — a deployed process's build does not change while it
#: runs, so re-reading the filesystem per request would be per-request drift
#: this codebase otherwise goes out of its way to avoid.
GIT_SHA: str = read_git_sha()


def digest(body: bytes) -> str:
    """sha256 hex digest of ``body`` — the one hashing implementation every
    receipt surface calls, so no caller re-derives it a second way."""
    return hashlib.sha256(body).hexdigest()


def format_line(digest_hex: str, as_of: date | None = None) -> str:
    """The one-line receipt text: schema revision, build SHA and the digest, with
    an optional leading as-of for surfaces that have a point-in-time reading (a
    report). A live export (CSV of the current table) has none and omits it."""
    prefix = f"computed {as_of.isoformat()} | " if as_of is not None else ""
    return f"{prefix}schema {EXPECTED_REVISION} | build {GIT_SHA} | sha256 {digest_hex}"


def verify_line(body: bytes, line: str) -> bool:
    """Whether ``line`` (produced by :func:`format_line`) names the true sha256
    of ``body``. Used both to check a report's trailing receipt against the text
    before it and to check a CSV export's receipt header against its body."""
    match = _DIGEST_RE.search(line)
    if not match:
        return False
    return digest(body) == match.group(1)
