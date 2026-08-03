"""The ONE Jinja environment every page renders through, so no render forgets its
CSRF pair.

Seven routers each held their own ``Jinja2Templates`` over the same directory and had
to remember the token; three did, four did not — and ``base.html`` renders the
sign-out form on *every* page. A context processor makes the field half unforgettable
instead: it runs on every render and Starlette merges it AFTER the caller's context,
so no router can omit the token or pass a stale one. The cookie half cannot come from
a processor, which never sees a response, so it is attached in :meth:`TemplateResponse`
— the one point every page passes on the way out, holding both the rendered context and
the response that carries its cookie. Middleware would have to guess which responses
are pages, and would stamp the JSON API too.

Being ONE environment is also what makes every page strict at once. Starlette builds
its own lenient ``Environment`` from a ``directory=``, so the environment is built here
and handed over instead: under Jinja's default a name no route passed — a misspelt
``{{ as_off }}``, a field only an empty-state branch mentions — renders as the **empty
string**, and a page whose date quietly vanished still answers 200 with every test
green. ``undefined=StrictUndefined`` turns that into an ``UndefinedError`` at render
time, for all 22 templates at once and for pages not written yet. A name that is
legitimately absent is passed explicitly (``None``) or guarded with ``is defined``;
there is no exemption list and no second, laxer environment to move a page onto.
"""

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from starlette.templating import _TemplateResponse

from driftless.models import SIGNOFF_DECISIONS
from driftless.web import csrf


class _Templates(Jinja2Templates):  # Starlette's, plus the cookie half of what it rendered
    def TemplateResponse(self, *args: Any, **kwargs: Any) -> _TemplateResponse:
        page: _TemplateResponse = super().TemplateResponse(*args, **kwargs)
        csrf.attach(page, page.context[csrf.FIELD])  # the very token just rendered
        return page


_PAIR = [lambda request: {csrf.FIELD: csrf.ensure(request)}]  # the field half, every render
_ENV = Environment(  # what Starlette's ``directory=`` builds, plus the one thing it cannot
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(),  # HTML output: escaping is what keeps a name from being markup
    auto_reload=False,  # packaged templates move only with a deploy; no os.stat per warm render
    undefined=StrictUndefined,  # a name no route passed raises; it never renders blank
)
TEMPLATES = _Templates(env=_ENV, context_processors=_PAIR)
TEMPLATES.env.filters["humanize"] = lambda s: s.replace("_", " ").title()  # audit finding LOW
# The sign-off decision vocabulary, on the environment rather than in three page
# contexts: ``_signoff.html``'s select is built FROM it, so a decision the store accepts
# cannot be hand-listed out of the UI (``waived`` was, for as long as the ledger existed).
TEMPLATES.env.globals["signoff_decisions"] = SIGNOFF_DECISIONS
