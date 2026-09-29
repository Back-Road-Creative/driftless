"""The credential vocabulary and the CSRF-pair rule have ONE home, and it is not pages.py.

Which credential authenticated a request is the gate's vocabulary: ``api.secure.TokenGate``
stamps it on the ASGI scope, and the web write path reads it to decide whether the CSRF
double-submit pair applies. Both sides lived off ``web/pages.py``, which is the ITTO page
module and owns neither idea — so the gate imported a page module to learn its own words,
and every write route carved out of ``pages.py`` had to keep importing it back.

``web/credentials.py`` is that home. The rule it holds is a security boundary, so this
file pins it from both ends: the gate stamps the names this module defines, and the pair
is skipped for exactly the deliberate credentials and required for everything else —
including the unstamped scope, which is the app running with no gate at all.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from driftless.api import secure
from driftless.web import credentials


def _request(state: dict[str, object] | None) -> Request:
    scope: dict[str, object] = {"type": "http", "headers": [], "method": "POST", "path": "/x"}
    if state is not None:
        scope["state"] = state
    return Request(scope)  # type: ignore[arg-type]


def test_the_gate_reads_the_names_from_this_module() -> None:
    """``secure.py`` no longer reaches into the page module for its own vocabulary."""
    source = (secure.__file__ or "").rsplit("/", 1)[-1]
    assert source == "secure.py"
    assert "pages.CREDENTIAL_KEY" not in _text(secure)
    assert "credentials.CREDENTIAL_KEY" in _text(secure)


def _text(module: object) -> str:
    from pathlib import Path

    return Path(getattr(module, "__file__", "")).read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", [credentials.TOKEN_CREDENTIAL, credentials.SHARED_CREDENTIAL])
def test_a_deliberate_credential_skips_the_pair(kind: str) -> None:
    """A bearer is not ambient: no cross-origin page can make a browser send one."""
    credentials.require_pair_unless_bearer(_request({credentials.CREDENTIAL_KEY: kind}), "")


@pytest.mark.parametrize(
    "state",
    [None, {}, {"credential": "cookie"}],
    ids=["unstamped-scope", "empty-state", "cookie"],
)
def test_everything_else_must_present_the_pair(state: dict[str, object] | None) -> None:
    """Fail closed — an ungated app takes the pair too, not a free pass."""
    with pytest.raises(HTTPException):
        credentials.require_pair_unless_bearer(_request(state), "")
