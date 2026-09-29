"""The technique library as pages: ``GET /techniques`` and ``GET /techniques/{slug}``.

``driftless.pmbok.definitions.TECHNIQUES`` holds a written explanation of every
member of the closed ``tt.TT_CATALOG`` — summary, when to use, when to avoid,
ordered steps, outputs, pitfalls, a worked example, and the PMBOK-6 clause it
comes from where the edition defines one — and until these two routes existed
none of it was reachable from the running app. A
process page listed its Tools & Techniques as humanized names, so a reader who
followed the app's own recommendation to apply a technique arrived at the word
for it.

Top-level ``/techniques`` rather than something under ``/pmbok/``: that prefix
already holds ``/pmbok/{process_id}``, and a sibling literal segment beneath it
would resolve by declaration order rather than by shape.

**Keyed by the slug, not by the registry key.** ``/techniques/earned-value-analysis``
is the same word the ITTO page already writes as ``id="tt-earned-value-analysis"``
and the address ``Action.reference_href`` sends a reader to, so the surface has one
vocabulary rather than two — and no page ever prints the raw ``earned_value_analysis``
identifier a reader would have to decode. The slug comes from
:func:`driftless.naming.technique_slug`, the one formula the ITTO template also
reaches through its ``technique_slug`` filter and the model addresses with; nothing
here restates it.

Neither page reads the store or a clock, so this router takes no as-of: what it
renders is the frozen registry, identical on every request.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Project
from driftless.naming import technique_slug
from driftless.pmbok.definitions import (
    FAMILY_EXPLANATIONS,
    TECHNIQUES,
    TechniqueDefinition,
    TechniqueFamily,
)
from driftless.services.technique_runs import runs_for_project
from driftless.web.as_of import as_of_dependency
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
from driftless.pmbok.worksheets import WORKSHEETS
from driftless.web.errors import PageRoute
from driftless.web.related import for_technique
from driftless.web.templating import TEMPLATES


def support_tier(key: str) -> str:
    """One technique's support tier, in plain words: "Runnable here" once
    ``ASSISTANT_ROUTES`` names a launch route for it, else "Guide only — " followed
    by the exact sentence its ``GUIDE_ONLY_REASONS`` entry records.
    ``tests/test_launcher_totality.py`` pins that every ``TECHNIQUES`` key is one or
    the other, never both and never neither, so the lookup below cannot miss.
    """
    if key in ASSISTANT_ROUTES:
        return "Runnable here"
    return f"Guide only — {GUIDE_ONLY_REASONS[key].why}"


def support_tier_href(key: str, project: int | None) -> str | None:
    """Where the "Runnable here" sentence should link to, or ``None`` when it must
    stay plain text.

    Driven by the same ``ASSISTANT_ROUTES`` registry ``support_tier`` reads — never
    a second, hand-maintained list of which techniques have an assist page, which
    is exactly the kind of list this codebase refuses to keep in sync by hand.
    Every route in that registry takes a ``project_id``, so without one in scope
    (no ``?project=`` on this page) there is no address to fill it with; the
    sentence renders as words, not a link to a route that isn't there.
    """
    route = ASSISTANT_ROUTES.get(key)
    if route is None or project is None:
        return None
    return route.format(project_id=project)


#: The index's own tier words. The detail page says "Guide only — <reason>" in a
#: sentence; a column has room for neither the prefix nor a paraphrase, so the two
#: launchable tiers are named here once and the third IS the recorded reason.
RUNNABLE_TIER = "Runnable here"
WORKSHEET_TIER = "Worksheet"


def index_support_tier(key: str) -> str:
    """One technique's tier as the library index prints it, in three words or the
    registry's own sentence.

    Derived from the three registries that decide it, never typed per row:
    ``ASSISTANT_ROUTES`` names a launchable assistant, ``WORKSHEETS`` a printable
    worksheet, and everything left carries a ``GUIDE_ONLY_REASONS`` entry verbatim —
    ``tests/test_launcher_totality.py`` pins that the last lookup cannot miss.

    Distinct from :func:`support_tier`, which the DETAIL page renders as a sentence: a
    worksheet is not an assistant, so a technique that has one is still guide-only there
    while this column can say the more useful thing about it.
    """
    if key in ASSISTANT_ROUTES:
        return RUNNABLE_TIER
    if key in WORKSHEETS:
        return WORKSHEET_TIER
    return GUIDE_ONLY_REASONS[key].why


def tier_counts() -> dict[str, int]:
    """How many techniques sit in each tier, counted off the registries at call time.

    The page states these three numbers beside the key. Counting them here rather than
    writing them into the template is what stops the prose from outliving the fact the
    day an assistant or a worksheet ships.
    """
    counts = {"runnable": 0, "worksheet": 0, "guide": 0}
    for key in TECHNIQUES:
        tier = index_support_tier(key)
        name = (
            "runnable"
            if tier == RUNNABLE_TIER
            else "worksheet"
            if tier == WORKSHEET_TIER
            else "guide"
        )
        counts[name] += 1
    return counts


def slug_index(definitions: Mapping[str, TechniqueDefinition]) -> dict[str, str]:
    """``{slug: key}`` for ``definitions``, refusing a collision rather than losing
    a technique to one.

    Two keys that slug to the same word would leave exactly one of them reachable
    and the other silently gone — a 404 on a technique the library lists, with
    nothing anywhere else in the tree to notice. The registry is frozen at import,
    so raising here is a startup failure naming both offenders, not a runtime one.
    """
    index: dict[str, str] = {}
    for key in definitions:
        slug = technique_slug(key)
        if (taken := index.get(slug)) is not None:
            raise ValueError(
                f"{key!r} and {taken!r} both slug to {slug!r}; one would be unreachable"
            )
        index[slug] = key
    return index


#: Every technique reachable by its URL word. Built once, at import, from the frozen
#: registry — so a colliding key fails the process rather than one page.
BY_SLUG: dict[str, str] = slug_index(TECHNIQUES)


def library() -> list[tuple[str, tuple[tuple[str, TechniqueDefinition, str], ...]]]:
    """The whole registry as ``(family value, ((slug, technique), ...))``, in enum
    order and display-name order within a family.

    Built by walking ``TECHNIQUES`` — never a list of families written here — so a
    family that gains a technique gains a row, and a family declared in
    ``TechniqueFamily`` with nothing in it is simply absent rather than an empty
    heading. Each row carries the slug ``BY_SLUG`` resolves, so the index links to
    the address the detail route actually answers, and the support tier
    :func:`index_support_tier` derives, so the column cannot drift from the registries.
    """
    grouped: dict[str, list[TechniqueDefinition]] = {}
    for definition in TECHNIQUES.values():
        grouped.setdefault(definition.family.value, []).append(definition)
    return [
        (
            family.value,
            tuple(
                (technique_slug(d.key), d, index_support_tier(d.key))
                for d in sorted(grouped[family.value], key=lambda d: d.display_name)
            ),
        )
        for family in TechniqueFamily
        if family.value in grouped
    ]


def create_techniques_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The two technique-library pages. The registry itself is frozen — the as-of
    is only for the optional ``?project=`` run listing on the detail page."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/techniques", response_class=HTMLResponse)
    def technique_index(request: Request) -> HTMLResponse:
        """Every technique in the closed catalog, grouped by family, each row
        carrying its summary so the index answers "which one do I want?" on its own
        before anybody follows a link."""
        return TEMPLATES.TemplateResponse(
            request,
            "techniques.html",
            {
                "families": library(),
                "family_explanations": FAMILY_EXPLANATIONS,
                "tier_counts": tier_counts(),
                "total": len(TECHNIQUES),
            },
        )

    @router.get("/techniques/{slug}", response_class=HTMLResponse)
    def technique_detail(
        request: Request,
        slug: str,
        db: Db,
        project: int | None = None,
        at: date = Depends(resolve_as_of),
    ) -> HTMLResponse:
        """One technique in full, found by the same word its ITTO anchor uses. A
        slug no technique answers to 404s rather than 500s, the same way
        ``/pmbok/{process_id}`` handles a clause the catalog never had. With
        ``?project=`` it also lists the runs recorded for that project — and an id
        no ``Project`` row answers to 404s the same way ``fetch`` does everywhere
        else, rather than rendering as an empty run list."""
        key = BY_SLUG.get(slug)
        if key is None:
            raise HTTPException(404, f"unknown technique: {slug}")
        live = None
        if project is not None:
            resolved_project = fetch(db, Project, project)
            live = {"project": resolved_project, "as_of": at.isoformat()}
        runs = runs_for_project(db, project, at) if project is not None else []
        runs = [r for r in runs if r.technique_key == key]
        context = {
            "technique": TECHNIQUES[key],
            "runs": runs,
            "support_tier": support_tier(key),
            "support_tier_href": support_tier_href(key, project),
            "related": for_technique(key),
            "live": live,
        }
        return TEMPLATES.TemplateResponse(request, "technique_detail.html", context)

    return router
