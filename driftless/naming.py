"""The two word-shaping rules a reader's surfaces spell identifiers with — and the
only module in the tree that may hold them.

``humanize`` turns a snake_case identifier into a reader's words; ``technique_slug``
turns a technique key into the word it is addressed by, and is built FROM
``humanize`` rather than beside it. They live together because the second calls the
first: splitting them would put a formula and half of its own derivation in two
modules that would then have to be argued equal.

**Why a top-level leaf rather than the web layer.** Both rules used to live in
``driftless.web.templating``, which is where the Jinja filters are registered — and
``driftless.assess.model`` cannot import that at module scope. ``driftless.web``'s
package init imports ``departments``, which imports
``driftless.assess.evaluators.resource``, which imports the model: a circular
``ImportError`` on ``import driftless.assess.model``. The model reached the slug
through an import inside a property body instead, which works while leaving the
cycle in place, and would have to be repeated by the next non-web caller.

This module imports nothing at all — not from driftless, not from a framework — so
it cannot participate in any cycle, and every layer can reach it at module scope.
``templating`` still registers both as filters, so templates call them exactly as
before and there is still only one function object behind the filter, the model and
the routers.
"""

from __future__ import annotations

#: Words that stay lower-case mid-label (never as the first word): plain
#: ``.title()`` over every underscore-separated word reads "Monitoring
#: Controlling" and "Interpersonal And Team Skills" — grammatically wrong, not
#: merely a style choice. This list is deliberately small: the conjunctions,
#: prepositions and articles PMBOK's own vocabulary actually uses.
_MINOR_WORDS = frozenset({"and", "or", "of", "the", "to", "for", "in", "on", "a", "an"})

#: Full-key overrides for identifiers the minor-word rule still cannot reach:
#: a hyphenated term of art (``make_or_buy_analysis``) and a name the rule
#: would otherwise render without its conjunction at all — every underscore
#: between "monitoring" and "controlling" reads as a space, not "and".
#: Checked before the general rule; every other key takes the rule unaltered.
_OVERRIDES = {
    "monitoring_controlling": "Monitoring and Controlling",
    "make_or_buy_analysis": "Make-or-Buy Analysis",
}


def humanize(text: str) -> str:
    """A snake_case identifier as a reader's words: ``earned_value_analysis`` ->
    ``Earned Value Analysis`` (audit finding LOW). Named rather than a lambda so
    :func:`technique_slug` can be built FROM it instead of beside it.

    Minor words (``_MINOR_WORDS``) stay lower-case except as the first word of
    the label, and ``_OVERRIDES`` names the identifiers that rule still gets
    wrong. ``pmbok.definitions._display_name`` calls this too, for every
    technique its own override table does not correct. It used to restate the
    body instead, which made the module docstring's "only module that may hold
    them" claim false and — because :func:`technique_slug` really is built from
    this — meant a rewrite here moved every technique URL while every display
    name stayed put, silently.
    """
    if text in _OVERRIDES:
        return _OVERRIDES[text]
    words = text.split("_")
    return " ".join(
        word.capitalize() if index == 0 or word.lower() not in _MINOR_WORDS else word.lower()
        for index, word in enumerate(words)
    )


def technique_slug(key: str) -> str:
    """A technique key as it appears in a URL: ``earned_value_analysis`` ->
    ``earned-value-analysis``.

    Calls :func:`humanize` rather than restating what it does. That matters more
    than it looks: this slug is what ``/techniques/{slug}`` is keyed by, what
    ``Action.reference_href`` sends a reader to, and what ``pmbok_detail.html``
    writes as both its library link and its ``id="tt-…"`` deep-link anchor. Every
    earlier attempt derived it a second time and checked by hand that the two
    agreed; there is one formula now, and the model, the routers and the templates
    all reach it here.
    """
    return humanize(key).lower().replace(" ", "-")
