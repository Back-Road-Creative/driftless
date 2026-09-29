"""The glossary as a page: ``GET /glossary``.

Mirrors :mod:`driftless.web.techniques` deliberately -- same shape, same
reasoning. ``driftless.pmbok.glossary.GLOSSARY`` is a frozen registry, so this
router reads no store and takes no as-of: what it renders is identical on
every request, and the whole vocabulary is one page rather than a page per
term, since the point of a glossary is that a reader can scan it in one pass.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from driftless.naming import technique_slug
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.methods import METHODS
from driftless.web.errors import PageRoute
from driftless.web.related import for_term
from driftless.web.templating import TEMPLATES, artifact_slug

#: Labels for the handful of whole-section pages a ``defined_on`` path can name
#: that no registry entry already carries a display name for -- copied from the
#: exact words ``base.html``'s ``nav_link`` calls already give these same
#: routes, so a term's "Where you meet it" link never invents a second name
#: for a page the primary nav already labels.
_SECTION_PAGE_LABELS = {
    "/pmbok": "PMBOK",
    "/methods": "Methods",
    "/scorecard": "Scorecard",
}

_TECHNIQUE_BY_SLUG = {technique_slug(key): key for key in TECHNIQUES}
_ARTIFACT_BY_SLUG = {artifact_slug(key): key for key in ARTIFACTS}


def _page_label(path: str) -> str:
    """A ``defined_on`` route path as the name a reader already knows it by --
    a registry's own ``display_name`` for a detail page, or the primary nav's
    own word for a whole-section page. Never a label typed fresh for this
    template: every source here is the same one another page's own link
    already reads."""
    if path in _SECTION_PAGE_LABELS:
        return _SECTION_PAGE_LABELS[path]
    prefix, _, slug = path.rpartition("/")
    if prefix == "/techniques" and slug in _TECHNIQUE_BY_SLUG:
        return TECHNIQUES[_TECHNIQUE_BY_SLUG[slug]].display_name
    if prefix == "/artifacts" and slug in _ARTIFACT_BY_SLUG:
        return ARTIFACTS[_ARTIFACT_BY_SLUG[slug]].display_name
    if prefix == "/methods" and slug in METHODS:
        return METHODS[slug].display_name
    raise KeyError(f"no label source for defined_on path {path!r}")


def create_glossary_router() -> APIRouter:
    """The one glossary page. No as-of: it reads no store and no clock."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/glossary", response_class=HTMLResponse)
    def glossary_index(request: Request) -> HTMLResponse:
        """Every term of art in alphabetical order by its display word, each
        carrying an id the ``gloss`` filter's links and every ``#term`` deep
        link resolve to."""
        entries = sorted(GLOSSARY.items(), key=lambda pair: pair[1].term.lower())
        related = {key: for_term(key) for key, _ in entries}
        defined_on_labels = {
            key: [(path, _page_label(path)) for path in entry.defined_on] for key, entry in entries
        }
        return TEMPLATES.TemplateResponse(
            request,
            "glossary.html",
            {"entries": entries, "related": related, "defined_on_labels": defined_on_labels},
        )

    return router
