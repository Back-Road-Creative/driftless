"""The artifact catalog as pages: ``GET /artifacts`` and ``GET /artifacts/{slug}``.

``driftless.pmbok.artifact_definitions.ARTIFACTS`` holds a written explanation of
every member of the closed ``ARTIFACT_KINDS`` vocabulary — what it is, why it
matters, what it looks like on this product, which processes produce and read it
(derived from the ITTO catalog itself), and whether this product's store can
track it — and until these two routes existed none of it was reachable from the
running app. An ITTO table showed only the humanized word for an input or
output, with nowhere for a reader to click through to; ``pmbok_detail.html``'s
``itto`` macro now links there the same way it already links a Tools &
Techniques entry to its technique page.

Top-level ``/artifacts`` for the same reason ``/techniques`` sits beside
``/pmbok`` rather than under it: a sibling literal segment under ``/pmbok/``
would resolve by declaration order rather than by shape.

**Keyed by the slug, not by the registry key.** ``/artifacts/project-charter``
is one word, addressed by :func:`driftless.web.templating.artifact_slug` — the
same formula the ITTO template reaches through its ``artifact_slug`` filter —
so no page ever prints the raw ``project_charter`` identifier a reader would
have to decode.

Without ``?project=`` this is the frozen registry, identical on every request.
With it, the detail page additionally shows what THIS project's store answers
for this one kind — the same per-kind resolution
``driftless.web.views.process_in_project`` already does for a whole process's
ITTO table, over a single ``mapping.resolve`` call rather than a whole
process's worth of them: exactly as cheap for one kind as one iteration of the
loop inside ``process_in_project`` is, so nothing here re-derives the store
read that drill page already trusts. The label/rank shaping around that one
``ArtifactStatus`` is a private helper on ``views`` (``_artifact_cell``), and a
module may not import another's private name
(``tests/test_package.py``), so it is repeated here as the four-line function
it is rather than exposed across the boundary for one caller.

**The path parameter is named ``kind_slug``, not ``slug``.** Both this route and
``/techniques/{slug}`` are ``PageRoute``s with one path parameter apiece, and
``bin/driftless-snapshot-pages.py`` fills every such parameter from the demo
store by parameter NAME — so two different routes sharing the name ``slug``
would collide onto one id list and one of the two would be snapshotted with
the other's word. Distinct names keep the two catalogs independent there.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Project
from driftless.pmbok import catalog, mapping
from driftless.pmbok.artifact_definitions import ARTIFACTS, ArtifactDefinition, ArtifactFamily
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.pmbok.worksheets import ARTIFACT_TEMPLATES
from driftless.web.related import for_artifact
from driftless.web.templating import TEMPLATES, artifact_slug


def slug_index(definitions: Mapping[str, ArtifactDefinition]) -> dict[str, str]:
    """``{slug: key}`` for ``definitions``, refusing a collision rather than losing
    an artifact kind to one — the same rule :func:`driftless.web.techniques.slug_index`
    applies to the technique library, over the artifact vocabulary instead.
    """
    index: dict[str, str] = {}
    for key in definitions:
        slug = artifact_slug(key)
        if (taken := index.get(slug)) is not None:
            raise ValueError(
                f"{key!r} and {taken!r} both slug to {slug!r}; one would be unreachable"
            )
        index[slug] = key
    return index


#: Every artifact kind reachable by its URL word. Built once, at import, from the
#: frozen registry — so a colliding key fails the process rather than one page.
BY_SLUG: dict[str, str] = slug_index(ARTIFACTS)


#: What each family groups together, in plain words — newly authored for this
#: page; no other surface explains the ``ArtifactFamily`` taxonomy today, unlike
#: ``driftless.pmbok.definitions.FAMILY_EXPLANATIONS`` for the technique
#: library's own (unrelated) family set. Grounded in ``driftless.pmbok.artifacts``'s
#: own grouping comments, never a paraphrase of a definition that does not exist.
FAMILY_EXPLANATIONS: dict[ArtifactFamily, str] = {
    ArtifactFamily.PLANS: (
        "Charters and the management plans they authorize — the intentions "
        "a project sets before the work starts."
    ),
    ArtifactFamily.BASELINES: (
        "The approved scope, schedule, cost and combined baselines that later "
        "progress is measured against."
    ),
    ArtifactFamily.DOCUMENTS: (
        "The working documents a process reads and revises as the project "
        "runs — logs, registers, estimates and the schedule's own detail."
    ),
    ArtifactFamily.PERFORMANCE: (
        "Raw work-performance data, turned into information, turned into the "
        "reports a stakeholder actually reads."
    ),
    ArtifactFamily.PROCUREMENT: (
        "What it takes to buy work from a seller and see it through — from "
        "the statement of work to a closed agreement."
    ),
    ArtifactFamily.DELIVERABLES: (
        "The product or result the project exists to produce, at each stage "
        "from built to verified to accepted."
    ),
    ArtifactFamily.CHANGES: ("Change requests and the ones a change control board has approved."),
    ArtifactFamily.ENVIRONMENT: (
        "What the organization brings to the project from outside it — its "
        "existing assets, its constraints, and the business case for doing "
        "the work at all."
    ),
}


def library() -> list[tuple[str, tuple[tuple[str, ArtifactDefinition], ...]]]:
    """The whole registry as ``(family value, ((slug, artifact), ...))``, in enum
    order and display-name order within a family — :func:`driftless.web.techniques.library`'s
    counterpart for the artifact vocabulary."""
    grouped: dict[str, list[ArtifactDefinition]] = {}
    for definition in ARTIFACTS.values():
        grouped.setdefault(definition.family.value, []).append(definition)
    return [
        (
            family.value,
            tuple(
                (artifact_slug(d.key), d)
                for d in sorted(grouped[family.value], key=lambda d: d.display_name)
            ),
        )
        for family in ArtifactFamily
        if family.value in grouped
    ]


def _cell(status: mapping.ArtifactStatus) -> dict[str, str]:
    """One artifact kind as this page reads it: a word for what the store knows, the
    ``.st-*`` wash the process map and the ITTO drill already use for that reading, and
    the resolver's own detail — the same shaping ``driftless.web.views._artifact_cell``
    does for a whole process's ITTO table, repeated here rather than imported (see the
    module docstring) because a private name crosses no module boundary.
    """
    if status.present:
        label, rank = ("healthy", "ok") if status.healthy else ("at risk", "warn")
    elif mapping.is_tracked(status.kind):
        label, rank = "absent", "muted"
    else:
        label, rank = "not tracked", "muted"
    return {"label": label, "rank": rank, "detail": status.detail}


_IDENTIFIER_PATTERN = re.compile(
    "|".join(re.escape(key) for key in sorted(ARTIFACTS, key=len, reverse=True))
)


def spell_out_identifiers(text: str) -> str:
    """``text`` with every raw ``ARTIFACT_KINDS`` key it names replaced by that
    kind's ``display_name`` — the disposition sentences in
    ``mapping.UNTRACKED_DISPOSITIONS`` are hand-authored prose that names other
    artifacts by their registry key (``"folded into schedule_baseline"``), and
    this is the only page that prints them, so the gloss happens here rather
    than in ``mapping.py`` itself. Longest key first, so a key that is a prefix
    of another (there are none today, but the registry is not closed against
    it) never leaves a partial match behind."""
    return _IDENTIFIER_PATTERN.sub(lambda m: ARTIFACTS[m.group(0)].display_name, text)


def _process_links(process_ids: tuple[str, ...]) -> list[tuple[str, str]]:
    """``(id, name)`` for every process id in ``process_ids`` — read off the
    frozen catalog rather than carried a second time, so a page can link
    ``/pmbok/{id}`` and print its name without the router repeating a lookup
    ``catalog.get`` already owns."""
    return [(process_id, catalog.get(process_id).name) for process_id in process_ids]


def create_artifacts_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The two artifact-catalog pages, defaulting to ``default_as_of`` for the
    project-scoped reading ``?project=`` asks for."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/artifacts", response_class=HTMLResponse)
    def artifact_index(request: Request) -> HTMLResponse:
        """Every artifact kind in the closed vocabulary, grouped by family, each
        row marked tracked or not from ``mapping.is_tracked`` — the same resolver
        partition ``ArtifactDefinition.tracked_by`` is derived from — and, where
        not tracked, ``mapping``'s own disposition sentence for why."""
        return TEMPLATES.TemplateResponse(
            request,
            "artifacts.html",
            {
                "families": library(),
                "family_explanations": FAMILY_EXPLANATIONS,
                "dispositions": {
                    key: spell_out_identifiers(sentence)
                    for key, sentence in mapping.UNTRACKED_DISPOSITIONS.items()
                },
            },
        )

    @router.get("/artifacts/{kind_slug}", response_class=HTMLResponse)
    def artifact_detail(
        request: Request,
        kind_slug: str,
        db: Db,
        project: int | None = None,
        at: date = Depends(resolve_as_of),
    ) -> HTMLResponse:
        """One artifact kind in full, found by the same word its ITTO link uses. A
        slug no kind answers to 404s rather than 500s, the same way
        ``/techniques/{slug}`` handles a word the library never had.

        With ``?project=`` the pinned as-of comes along for the same reading
        ``/pmbok/{id}?project=`` already gives a whole process — here narrowed
        to the one kind this page is about.
        """
        key = BY_SLUG.get(kind_slug)
        if key is None:
            raise HTTPException(404, f"unknown artifact: {kind_slug}")
        disposition = mapping.UNTRACKED_DISPOSITIONS.get(key)
        context: dict[str, Any] = {
            "artifact": ARTIFACTS[key],
            "produced_by": _process_links(ARTIFACTS[key].produced_by),
            "read_by": _process_links(ARTIFACTS[key].read_by),
            "related": for_artifact(key),
            "live": None,
            "disposition": spell_out_identifiers(disposition) if disposition else None,
            "template": ARTIFACT_TEMPLATES.get(key),
        }
        if project is not None:
            resolved_project = fetch(db, Project, project)
            context["live"] = {
                "project": resolved_project,
                "as_of": at.isoformat(),
                "cell": _cell(mapping.resolve(key, resolved_project, db, at)),
            }
        return TEMPLATES.TemplateResponse(request, "artifact_detail.html", context)

    return router
