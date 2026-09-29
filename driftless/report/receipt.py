"""The reproducibility receipt on CLI markdown reports — the same primitives as
the web page footer (``driftless.web.receipt``), just a different trailer shape:
a rendered document is read as plain markdown, not HTML, so the receipt is a
trailing HTML-comment line (invisible wherever the markdown is viewed or
converted) rather than a footer inserted before ``</body>``.

The digest is computed over the document's own text BEFORE the receipt line is
appended — exactly like the web footer, and for the same reason: a footer that
hashed itself could never be verified by a reader who saves the document and
rehashes it. ``verify_receipt`` strips the trailing receipt line back off,
rehashes what remains, and compares — an untouched report verifies true, a
single edited byte anywhere verifies false.

``driftless proof reproduce`` (added on a sibling branch, not this one) should
call :func:`verify_receipt` on the rendered text it reads back, exactly as
``tests/test_report_receipt.py`` does here.
"""

from __future__ import annotations

from datetime import date

from driftless.calc import receipt as _receipt

_MARKER = "<!-- receipt: "


def attach_markdown_receipt(text: str, as_of: date) -> str:
    """Append the reproducibility receipt to ``text`` as a trailing HTML-comment
    line, computed over ``text`` exactly as it stood before this call."""
    line = _receipt.format_line(_receipt.digest(text.encode("utf-8")), as_of)
    return f"{text}\n{_MARKER}{line} -->\n"


def verify_receipt(rendered: str) -> bool:
    """Whether ``rendered``'s trailing receipt line names the true sha256 of
    everything before it."""
    idx = rendered.rfind(_MARKER)
    if idx == -1 or not rendered[:idx].endswith("\n"):
        return False
    body = rendered[: idx - 1]  # drop the single "\n" attach_markdown_receipt added
    return _receipt.verify_line(body.encode("utf-8"), rendered[idx:])
