"""Which credential authenticated a request, and what that means for CSRF.

One home for a vocabulary two sides share. :class:`driftless.api.secure.TokenGate`
stamps the kind on the ASGI scope once per request; the web write path reads it to decide
whether the double-submit pair applies. Neither idea belongs to any one page, and both
used to live in ``web/pages.py`` — so the gate imported the ITTO page module to learn its
own words, and every write route carved out of that module had to import it back.

This module still satisfies the constraint that put the names on the web side: the gate
wraps the finished app, so it can import from ``driftless.web``, and the reverse would be
an import cycle. Nothing here imports the gate.
"""

from __future__ import annotations

from fastapi import Request

from driftless.web import csrf

#: Scope-state key the gate stamps the credential kind under.
CREDENTIAL_KEY = "credential"
COOKIE_CREDENTIAL = "cookie"  # ambient: the browser attaches it, unasked
TOKEN_CREDENTIAL = "token"  # a per-user ``dfl_…`` bearer
SHARED_CREDENTIAL = "shared"  # the bootstrap ``DRIFTLESS_API_TOKEN`` bearer

#: The kinds a caller attaches on purpose — the ones a pair would prove nothing about.
DELIBERATE = frozenset({TOKEN_CREDENTIAL, SHARED_CREDENTIAL})


def require_pair_unless_bearer(request: Request, csrf_token: str) -> None:
    """The CSRF double submit, checked only where cross-site forgery is a threat.

    Forgery works because a browser attaches an *ambient* credential — a cookie — to a
    request some other origin caused, so the pair is what proves the caller could read
    our own cookie. A bearer token is not ambient: the caller attaches it deliberately
    and no cross-origin page can make a browser send one, so there is nothing left for a
    pair to prove. Session-versus-token is the same split mainstream frameworks make, and
    it is written down because "we skipped CSRF here" reads like a bug to anyone who does
    not know why.

    Fail closed on everything else. An unstamped scope — the app running without the gate
    — takes the pair, and so does a cookie request; the gate gives the cookie precedence
    when BOTH arrive, so attaching a header can never drop a browser's pair.
    """
    if (request.scope.get("state") or {}).get(CREDENTIAL_KEY) in DELIBERATE:
        return
    csrf.require(request, csrf_token)
