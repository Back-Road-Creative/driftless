"""The wizard's two routes: the step form, and the one write that produces its output.

Carved out of ``web/pages.py`` last among the read/write pairs, because it needed two
earlier moves first: the CSRF-pair rule (``web/credentials.py``) and the form model
(``web/wizard_form.py``).

``wizard_apply`` is the only form POST with no JSON twin — ``/sign-offs`` and
``/status-snapshots`` both have one — so it is also the one write an agent drives with a
token, which is why it goes through ``require_pair_unless_bearer`` rather than
``csrf.require``. A refusal hands the FORM back with the typed prose still in its
textarea, never an error shell that destroys it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from driftless.api.deps import Db, resolved_actor
from driftless.api.records import fetch
from driftless.assess import adapters
from driftless.models import Project
from driftless.pmbok import catalog
from driftless.web import credentials, wizard_form
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES
from driftless.wizard import cli as wizard_cli


def _known_process_id(process_id: str) -> bool:
    """Whether the live catalog names ``process_id`` — the one guard both a
    ``?process=`` address and a posted ``origin_process_id`` are checked against,
    so a forged id reads the same wording ``api.schemas.ProcessId`` refuses it
    with, whichever surface catches it first."""
    try:
        catalog.get(process_id)
    except KeyError:
        return False
    return True


def create_wizard_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The wizard step form and its apply route, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/wizard", response_class=HTMLResponse)
    def wizard_page(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        process: str | None = None,
        method: str | None = None,
    ) -> HTMLResponse:
        """``?process=`` shows that process's own step instead of ``next_step``'s
        pointer — a derived/reference step's "produced by" link lands here, so a
        reader can go work a prerequisite lifecycle order has not reached yet.
        Unknown ids 404, the same wording ``api.schemas.ProcessId`` refuses one
        with, same as ``/pmbok/{process_id}``. ``?method=`` picks the Scrum or
        Kanban crosswalk the workspace shows for the step."""
        project = fetch(db, Project, project_id)
        if process is not None and not _known_process_id(process):
            raise HTTPException(404, f"{process!r} is not a PMBOK process id")
        return TEMPLATES.TemplateResponse(
            request,
            "wizard.html",
            wizard_form.wizard_context(db, project, at, process_id=process, method=method),
        )

    @router.post("/projects/{project_id}/wizard/apply")
    def wizard_apply(
        request: Request,
        project_id: int,
        db: Db,
        kind: Annotated[str, Form()],
        posted: Annotated[dict[str, str], Depends(wizard_form.posted_fields)],
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
        body: Annotated[str, Form()] = "",
        origin_process_id: Annotated[str | None, Form()] = None,
    ) -> Response:
        """Produce the step's output — the browser's form, and the one write an agent
        drives with a token: the other two form POSTs have JSON API routes
        (``/sign-offs``, ``/status-snapshots``) and this has none. A refusal hands
        the FORM back with the typed prose still in its textarea, never an error
        shell that destroys it."""
        credentials.require_pair_unless_bearer(request, csrf_token)  # before any read/write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)

        # ``field_id`` names the ONE input ``message`` is about — set only where this
        # module itself authored the refusal and so genuinely knows (the two body checks
        # below);
        # everything ``wizard_cli.produce`` raises stays general, since that prose is not
        # parsed for a field name it does not structurally carry. Threading it as a kwarg
        # rather than reshaping ``message`` at every call site keeps refuse() the one
        # place that decides which half of the alert macro a refusal lands in.
        def refuse(status: int, message: str, *, field_id: str | None = None) -> Response:
            # The hidden field is client-controlled bytes like any other: a forged id
            # must not crash the re-render ``step_for`` would give it — it falls back
            # to ``next_step``'s own pointer instead, exactly as a caller with no
            # ``origin_process_id`` at all sees. The forged id's OWN refusal is
            # ``produce``'s (the schema's ``ProcessId`` guard), already carried in
            # ``message`` above this call.
            shown = (
                origin_process_id
                if origin_process_id and _known_process_id(origin_process_id)
                else None
            )
            context = wizard_form.wizard_context(
                db,
                project,
                at,
                process_id=shown,
                body=body,
                posted=posted,
                error=None if field_id else message,
                field_errors={field_id: message} if field_id else None,
                method=request.query_params.get("method"),
            )
            return TEMPLATES.TemplateResponse(request, "wizard.html", context, status_code=status)

        if kind in wizard_form.BASELINE_KINDS and adapters.plan_baseline(project) is not None:
            # See wizard_form.BASELINE_KINDS: 409, nothing written.
            return refuse(
                409,
                f"{project.name} already has an approved baseline; producing {kind} "
                "again would re-baseline it. Raise a change request instead.",
            )
        # Exactly the fields THIS kind is made of, and nothing else the body carried. A
        # missing one is the producer's refusal (422 below): no surface substitutes a
        # value, because the presence checks only count rows and a substituted one would
        # mark the output produced for good.
        fields: dict[str, Any] = {
            name: posted[name] for name in wizard_cli.required_fields(kind) if name in posted
        }
        if origin_process_id:
            # The step's hidden field — validated by the schema, refused below as 422.
            fields["origin_process_id"] = origin_process_id
        if kind in wizard_cli.body_kinds():
            # A narrative kind IS its prose, so a blank one is refused rather than
            # written: the row would read as absent to ``mapping.resolve`` — an output
            # the wizard reports produced that every completeness figure still counts
            # missing — while its unique (project, kind) turns the honest retry that
            # carries the real text into a duplicate-key failure.
            if not (typed := body.strip()):
                return refuse(422, f"{kind} is a record of prose and needs a body", field_id="body")
            if len(typed) > wizard_form.BODY_MAX:
                return refuse(
                    422, f"{kind} holds at most {wizard_form.BODY_MAX} characters", field_id="body"
                )
            fields["body"] = typed
        try:
            wizard_cli.produce(db, project, kind, fields, at, resolved_actor(request))
        except (KeyError, ValueError) as error:
            # Every refusal ``produce`` raises is a ValueError — pydantic's
            # ValidationError, ``MissingBody``, and any producer-side guard a later
            # commit adds — so it renders the form here, never escapes as a 500.
            return refuse(422, str(error))
        return RedirectResponse(
            f"/projects/{project_id}/wizard?as_of={at.isoformat()}", status_code=303
        )

    return router
