"""The reproducibility receipt: a footer every computed page can carry, naming what
would have to match for a reader to reproduce it — the as-of, the schema revision
this build expects, the git SHA it was built from, and a sha256 of the page's own
content.

The hash is computed over the response body BEFORE this footer is added, never
after: a footer that hashed itself (including its own hash text) could not be
verified by a reader who saves the page and rehashes it, since the saved copy
would already carry a hash of something the reader cannot reproduce. Attaching
the footer AFTER hashing is what keeps "sha256 of this page" answerable — strip
the footer this module inserted back out, and the rest of the bytes hash to the
value it printed.

``GIT_SHA`` is read once, at import time, never per request: a deployed process's
build does not change while it runs, and reading the clock or the filesystem on
every render is exactly the kind of per-request drift the rest of this codebase
goes out of its way to avoid. A checkout with no ``.git`` (a packaged install with
no working tree) and no override falls back to ``"unknown"`` rather than raising —
the receipt is honest about not knowing, not a reason to refuse to render the page.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TypeVar

from starlette.responses import Response

from driftless.calc import receipt as _receipt
from driftless.db.schema_version import EXPECTED_REVISION

_R = TypeVar("_R", bound=Response)

#: Back-compat aliases — the git-sha resolution and its env override now live in
#: ``driftless.calc.receipt`` (shared with the CLI report and CSV export
#: receipts), never reimplemented here a second way.
_GIT_SHA_ENV = _receipt.GIT_SHA_ENV
_read_git_sha = _receipt.read_git_sha
GIT_SHA: str = _receipt.GIT_SHA

_FOOTER = (
    '<p class="breadcrumbs">Computed {as_of} · schema {schema} · '
    "build {git_sha} · sha256 {digest}</p>"
)
_MARKER = '<p class="breadcrumbs">Computed '
_FOOTER_RE = re.compile(
    r'<p class="breadcrumbs">Computed \S+ · schema \S+ · '
    r"build \S+ · sha256 (?P<digest>[0-9a-f]{64})</p>"
)


def attach_receipt(response: _R, as_of: date) -> _R:
    """Insert the reproducibility footer into ``response`` in place, and return it.

    The sha256 is computed over ``response.body`` exactly as it stood before this
    call — the footer itself is never part of what it hashes. Inserted just before
    the closing ``</body>`` tag when one is present (every page rendered through
    ``base.html`` has one); appended to the end otherwise, so a caller handing this
    a body-less fragment still gets a receipt rather than a silent no-op.
    """
    body = bytes(response.body)
    digest = _receipt.digest(body)
    footer = _FOOTER.format(
        as_of=as_of.isoformat(), schema=EXPECTED_REVISION, git_sha=GIT_SHA, digest=digest
    )
    text = body.decode("utf-8")
    marker = "</body>"
    new_text = text.replace(marker, footer + marker, 1) if marker in text else text + footer
    response.body = new_text.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def verify_receipt(page: str) -> bool:
    """Whether a saved HTML page's reproducibility footer names the true sha256
    of everything else in the page — the read-back counterpart to
    :func:`attach_receipt`. Strips the exact footer :func:`attach_receipt`
    inserted back out (wherever it landed: before ``</body>`` or appended) and
    rehashes what remains, exactly as ``driftless.report.receipt.verify_receipt``
    does for a saved markdown report."""
    match = _FOOTER_RE.search(page)
    if match is None:
        return False
    without_footer = page[: match.start()] + page[match.end() :]
    return _receipt.digest(without_footer.encode("utf-8")) == match.group("digest")
