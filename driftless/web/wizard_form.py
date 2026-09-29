"""How the wizard's form is built, asked and refused.

Carved out of ``web/pages.py``, which owned none of it: the field table, the stored body
ceiling, which kinds re-baseline, and the context a GET and a refused POST both render
through are the wizard's model of its own form. The routes that use them follow in the
next change — the two together exceed the diff cap, and moving what is shared first is
the order ``web/credentials.py`` used.

Two properties are load-bearing and deliberately derived rather than written down here:
the field table is read off the producer's own required-fields table, so a kind cannot be
offered with no way to answer it, and the body ceiling is read off the schema that
enforces it, so the textarea's ``maxlength`` and the API's refusal are one number.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.models import COST_CATEGORIES, Project, RAG_STATUSES
from driftless.naming import technique_slug
from driftless.pmbok import catalog, state
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.methods import METHODS, Practice
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS, ProcessDefinition
from driftless.pmbok.reasons import UNTRACKED_REASONS
from driftless.web.techniques import support_tier
from driftless.web.templating import artifact_name, artifact_slug, technique_name
from driftless.wizard import cli as wizard_cli
from driftless.wizard import engine as wizard


# The stored ceiling on a narrative body, read off the schema that enforces it instead
# of retyped here: it becomes the textarea's own ``maxlength``, so the limit the API has
# always applied is one a browser meets at the form rather than as a 500 after the post.
BODY_MAX: int = next(
    rule.max_length for rule in s.NarrativeArtifactIn.model_fields["body"].metadata
)

# The producible kinds that CREATE a plan baseline (one producer serves both).
# Producing one against a project already holding an APPROVED plan is a re-baseline:
# version N+1 irreversibly becomes the plan every EVM figure is measured against.
# That is a change-control decision, so the one-click form refuses it (409).
BASELINE_KINDS = frozenset({"scope_baseline", "schedule_baseline"})


# How each collected field is typed and constrained in the browser, so a value the
# schema would refuse is one the form makes hard to enter: the vocabularies come from
# the ORM tuples the CHECK constraints are built from, never a hand-listed copy.
FIELD_CHOICES: dict[str, tuple[str, ...]] = {
    "category": COST_CATEGORIES,
    "rag_status": RAG_STATUSES,
}
FIELD_TYPE = {"target_date": "date"} | dict.fromkeys(
    ("probability", "impact", "planned_amount", "planned_cost", "target_value", "actual_value"),
    "number",
)


def input_rows(step: wizard.WizardStep) -> list[dict[str, Any]]:
    """The "What you need" rows: one per input, in words — its own artifact page,
    whether THIS project already has it, and, when it does not, the process(es) the
    catalog itself says produce it (``ArtifactDefinition.produced_by``), so a missing
    input is never a dead end with nowhere to go make it."""
    return [
        {
            "kind": i.kind,
            "name": artifact_name(i.kind),
            "href": f"/artifacts/{artifact_slug(i.kind)}",
            "present": i.present,
            "producers": [(pid, catalog.get(pid).name) for pid in ARTIFACTS[i.kind].produced_by],
        }
        for i in step.inputs
    ]


def technique_rows(step: wizard.WizardStep) -> list[dict[str, Any]]:
    """The "How you do it" rows: one per technique this step names, in words — its
    support tier sentence (``web.techniques.support_tier``) and the one page that
    either runs it or explains it, never the raw ``TT_CATALOG`` key."""
    return [
        {
            "key": key,
            "name": technique_name(key),
            "tier": support_tier(key),
            "href": f"/techniques/{technique_slug(key)}",
        }
        for key in step.tools_techniques
    ]


def output_rows(step: wizard.WizardStep) -> list[dict[str, Any]]:
    """The "What you get" rows: one per output, in words — the form on this page
    when the wizard can produce it, else why it is read rather than produced
    (``UNTRACKED_REASONS``, guaranteed for every kind outside the producible set by
    ``tests/test_launcher_totality.py``)."""
    return [
        {
            "kind": kind,
            "name": artifact_name(kind),
            "href": f"/artifacts/{artifact_slug(kind)}",
            "producible": kind in step.producible,
            "explanation": (
                "Produced by the form on this page."
                if kind in step.producible
                else UNTRACKED_REASONS[kind].why
            ),
        }
        for kind in step.outputs
    ]


def method_links(project_id: int, at: date, process_id: str | None) -> dict[str, str]:
    """This step's own page, once per crosswalk ``method`` the wizard offers --
    the real address ``?method=scrum`` or ``?method=kanban`` picks, built here so
    the template can link to it rather than telling a reader to type the query
    string themselves."""
    base = f"/projects/{project_id}/wizard?as_of={at.isoformat()}"
    if process_id is not None:
        base += f"&process={process_id}"
    return {key: f"{base}&method={key}" for key in ("scrum", "kanban")}


def method_practices(process_id: str, method_key: str | None) -> tuple[Practice, ...]:
    """The practices of ``method_key`` (``"scrum"`` or ``"kanban"``) that crosswalk to
    this process — empty for an unknown or absent key. ``Project`` carries no method
    of its own yet, so ``method_key`` comes from the page's own ``?method=`` query
    param rather than a stored fact; the caller is what says so out loud."""
    profile = METHODS.get(method_key or "")
    if profile is None:
        return ()
    return tuple(practice for practice in profile.practices if process_id in practice.crosswalk)


def wizard_context(
    db: Session,
    project: Project,
    at: date,
    *,
    process_id: str | None = None,
    body: str = "",
    posted: dict[str, str] | None = None,
    error: str | None = None,
    field_errors: dict[str, str] | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    """The wizard page's context — built ONE way, for a GET and for a refused POST.
    A refusal re-renders the FORM, threading the posted ``body`` and fields back into
    their inputs (the POST replaced the page, so no history entry holds the words) with
    ``error`` above it. ``field_errors`` is the SAME refusal's field-keyed half — see
    ``_alert.html``'s macro — and defaults to ``{}`` rather than ``None`` so the
    template's ``StrictUndefined`` environment never has to guard a GET with no refusal
    at all. ``process_id`` names a process to show INSTEAD of ``next_step``'s own
    pointer — a ``derived``/``reference`` step's "produced by" link, for a prerequisite
    lifecycle order has not reached yet. Both rides the route-scoped prefetch cache.

    ``method`` is the workspace's "In your method" section: which practices of a
    Scrum or Kanban profile crosswalk to the current step. ``Project`` carries no
    method of its own yet, so this reads the page's own ``?method=scrum|kanban``
    query param rather than a stored fact — the caller passes through whatever the
    request carried, and the template says out loud that it came from there."""
    with state.prefetched(db, [project]):
        step = (
            wizard.step_for(db, project, process_id, at)
            if process_id is not None
            else wizard.next_step(db, project, at)
        )
    # Which of THIS step's outputs are prose, read off the producer table rather
    # than listed here — so the form asks for a body exactly where one is stored.
    asks = sorted(set(step.producible) & wizard_cli.body_kinds()) if step else []
    offered = step.producible if step else ()
    definition: ProcessDefinition | None = PROCESS_DEFINITIONS[step.process_id] if step else None
    return {
        # One input per field the offered kinds are made of, read off the same table the
        # producers refuse against — so a kind cannot be offered with no way to answer it.
        # `required` follows the body's rule: only where EVERY offered kind needs it.
        "field_asks": [
            {
                "name": name,
                "type": FIELD_TYPE.get(name, "text"),
                "choices": FIELD_CHOICES.get(name, ()),
                "value": (posted or {}).get(name, ""),
                "required": all(name in wizard_cli.required_fields(k) for k in offered),
            }
            for name in sorted({f for k in offered for f in wizard_cli.required_fields(k)})
        ],
        "project": project,
        "as_of": at.isoformat(),
        "step": step,
        "done": step is None,
        "process_definition": definition,
        "input_rows": input_rows(step) if step else [],
        "technique_rows": technique_rows(step) if step else [],
        "output_rows": output_rows(step) if step else [],
        "method": method,
        "method_links": method_links(project.id, at, process_id),
        "method_practices": method_practices(step.process_id, method) if step else (),
        "map_href": (
            f"/map?focus=process:{step.process_id}&project={project.id}" if step else None
        ),
        "body_kinds": asks,
        # The browser enforces `required` only where EVERY output on the step is
        # prose: 11.2 and 11.3 offer a risk register beside the assumption log, and
        # marking it there would block the kind that needs no body at all.
        "body_required": step is not None and asks == sorted(step.producible),
        "body_max": BODY_MAX,
        "body": body,
        "error": error,
        "field_errors": field_errors or {},
    }


async def posted_fields(request: Request) -> dict[str, str]:
    """The wizard POST's whole form, so the route can forward the inputs the CHOSEN kind
    needs without growing a parameter per field of every producible kind. Async because
    Starlette parses a body that way and caches it; the route stays sync."""
    return {name: value for name, value in (await request.form()).items() if isinstance(value, str)}
