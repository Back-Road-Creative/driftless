"""The wizard form's vocabulary has one home, and the routes will follow it there.

``web/pages.py`` carried the wizard's whole form model — how each collected field is
typed and constrained in the browser, which kinds re-baseline, the stored body ceiling,
and the context builder a GET and a refused POST both render through. None of that is
about the ITTO page module; it is about the wizard.

This lands before the routes themselves because the two together exceed the diff cap.
The same order worked for ``web/credentials.py`` in the previous change: move what is
shared, prove it still holds, then move what uses it.

The properties pinned here are the ones a silent copy would break: the field table is
read off the producer's own required-fields table rather than hand-listed, and the body
ceiling is read off the schema that enforces it rather than retyped.
"""

from __future__ import annotations

from driftless.api import schemas as s
from driftless.web import wizard_form
from driftless.wizard import cli as wizard_cli


def test_the_body_ceiling_is_read_off_the_schema_that_enforces_it() -> None:
    """Not retyped: a limit the browser meets at the form and the API meets at the post
    must be the same number, or the textarea invites a 500."""
    enforced = next(rule.max_length for rule in s.NarrativeArtifactIn.model_fields["body"].metadata)
    assert wizard_form.BODY_MAX == enforced


def test_re_baselining_kinds_are_the_plan_producers() -> None:
    """Producing one against an approved plan is a change-control decision, not a form."""
    assert wizard_form.BASELINE_KINDS == frozenset({"scope_baseline", "schedule_baseline"})


def test_every_offered_kind_can_be_answered() -> None:
    """A field table hand-listed beside the producers drifts from them; read off, it
    cannot. Every field any producible kind requires must be typeable."""
    for kind in wizard_cli.body_kinds() | wizard_form.BASELINE_KINDS:
        for field in wizard_cli.required_fields(kind):
            assert isinstance(wizard_form.FIELD_TYPE.get(field, "text"), str)
            assert isinstance(wizard_form.FIELD_CHOICES.get(field, ()), tuple)
