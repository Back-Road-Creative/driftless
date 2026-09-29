"""The sign-off write: ``POST /sign-off``, posted from the threat board and the home rail.

Last of the ITTO page module's write routes to be carved out. Both surfaces that post to
it were controllers of their own by then, so the redirect allowlist below was the last
thing that had still tied this route to ``web/pages.py``.

The row itself is written by ``driftless.services.sign_offs``, which the JSON route calls
too, so the two write paths stay one without either importing the other.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from driftless.api import schemas as s
from driftless.api.deps import Db, is_agent_actor, signer
from driftless.services.sign_offs import create_sign_off
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute


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
    if subject_kind == "baseline" and project_id is not None:
        return f"/projects/{project_id}/baselines/diff"
    if subject_kind == "gate" and project_id is not None:
        return f"/projects/{project_id}/gates"
    return requested if requested in _SIGN_OFF_REDIRECT_TARGETS else "/threats"


def create_sign_off_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The sign-off write route, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

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
        the JSON route applies — see :func:`driftless.api.deps.signer`, which is the
        one place that decides, including when the field survives.

        The board used to post a hidden ``signal`` input alongside the decision — a
        worse claim than ``signed_by``, since it named the threshold a threat must
        regress past to come back, and a forged value muted it for good. That input
        is gone from both ``threats.html`` and ``home.html``: there is no ``signal``
        parameter above, none on ``SignOffIn``, and ``SignOffIn`` now refuses any
        field it does not declare, so a request that still carries one is a 422
        rather than a claim silently discarded. :func:`driftless.services.sign_offs.stamped_signal`
        is the whole mechanism instead of a backstop behind an ignored field — it
        computes what is stored from the live score, and nothing the caller sends
        can move it. The row itself is appended by the service the JSON route calls,
        so the two write paths are one.
        """
        csrf.require(request, csrf_token)  # before any read or write
        at = resolve_as_of(as_of)
        # Wrapped exactly as ``status_submit`` below wraps ``StatusSnapshotIn``: a
        # bad ``decision`` or ``subject_kind`` is a ``ValidationError``, not an
        # ``HTTPException``, and without this it fell through to the catch-all 500.
        # ``HTTPException(422)`` over the wizard's field-keyed ``refuse()``: unlike
        # the wizard step, sign-off has no dedicated form page to re-render — it is
        # posted from the threat board and the home rail — so there is nothing to
        # hand the error back into, which is the same shape ``status_submit`` is in.
        try:
            payload = s.SignOffIn(
                project_id=project_id,
                subject_kind=subject_kind,  # type: ignore[arg-type]
                subject_ref=subject_ref,
                decision=decision,  # type: ignore[arg-type]
                signed_by=signed_by or "web",
                as_of=at,
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        create_sign_off(
            db, payload, signer(request, payload.signed_by), is_agent=is_agent_actor(request)
        )
        target = _sign_off_redirect(payload.subject_kind, payload.project_id, next)
        return RedirectResponse(f"{target}?as_of={at.isoformat()}", status_code=303)

    return router
