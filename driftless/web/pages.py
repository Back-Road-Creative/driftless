"""The ITTO web surface: threat board, process map, wizard, and the weekly-status
edit flow — server-rendered, and reachable on the same app the dashboard lives on.

Every write goes through the validated boundary the API and the wizard use — the
Pydantic schemas, the JSON routes themselves, the stamped-percent rule and
the ChangeLog — never a bespoke web-only path, so the single-write-path guarantee
holds from the browser too. Reads come from the assessment and process-state
engines. Pages degrade without JavaScript (a form posts and the server
re-renders); ``static/driftless.js`` only makes the swap feel instant.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.app import create_sign_off, create_status_snapshot, fetch, get_session
from driftless.api.app import signer, stamped_percent
from driftless.assess import adapters
from driftless.assess import engine as assess
from driftless.assess.feed import trend_delta as _trend_delta
from driftless.models import COST_CATEGORIES, CostEntry, Project, RAG_STATUSES, StatusSnapshot
from driftless.pmbok import catalog, mapping, state
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup
from driftless.report import gather
from driftless.wizard import cli as wizard_cli
from driftless.wizard import engine as wizard
from driftless.web import csrf
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]

# Which credential authenticated this request, stamped on the ASGI scope by the gate
# (:class:`driftless.api.secure.TokenGate`, which imports these). The names live on this
# side because the gate wraps the finished app: it can import a page module, and the
# reverse would be an import cycle. Read by :func:`_require_pair_unless_bearer`.
CREDENTIAL_KEY = "credential"
COOKIE_CREDENTIAL = "cookie"  # ambient: the browser attaches it, unasked
TOKEN_CREDENTIAL = "token"  # a per-user ``dfl_…`` bearer
SHARED_CREDENTIAL = "shared"  # the bootstrap ``DRIFTLESS_API_TOKEN`` bearer
_DELIBERATE = frozenset({TOKEN_CREDENTIAL, SHARED_CREDENTIAL})

# The stored ceiling on a narrative body, read off the schema that enforces it instead
# of retyped here: it becomes the textarea's own ``maxlength``, so the limit the API has
# always applied is one a browser meets at the form rather than as a 500 after the post.
_BODY_MAX: int = next(
    rule.max_length for rule in s.NarrativeArtifactIn.model_fields["body"].metadata
)

# The producible kinds that CREATE a plan baseline (one producer serves both).
# Producing one against a project already holding an APPROVED plan is a re-baseline:
# version N+1 irreversibly becomes the plan every EVM figure is measured against.
# That is a change-control decision, so the one-click form refuses it (409).
_BASELINE_KINDS = frozenset({"scope_baseline", "schedule_baseline"})


# How each collected field is typed and constrained in the browser, so a value the
# schema would refuse is one the form makes hard to enter: the vocabularies come from
# the ORM tuples the CHECK constraints are built from, never a hand-listed copy.
_FIELD_CHOICES: dict[str, tuple[str, ...]] = {
    "category": COST_CATEGORIES,
    "rag_status": RAG_STATUSES,
}
_FIELD_TYPE = {"target_date": "date"} | dict.fromkeys(
    ("probability", "impact", "planned_amount", "planned_cost", "target_value", "actual_value"),
    "number",
)


def _wizard_context(
    db: Session,
    project: Project,
    at: date,
    *,
    body: str = "",
    posted: dict[str, str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """The wizard page's context — built ONE way, for a GET and for a refused POST.
    A refusal re-renders the FORM, threading the posted ``body`` and fields back into
    their inputs (the POST replaced the page, so no history entry holds the words) with
    ``error`` above it. ``next_step`` rides the route-scoped prefetch cache."""
    with state.prefetched(db, [project]):
        step = wizard.next_step(db, project, at)
    # Which of THIS step's outputs are prose, read off the producer table rather
    # than listed here — so the form asks for a body exactly where one is stored.
    asks = sorted(set(step.producible) & wizard_cli.body_kinds()) if step else []
    offered = step.producible if step else ()
    return {
        # One input per field the offered kinds are made of, read off the same table the
        # producers refuse against — so a kind cannot be offered with no way to answer it.
        # `required` follows the body's rule: only where EVERY offered kind needs it.
        "field_asks": [
            {
                "name": name,
                "type": _FIELD_TYPE.get(name, "text"),
                "choices": _FIELD_CHOICES.get(name, ()),
                "value": (posted or {}).get(name, ""),
                "required": all(name in wizard_cli.required_fields(k) for k in offered),
            }
            for name in sorted({f for k in offered for f in wizard_cli.required_fields(k)})
        ],
        "project": project,
        "as_of": at.isoformat(),
        "step": step,
        "done": step is None,
        "body_kinds": asks,
        # The browser enforces `required` only where EVERY output on the step is
        # prose: 11.2 and 11.3 offer a risk register beside the assumption log, and
        # marking it there would block the kind that needs no body at all.
        "body_required": step is not None and asks == sorted(step.producible),
        "body_max": _BODY_MAX,
        "body": body,
        "error": error,
    }


async def _posted_fields(request: Request) -> dict[str, str]:
    """The wizard POST's whole form, so the route can forward the inputs the CHOSEN kind
    needs without growing a parameter per field of every producible kind. Async because
    Starlette parses a body that way and caches it; the route stays sync."""
    return {name: value for name, value in (await request.form()).items() if isinstance(value, str)}


def _require_pair_unless_bearer(request: Request, csrf_token: str) -> None:
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
    if (request.scope.get("state") or {}).get(CREDENTIAL_KEY) in _DELIBERATE:
        return
    csrf.require(request, csrf_token)


# Each of the five process states maps to one ``.st-*`` wash defined in base.html;
# the process-map legend renders from these SAME classes (via ``_LEGEND`` below), so
# a swatch can never drift from the cell it explains (findings #12 / #18):
#   produced → ok (green)     signed_off → signed (teal, distinct from produced)
#   in_progress → warn        waived → muted        not_started → muted (neutral,
# not alarming red — a not-yet-started process is no-data, not a failure).
STATE_RANK = {
    "produced": "ok",
    "signed_off": "signed",
    "waived": "muted",
    "in_progress": "warn",
    "not_started": "muted",
}
# The wash cannot be the state's only carrier, and on this grid it never could: two of
# the five states share the neutral ``muted`` wash on purpose, and the five washes sit
# under 1.2:1 from each other, so in greyscale, in print, or to a colour-blind reader the
# whole grid was one colour and a WAIVED process — tailored out of every completeness
# figure — read exactly like an untouched one that counts against it. ``sr-only`` text
# does not answer that (visually hidden) and ``title=`` does not either (hover only), so
# each state also carries a MARK: a visible glyph printed in the cell and in the legend
# chip that names it. The marks are SHAPES, never hues — an empty circle (nothing yet), a
# half-filled one (under way), a filled one (produced), a check (signed off) and an em
# dash (waived: the table convention for "not applicable", and deliberately not a cross —
# tailoring a process out is a decision, not a failure). Colour now only reinforces them.
STATE_MARK = {
    "produced": "\N{BLACK CIRCLE}",
    "signed_off": "\N{CHECK MARK}",
    "in_progress": "\N{CIRCLE WITH LEFT HALF BLACK}",
    "waived": "\N{EM DASH}",
    "not_started": "\N{WHITE CIRCLE}",
}
# The legend's fixed reading order, each state paired with its live ``.st-*`` class and
# the mark its cells print, so neither can drift from the grid it explains.
_LEGEND = [
    (st, STATE_RANK[st], STATE_MARK[st])
    for st in ("produced", "signed_off", "in_progress", "waived", "not_started")
]
# The sixth word the map needs — and the one ``ProcessState`` must never grow. 26 of the
# 49 catalog processes name no output the store holds a resolver for, so ``process_state``
# answers NOT_STARTED about the STORE (there was nothing to look for) and the cell printed
# it as a verdict on the PROJECT: work it owes and has not begun. Nothing is owed on any of
# them — the catalog not tracking them is a settled boundary, not a gap. ``is_assessable``
# is that distinction, so the map asks it and prints the same "not tracked" an artifact
# cell prints (:func:`_artifact_cell`): one vocabulary for one fact. It stays OUT of
# ``ProcessState``, whose five members reach the rollup counts, the wizard, the report and
# the API — none of which asks this question. It stays out of the legend too, and that is
# why it is a WORD and not a sixth mark: a word carries its own meaning into greyscale and
# print with no chip to decode it, so the five-chip legend still explains every mark drawn.
UNTRACKED = "not_tracked"
CELL_RANK = {**STATE_RANK, UNTRACKED: "muted"}
CELL_MARK: dict[str, str | None] = {**STATE_MARK, UNTRACKED: None}


def _cell_state(process: Process, proc_state: state.ProcessState) -> str:
    """The word the map prints for one process — never a state the process is not in.

    A recorded decision outranks the coverage fact: a waived or signed-off process shows
    what someone signed, tracked or not. Only the computed NOT_STARTED — the one answer an
    untracked process reaches with nobody having decided anything — is re-read as silence.
    """
    if proc_state is state.ProcessState.NOT_STARTED and not state.is_assessable(process):
        return UNTRACKED
    return proc_state.value


# The threat board slices the ranked feed into fixed pages so a large board stays
# readable; the template groups each page's cards by project (finding #22).
THREATS_PER_PAGE = 15

# Threat sign-off originates from both threats.html and the home rail, so the
# redirect target is a strict allowlist of known-safe paths rather than the posted
# value itself (the security audit found no open redirect here; this keeps it that
# way) — anything not in this set falls back to /threats.
_SIGN_OFF_REDIRECT_TARGETS = frozenset({"/", "/threats"})


def _sign_off_redirect(subject_kind: str, project_id: int | None, requested: str | None) -> str:
    """Where a sign-off lands — derived from the SUBJECT, not from a posted target.

    A process decision belongs to the map that drew the state it changes, and that path
    is per-project, so an allowlist of literals could never hold it. It is built here
    from the already-validated integer id instead: the path cannot be anything but one
    of ours, so the process side needs no allowlist entry and can carry no open redirect
    either. Threat sign-offs keep the fixed allowlist they always had.
    """
    if subject_kind == "process" and project_id is not None:
        return f"/projects/{project_id}/process-map"
    return requested if requested in _SIGN_OFF_REDIRECT_TARGETS else "/threats"


def create_pages_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The threat/process/wizard/edit pages, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    def _as_of(value: date | None) -> date:
        return value or resolve()

    @router.get("/threats", response_class=HTMLResponse)
    def threats(request: Request, db: Db, as_of: date | None = None, page: int = 1) -> HTMLResponse:
        """The ranked live-threat board, grouped by project and paginated.

        Each card names its project and links it to the project's process map, and
        lists the recommended PMBOK actions its assessment attached, so the board
        goes from "what is wrong" to "which project and what to do". Suppression and
        cross-store ranking stay with the assess engine (``top_threats``); the card
        build (``threat_cards``) only joins each threat to its project and actions.
        The ranked feed is sliced into ``THREATS_PER_PAGE`` pages BEFORE the template
        groups a page's cards by project — slicing keeps the ranked order, so the
        template only reshapes what it is handed. ``page`` is clamped into range, so
        an out-of-bounds page lands on a valid one. Reads are pure functions of the
        store and the as-of date, so a double fetch is byte-identical.
        """
        at = _as_of(as_of)
        ranked = threat_cards(db, at)
        total_pages = max(1, -(-len(ranked) // THREATS_PER_PAGE))
        page = max(1, min(page, total_pages))
        start = (page - 1) * THREATS_PER_PAGE
        context = {
            "as_of": at.isoformat(),
            "threats": ranked[start : start + THREATS_PER_PAGE],
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }
        return TEMPLATES.TemplateResponse(request, "threats.html", context)

    @router.post("/sign-off")
    def sign_off(
        request: Request,
        db: Db,
        subject_kind: Annotated[str, Form()],
        subject_ref: Annotated[str, Form()],
        decision: Annotated[str, Form()],
        signed_by: Annotated[str, Form()] = "web",
        project_id: Annotated[int | None, Form()] = None,
        as_of: Annotated[date | None, Form()] = None,
        next: Annotated[str | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Append one decision to the ledger, signed by whoever the gate resolved.

        The posted ``signed_by`` is a claim, not the record: a browser can type
        anything into it, and a sign-off names a person permanently (the ledger is
        append-only). So the signed-in user is stamped over it here, the same rule
        the JSON route applies — see :func:`driftless.api.app.signer`, which is the
        one place that decides, including when the field survives.

        The board's hidden ``signal`` input is a claim in the same way, and a worse
        one: it is the threshold a threat must regress past to come back, so a forged
        value muted it for good. There is no ``signal`` parameter above and none on
        ``SignOffIn`` — the posted field is unreachable rather than merely unused, and
        :func:`driftless.api.app.stamped_signal` computes what is stored. The row
        itself is written by calling the JSON route, so the two write paths are one.
        """
        csrf.require(request, csrf_token)  # before any read or write
        at = _as_of(as_of)
        payload = s.SignOffIn(
            project_id=project_id,
            subject_kind=subject_kind,  # type: ignore[arg-type]
            subject_ref=subject_ref,
            decision=decision,  # type: ignore[arg-type]
            signed_by=signer(request, signed_by or "web"),
            as_of=at,
        )
        create_sign_off(request, payload, db)
        target = _sign_off_redirect(payload.subject_kind, payload.project_id, next)
        return RedirectResponse(f"{target}?as_of={at.isoformat()}", status_code=303)

    @router.get("/projects/{project_id}/process-map", response_class=HTMLResponse)
    def process_map(
        request: Request, project_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        at = _as_of(as_of)
        # One prefetch scope for the whole render: project_process_states is
        # computed ONCE and threaded into _process_grid/area_completeness below
        # instead of each re-walking the store; state.completeness's own walk
        # still rides the same cache (see pmbok.state.prefetched).
        with state.prefetched(db, [project]):
            states = state.project_process_states(project, db, at)
            grid = _process_grid(states)
            rings = area_completeness(states)
            completeness = pct(state.completeness(project, db, at))
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "groups": [g.value for g in ProcessGroup],
            "areas": [a.value for a in KnowledgeArea],
            "grid": grid,
            "legend": _LEGEND,
            "completeness": completeness,
            # Raw per-area fractions drive the ring geometry; the pre-formatted
            # labels reuse pct so a ring's text can never drift from the header.
            "rings": rings,
            "ring_labels": {area: pct(frac) for area, frac in rings.items()},
            "count": len(states),
            # The sign-off picker's rows, in catalog order and carrying the state the
            # grid drew — through the SAME ``_cell_state``, so the picker cannot call a
            # process something the cell above it does not. ``ref`` is built HERE by
            # state.process_subject_ref — the one home for that convention — so a
            # decision always names the process the cell showed, and the template never
            # assembles a subject by hand.
            "processes": [
                {
                    "id": process.id,
                    "name": process.name,
                    "state": _cell_state(process, process_state),
                    "ref": state.process_subject_ref(process, project),
                }
                for process, process_state in states
            ],
        }
        return TEMPLATES.TemplateResponse(request, "process_map.html", context)

    @router.get("/projects/{project_id}/wizard", response_class=HTMLResponse)
    def wizard_page(
        request: Request, project_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        at = _as_of(as_of)
        return TEMPLATES.TemplateResponse(request, "wizard.html", _wizard_context(db, project, at))

    @router.post("/projects/{project_id}/wizard/apply")
    def wizard_apply(
        request: Request,
        project_id: int,
        db: Db,
        kind: Annotated[str, Form()],
        posted: Annotated[dict[str, str], Depends(_posted_fields)],
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
        _require_pair_unless_bearer(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = _as_of(as_of)

        def refuse(status: int, message: str) -> Response:
            context = _wizard_context(db, project, at, body=body, posted=posted, error=message)
            return TEMPLATES.TemplateResponse(request, "wizard.html", context, status_code=status)

        if kind in _BASELINE_KINDS and adapters.plan_baseline(project) is not None:
            # See _BASELINE_KINDS: 409, nothing written.
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
                return refuse(422, f"{kind} is a record of prose and needs a body")
            if len(typed) > _BODY_MAX:
                return refuse(422, f"{kind} holds at most {_BODY_MAX} characters")
            fields["body"] = typed
        try:
            wizard_cli.produce(db, project, kind, fields, at)
        except (KeyError, ValueError) as error:
            # Every refusal ``produce`` raises is a ValueError — pydantic's
            # ValidationError, ``MissingBody``, and any producer-side guard a later
            # commit adds — so it renders the form here, never escapes as a 500.
            return refuse(422, str(error))
        return RedirectResponse(
            f"/projects/{project_id}/wizard?as_of={at.isoformat()}", status_code=303
        )

    @router.get("/projects/{project_id}/status", response_class=HTMLResponse)
    def status_form(
        request: Request, project_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        at = _as_of(as_of)
        # The append-only StatusSnapshot series IS the trend — ordered by date so the
        # chart's coordinates are stable across renders.
        snapshots = db.scalars(
            select(StatusSnapshot)
            .where(StatusSnapshot.project_id == project.id)
            .order_by(StatusSnapshot.taken_on)
        ).all()
        series = trend_series(snapshots)
        # Planned-vs-actual cost S-curve. Costs load once; the baseline hierarchy
        # is eager-loaded so the in-memory sweep in ``evm_curve`` never fires a
        # query per sample date (``snapshot_from`` is pure once baselines are in).
        project = db.scalars(
            select(Project).where(Project.id == project.id).options(*adapters.eager_project())
        ).one()
        costs = adapters.project_costs(db, project)
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "percent": stamped_percent(db, project, at),
            "rags": list(RAG_STATUSES),
            "series": series,
            "evm": evm_curve(project, costs, at),
        }
        return TEMPLATES.TemplateResponse(request, "status_form.html", context)

    @router.post("/projects/{project_id}/status")
    def status_submit(
        request: Request,
        project_id: int,
        db: Db,
        rag_status: Annotated[str, Form()] = "green",
        note: Annotated[str | None, Form()] = None,
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """File the weekly snapshot through the SAME validated boundary the JSON
        route uses: ``StatusSnapshotIn`` refuses a bad RAG or oversize note as 422
        at the schema — never handed to the ORM to bounce off a CHECK as a 409 or
        slip past a VARCHAR SQLite does not enforce — and ``create_status_snapshot``
        stamps the percent from calc, never typed. The two write paths are one."""
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = _as_of(as_of)
        try:
            payload = s.StatusSnapshotIn(
                project_id=project.id,
                taken_on=at,
                rag_status=rag_status,  # type: ignore[arg-type]
                note=note or None,
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        create_status_snapshot(payload, db)
        return RedirectResponse(
            f"/projects/{project_id}/status?as_of={at.isoformat()}", status_code=303
        )

    @router.get("/pmbok", response_class=HTMLResponse)
    def pmbok_reference(request: Request) -> HTMLResponse:
        """The 49 PMBOK processes as a stateless ITTO reference grid.

        Rendered straight from the frozen ``catalog.PROCESSES`` — no DB, no project
        state — so the knowledge map is reachable as theory, not only through a
        project (audit findings #8 / #9). Same area×group shape as the per-project
        map, but every cell links to its process's ITTO detail.
        """
        context = {
            "groups": [g.value for g in ProcessGroup],
            "areas": [a.value for a in KnowledgeArea],
            "grid": _reference_grid(),
        }
        return TEMPLATES.TemplateResponse(request, "pmbok.html", context)

    @router.get("/pmbok/{process_id}", response_class=HTMLResponse)
    def pmbok_detail(
        request: Request,
        process_id: str,
        db: Db,
        project: int | None = None,
        as_of: date | None = None,
    ) -> HTMLResponse:
        """One process's ITTO — inputs, tools & techniques, outputs — by clause id.

        The drill target of a project process-map cell (finding #12), and with
        ``?project=`` the REST of that drill rather than its dead end: the cell
        carries the project and the pinned as-of through the hop, so the page adds
        this project's live artifacts, its computed state for the process, and its
        knowledge area's assessment with the threats and actions attached — then
        links back to the map the reader came from instead of to the theory grid.
        Without ``?project=`` it is the stateless reference it has always been, so
        the two reading modes stay distinct. Unknown ids (and unknown projects)
        404 rather than 500 (``catalog.get`` raises ``KeyError``).
        """
        try:
            process = catalog.get(process_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        context: dict[str, Any] = {"process": process, "live": None}
        if project is not None:
            context["live"] = process_in_project(
                process, fetch(db, Project, project), db, _as_of(as_of)
            )
        return TEMPLATES.TemplateResponse(request, "pmbok_detail.html", context)

    return router


def threat_cards(db: Session, as_of: date, project_id: int | None = None) -> list[dict[str, Any]]:
    """Ranked live-threat cards, each naming its project and carrying its actions.

    ``top_threats`` supplies the cross-store suppression and ranking. A per-project
    ``assess_project`` pass supplies, for each threat, the project it belongs to and
    the recommended actions its assessment attached — actions live on the
    ``Assessment``, not the ``Threat`` — keyed by the globally unique threat id.
    Both reads are pure functions of the store and ``as_of``, and the card list
    follows the engine's ranking, so the board regenerates byte-identically.

    ``project_id`` scopes every read to one project — the project hub's own use —
    so a single hub page never pays the whole-store cost: only that project's
    assessment runs, and ranking comes from ``live_threats`` (the same per-project
    engine call ``top_threats`` fans out to) instead of the store-wide feed. Both
    paths share the same ``eager_project`` options as ``engine.top_threats``, so the
    walk down to ``line.task`` never fires a lazy query per baseline line here
    either. Filtering the unscoped board by project id and calling this scoped
    would produce the same cards in the same order — both sort by the engine's one
    ranking key — so the scoped path is a cost cut, not a behavior change.

    Each card also carries a ``delta`` describing its week-over-week trend: the
    same ranked feed one week earlier (``as_of - 7d``) is loaded and threats are
    matched by their stable, severity-independent id, so ``dir`` is ``up`` when the
    score worsened, ``down`` when it improved, ``flat`` when unchanged, or ``new``
    for a threat with no counterpart a week ago. The window is measured from
    ``as_of``, never the wall clock, so the trend regenerates deterministically.
    The second load (of the prior week) is the accepted cost of that comparison —
    eager-loaded like the current week, so it is not an N+1 either.
    """
    query = select(Project).order_by(Project.name, Project.id).options(*adapters.eager_project())
    if project_id is not None:
        query = query.where(Project.id == project_id)
    projects = list(db.scalars(query))

    by_id: dict[str, dict[str, Any]] = {}
    # The one pass that is this function's own (the two ``top_threats`` calls
    # below batch inside the engine): scoped so its per-project reads are
    # batched across the whole board too, not re-queried project by project.
    with adapters.prefetched(db, projects):
        for project in projects:
            for assessment in assess.assess_project(db, project, as_of):
                actions = [{"label": a.label, "rationale": a.rationale} for a in assessment.actions]
                for threat in assessment.threats:
                    by_id[threat.id] = {
                        "project_id": project.id,
                        "project_name": project.name,
                        "actions": actions,
                    }

    if project_id is not None:
        scoped_project = projects[0] if projects else None
        current = assess.live_threats(db, scoped_project, as_of) if scoped_project else ()
        prior_threats = (
            assess.live_threats(db, scoped_project, as_of - timedelta(days=7))
            if scoped_project
            else ()
        )
    else:
        current = assess.top_threats(db, as_of)
        prior_threats = assess.top_threats(db, as_of - timedelta(days=7))
    prior = {t.id: t.score for t in prior_threats}

    cards: list[dict[str, Any]] = []
    for t in current:
        meta = by_id[t.id]
        cards.append(
            {
                "id": t.id,
                "kind": t.kind,
                "severity": t.severity,
                "score": t.score,
                "description": t.description,
                "project_id": meta["project_id"],
                "project_name": meta["project_name"],
                "actions": meta["actions"],
                "delta": _trend_delta(t.score, prior.get(t.id)),
            }
        )
    return cards


def _artifact_cell(status: mapping.ArtifactStatus) -> dict[str, str]:
    """One ITTO artifact as the drill page reads it: a word for what the store knows,
    the ``.st-*`` wash the map already uses for that reading, and the resolver's own
    detail. ``not tracked`` — a kind with no resolver at all — is deliberately
    distinct from ``absent``: the first is a fact about this product, the second a
    claim about the project. The word is inside the badge, so no wash stands alone.
    """
    if status.present:
        label, rank = ("healthy", "ok") if status.healthy else ("at risk", "warn")
    elif mapping.is_tracked(status.kind):
        label, rank = "absent", "muted"
    else:
        label, rank = "not tracked", "muted"
    return {"label": label, "rank": rank, "detail": status.detail}


def process_in_project(
    process: Process, project: Project, db: Session, as_of: date
) -> dict[str, Any]:
    """The hops a theory page cannot make: one process, read against one project.

    Carries this project's live artifact status for every kind the process's ITTO
    names, its computed process state, and its knowledge area's assessment with the
    threats and actions that assessment attached. The join to the assessment is by
    name and needs no second table: ``Assessment.kind`` IS the ``KnowledgeArea``
    value for the nine evaluators, and ``integration`` for the worst-of roll-up, so
    every one of the ten areas has exactly one — pinned by a test, and answered with
    ``None`` rather than a 500 if that ever stops holding. Threats run through
    ``assess.is_suppressed``, so one signed off on the board stays hidden here too.

    Nothing is recomputed: ``mapping.resolve``, ``state.process_state`` and
    ``assess.assess_project`` are the same pure, as-of-parameterised engines the map,
    the wizard and the threat board already read, so a pinned as-of regenerates
    byte-identically and no figure here can drift from the one beside it.
    """
    with state.prefetched(db, [project]):
        artifacts = {
            kind: _artifact_cell(mapping.resolve(kind, project, db, as_of))
            for kind in dict.fromkeys((*process.inputs, *process.outputs))
        }
        cell_state = state.process_state(process, project, db, as_of).value
        area = {a.kind: a for a in assess.assess_project(db, project, as_of)}.get(
            process.area.value
        )
    return {
        "project": project,
        "as_of": as_of.isoformat(),
        "artifacts": artifacts,
        "state": cell_state,
        "rank": STATE_RANK[cell_state],
        # The distinguishing predicate the map cell cannot say in five words: a
        # process with no tracked output reads not_started about the STORE.
        "assessable": state.is_assessable(process),
        "assessment": area
        and {
            "status": area.status,
            "score": area.risk_score,
            "threats": [
                {"severity": t.severity, "description": t.description}
                for t in area.threats
                if not assess.is_suppressed(db, t, as_of)
            ],
            "actions": [{"label": a.label, "rationale": a.rationale} for a in area.actions],
        },
    }


def pct(value: float | None) -> str:
    """A 0..1 fraction as a whole-percent label, or ``n/a`` — never a fake 0%."""
    return f"{value * 100:.0f}%" if value is not None else "n/a"


def trend_series(snapshots: Sequence[StatusSnapshot]) -> list[dict[str, Any]]:
    """The weekly-status trend's plotted points — each carrying ``at``, its position
    along the ELAPSED span as a 0..1 fraction, not its row number.

    Snapshots are not weekly. The only rule on the series is one row per project per
    DATE (``uq_status_snapshot_project_date``) and the form writes at whatever ``as_of``
    it is posted, so plotting by row index drew three readings a day apart and a fourth
    three months later as four evenly spaced points — a slope reporting a rate of
    progress the dates never supported. The fraction is computed here rather than left
    to the template, which has only the loop index and ISO strings: with the arithmetic
    on this side the template cannot re-derive an ordinal axis by accident.

    Unlike the S-curves, this series is stored rows at operator-chosen dates, which is
    why ``gather.sample_dates`` — evenly spaced by construction, and the reason the
    dashboard, burn and EVM curves index-plot honestly — cannot serve it. A lone
    snapshot spans zero days and sits at 0.0; the axis has no length to divide by.
    """
    if not snapshots:
        return []
    first = snapshots[0].taken_on
    span = (snapshots[-1].taken_on - first).days
    return [
        {
            "taken_on": row.taken_on.isoformat(),
            "percent": row.percent_complete,
            "rag": row.rag_status,
            "at": ((row.taken_on - first).days / span) if span else 0.0,
        }
        for row in snapshots
    ]


_EVM_SAMPLES = 12


def evm_curve(project: Project, costs: Sequence[CostEntry], as_of: date) -> dict[str, Any]:
    """Planned-vs-actual cost S-curve data for one project — pure and drift-free.

    Sweeps the two genuinely time-phased lines — PV(t) (planned value) and AC(t)
    (actual cost) — over a fixed ``_EVM_SAMPLES`` :func:`gather.sample_dates`
    from the ``adapters.plan_baseline`` window's earliest ``planned_start`` to
    ``as_of``, plus the flat BAC and the CURRENT EV/CPI/SPI/EAC as text figures.
    One selector, so the curve's x-axis is the plan its BAC came from. EV is deliberately
    a single as-of *position*, never a swept line: the model retains only each
    task's current ``percent_complete`` (no progress history), so an EV curve
    swept over past dates would be a flat, misleading fiction. ``snapshot_from``
    is pure once the baselines are loaded, so no query fires per sample date;
    with no APPROVED baseline the ``points`` list is empty and the template shows
    an empty state.
    """
    baseline = adapters.plan_baseline(project)
    lines = baseline.lines if baseline else []
    if not lines:
        return {"points": [], "bac": 0.0, "current": None}
    starts = [line.planned_start for line in lines]
    points: list[dict[str, float]] = []
    for sample in gather.sample_dates(starts, as_of, _EVM_SAMPLES):
        snap = adapters.snapshot_from(project, costs, sample)
        points.append({"pv": round(snap.pv, 2), "ac": round(snap.ac, 2)})
    current = adapters.snapshot_from(project, costs, as_of)
    return {
        "points": points,
        "bac": round(current.bac, 2),
        "current": {
            "ev": round(current.ev, 2),
            "cpi": round(current.cpi, 3) if current.cpi is not None else None,
            "spi": round(current.spi, 3) if current.spi is not None else None,
            "eac": round(current.eac, 2) if current.eac is not None else None,
        },
    }


def _reference_grid() -> dict[str, dict[str, list[dict[str, str]]]]:
    """A stateless knowledge-area × process-group grid of the frozen catalog.

    The same area×group shape as :func:`_process_grid`, but each cell carries only
    the process id and name — no state or rank — straight from ``catalog.PROCESSES``.
    """
    grid: dict[str, dict[str, list[dict[str, str]]]] = {
        area.value: {group.value: [] for group in ProcessGroup} for area in KnowledgeArea
    }
    for process in catalog.PROCESSES:
        grid[process.area.value][process.group.value].append(
            {"id": process.id, "name": process.name}
        )
    return grid


def _process_grid(
    states: Sequence[tuple[Process, state.ProcessState]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """A knowledge-area × process-group grid of process cells, each with its state.

    Takes the project's ``project_process_states`` result directly — the caller
    computes it once (inside a ``pmbok.state.prefetched`` scope) and threads it
    here rather than this re-walking the store itself.
    """
    by_id = {p.id: s for p, s in states}
    grid: dict[str, dict[str, list[dict[str, Any]]]] = {
        area.value: {group.value: [] for group in ProcessGroup} for area in KnowledgeArea
    }
    for process in catalog.PROCESSES:
        cell_state = _cell_state(process, by_id[process.id])
        grid[process.area.value][process.group.value].append(
            {
                "id": process.id,
                "name": process.name,
                "state": cell_state,
                "rank": CELL_RANK[cell_state],
                "mark": CELL_MARK[cell_state],
            }
        )
    return grid


def area_completeness(
    states: Sequence[tuple[Process, state.ProcessState]],
) -> dict[str, float | None]:
    """Per-knowledge-area completion, the SAME rule as ``state.completeness`` grouped by area.

    For each area: the share of its assessable, non-waived processes that are
    PRODUCED or SIGNED_OFF — waived and untrackable processes are excluded exactly
    as :func:`state.completeness` excludes them, so the ring's percentage can never
    drift from the states the grid renders. Takes the SAME ``project_process_states``
    result the grid renders from — the caller computes it once (inside a
    ``pmbok.state.prefetched`` scope) and threads it here, so a page with both a
    grid and rings never walks the store for the same states twice. ``None`` for
    an area with nothing to assess (rendered as an ``n/a`` ring, never a fake 0%).
    Pure and deterministic.
    """
    counted: dict[str, int] = {area.value: 0 for area in KnowledgeArea}
    done: dict[str, int] = {area.value: 0 for area in KnowledgeArea}
    for process, process_state in states:
        if state.excluded_from_completeness(process, process_state):
            continue
        counted[process.area.value] += 1
        if process_state in (state.ProcessState.PRODUCED, state.ProcessState.SIGNED_OFF):
            done[process.area.value] += 1
    return {area: (done[area] / counted[area] if counted[area] else None) for area in counted}
