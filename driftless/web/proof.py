"""The totality proof as a page: ``GET /pmbok/proof``.

Mirrors :mod:`driftless.web.glossary` in shape: ``driftless.pmbok.proof.build_proof``
reads only frozen registries, so this router takes no as-of and no project — what it
renders is identical on every request. Read-only: nothing here writes, and nothing
it renders can be reached through a form.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from driftless.pmbok.proof import build_proof
from driftless.web import related
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: Gap shapes whose members are technique / artifact / process keys, or
#: ``method_key:practice_key`` pairs -- the vocabularies :mod:`driftless.web.related`
#: already knows how to address.
_TECHNIQUE_FIELDS = frozenset(
    {"orphan_techniques", "unexplained_techniques", "unlaunchable_techniques"}
)
_ARTIFACT_FIELDS = frozenset(
    {"orphan_artifacts", "unexplained_artifacts", "unlaunchable_artifacts"}
)
_PROCESS_FIELDS = frozenset({"unexplained_processes", "skipped_processes"})
_PRACTICE_FIELDS = frozenset({"orphan_method_practices", "uncrosswalked_method_practices"})


def member_href(field: str, member: str) -> str | None:
    """The page ``member`` -- one offending catalog key a gap shape reports --
    would open on, using the same href formulas every other catalog page
    already links through (``driftless.web.related``), never a second,
    hand-typed URL pattern. ``None`` for a gap shape whose members are not a
    catalog page's key at all -- an agile model class name, or a
    ``profile:process`` tailoring pair -- so the template can fall back to
    plain text rather than invent a page that does not exist.
    """
    if field in _TECHNIQUE_FIELDS:
        return related._href("technique", member)
    if field in _ARTIFACT_FIELDS:
        return related._href("artifact", member)
    if field in _PROCESS_FIELDS:
        return related._href("process", member)
    if field in _PRACTICE_FIELDS:
        method_key, _, practice_key = member.partition(":")
        return related._practice_href(method_key, practice_key)
    return None


def create_pmbok_proof_router() -> APIRouter:
    """The one totality-proof page. No as-of: it reads no store and no clock."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/pmbok/proof", response_class=HTMLResponse)
    def pmbok_proof(request: Request) -> HTMLResponse:
        """Every count ``pmbok.proof.build_proof()`` reports, plain-worded, plus
        the offending members for any that is not zero. The shapes, their headings
        and the sentence explaining each come from ``proof.GAP_SHAPES``, so a count
        added to ``Proof`` cannot render here as a bare label nobody worded."""
        proof = build_proof()
        context = {"proof": proof, "gaps": proof.gaps(), "member_href": member_href}
        return TEMPLATES.TemplateResponse(request, "pmbok_proof.html", context)

    return router
