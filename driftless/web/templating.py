"""The ONE Jinja environment every page renders through, so no render forgets its
CSRF pair.

Seven routers each held their own ``Jinja2Templates`` over the same directory and had
to remember the token; three did, four did not — and ``base.html`` renders the
sign-out form on *every* page. A context processor makes the field half unforgettable
instead: it runs on every render and Starlette merges it AFTER the caller's context,
so no router can omit the token or pass a stale one. The cookie half cannot come from
a processor, which never sees a response, so it is attached in :meth:`TemplateResponse`
— the one point every page passes on the way out, holding both the rendered context and
the response that carries its cookie. Middleware would have to guess which responses
are pages, and would stamp the JSON API too.

Being ONE environment is also what makes every page strict at once. Starlette builds
its own lenient ``Environment`` from a ``directory=``, so the environment is built here
and handed over instead: under Jinja's default a name no route passed — a misspelt
``{{ as_off }}``, a field only an empty-state branch mentions — renders as the **empty
string**, and a page whose date quietly vanished still answers 200 with every test
green. ``undefined=StrictUndefined`` turns that into an ``UndefinedError`` at render
time, for every template in the directory at once — the count is nobody's to keep, since
this is one environment and a template joins it by being written — and for pages not
written yet. A name that is legitimately absent is passed explicitly (``None``) or
guarded with ``is defined``; there is no exemption list and no second, laxer
environment to move a page onto.
"""

import re
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape
from starlette.templating import _TemplateResponse

from driftless.models import SIGNOFF_DECISIONS
from driftless.naming import humanize, technique_slug
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.reasons import UNCITED_EXEMPTIONS
from driftless.pmbok.tt import EXTENSION_REASONS
from driftless.web import csrf


class _Templates(Jinja2Templates):  # Starlette's, plus the cookie half of what it rendered
    def TemplateResponse(self, *args: Any, **kwargs: Any) -> _TemplateResponse:
        page: _TemplateResponse = super().TemplateResponse(*args, **kwargs)
        csrf.attach(page, page.context[csrf.FIELD])  # the very token just rendered
        return page


_PAIR = [lambda request: {csrf.FIELD: csrf.ensure(request)}]  # the field half, every render
_ENV = Environment(  # what Starlette's ``directory=`` builds, plus the one thing it cannot
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(),  # HTML output: escaping is what keeps a name from being markup
    auto_reload=False,  # packaged templates move only with a deploy; no os.stat per warm render
    undefined=StrictUndefined,  # a name no route passed raises; it never renders blank
)


def technique_name(key: str) -> str:
    """A technique key as the ONE name a page may show for it: whatever the registry
    holds in ``TechniqueDefinition.display_name``.

    ``humanize`` is not that name. ``definitions._DISPLAY_NAME_OVERRIDES`` exists
    precisely because ``.title()`` mishandles PMBOK terms of art — it drops the hyphen
    in "To-Complete Performance Index" and capitalizes the "for" in "Design for X" — and
    the ITTO list used to pipe the raw key through ``humanize``, deriving the name a
    second time and disagreeing with the technique page it linked to for exactly the
    keys the override table exists to correct. There is one name now, read from the
    registry by both surfaces.

    An unknown key raises rather than falling back to ``humanize``: a silent fallback is
    the second derivation coming back, and a technique the registry does not hold has no
    page to link to either.
    """
    return TECHNIQUES[key].display_name


def artifact_slug(key: str) -> str:
    """An artifact kind key as it appears in a URL: ``project_charter`` ->
    ``project-charter`` — the same ``humanize``-then-lower-then-dash formula
    :func:`driftless.naming.technique_slug` uses for the technique library, applied
    to the artifact vocabulary instead. It lives here rather than in
    ``driftless.naming`` because, unlike the technique slug, nothing outside
    ``driftless.web`` needs to address an artifact kind by it — the ITTO template
    and ``web/artifacts.py``'s own index are both already inside this package.
    """
    return humanize(key).lower().replace(" ", "-")


def artifact_name(key: str) -> str:
    """An artifact kind key as the ONE name a page may show for it: whatever the
    registry holds in ``ArtifactDefinition.display_name`` — :func:`technique_name`'s
    counterpart for the artifact vocabulary, so an ITTO input or output reads the
    same override-corrected word its own ``/artifacts/{slug}`` page titles itself
    with, never the raw key ``humanize`` would produce on its own.
    """
    return ARTIFACTS[key].display_name


def or_no_data(value: Any) -> Any:
    """``value``, or the reader-facing ``"no data yet"`` in place of a bare
    ``None`` -- the one substitute every page uses for a figure nothing has
    computed, so a reader never has to already know ``n/a`` is database jargon
    for "nothing here yet"."""
    return value if value is not None else "no data yet"


def money(value: Any) -> Any:
    """A dollar figure as the ONE way every page prints it: thousands-separated,
    no cents (``"{:,.0f}"``) -- so a reader sees ``15,000`` on every page rather
    than one page's bare ``round(x, 2)`` float (``15000.0``) beside another's
    comma-grouped rollup for the same figure. ``None`` passes through
    :func:`or_no_data`'s convention rather than a numeric filter treating "no
    data" as zero."""
    return or_no_data(value) if value is None else "{:,.0f}".format(value)


def plural_s(count: float) -> str:
    """The English plural suffix for ``count``: ``""`` for exactly one, else
    ``"s"`` -- so a page writes ``1 item`` and ``3 items`` rather than the
    ``item(s)`` shorthand that reads neither as singular nor as plural."""
    return "" if count == 1 else "s"


def extension_reason(key: str) -> str:
    """Why Driftless added this technique to its own vocabulary, as ``tt.py`` recorded
    it, or ``""`` for a technique the PMBOK-6 edition itself names.

    ``tt.EXTENSION_REASONS`` is a required field on every extension, and until this
    filter existed no page rendered any of it — the technique page said only that
    Driftless had added the technique, with the written justification readable in the
    source alone.
    """
    return EXTENSION_REASONS.get(key, "")


#: A clause number as ``further_reading`` writes one. Two recorded citation-gap
#: reasons quote the clause that was found, ruled out and blanked, which is the whole
#: point of the sentence to a maintainer — and unreadable as anything but a citation to
#: a reader, on the one page that must not show a clause number at all.
_QUOTED_CLAUSE = re.compile(r"PMBOK-6 §\d")


def uncited_reason(key: str) -> str:
    """Why PMBOK-6 gives this technique no clause number, as
    ``reasons.UNCITED_EXEMPTIONS`` recorded it, or ``""`` where the page must keep its
    general sentence instead.

    Every uncited technique has an entry — ``tests/test_technique_totality.py`` pins the
    set equal to the uncited ones — and until this filter existed none of it was
    rendered: a reader was told only that no clause was recorded, on every one of them
    alike, while the registry held the particular reason for each.

    The one withholding is a reason that quotes the ruled-out clause. A page for a
    technique with no citation must not print a clause number a reader could mistake for
    one, so those keep the general sentence until the recorded wording stops quoting it —
    a property of the sentence, read off the sentence, not a list of keys kept here.
    """
    reason = UNCITED_EXEMPTIONS.get(key)
    if reason is None or _QUOTED_CLAUSE.search(reason.why):
        return ""
    return reason.why


_TAG = re.compile(r"(<[^>]+>)")
# Longest term first, so "work breakdown structure" claims itself before "WBS"
# could ever be considered a match inside it (the two never overlap today, but
# a shorter term's pattern must not get first refusal over a longer one that
# contains it). Word-boundaries: a plain ``\b`` boundary sits at the transition
# between a word character and a non-word one, which is exactly the edge of
# "as-of" or "sign-off" despite the internal hyphen -- neither is a substring of
# a longer ordinary word by construction.
_TERM_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(entry.term) for entry in sorted(GLOSSARY.values(), key=lambda e: -len(e.term))
    )
    + r")\b",
    re.IGNORECASE,
)
_KEY_BY_TERM = {entry.term.lower(): key for key, entry in GLOSSARY.items()}


def _link_first(text: str, seen: set[str]) -> str:
    """``text`` (already escaped, tag-free) with the first unseen occurrence of
    each glossary term wrapped; a term already ``seen`` in this text run is left
    exactly as it reads."""

    def _wrap(match: "re.Match[str]") -> str:
        matched = match.group(0)
        key = _KEY_BY_TERM[matched.lower()]
        if key in seen:
            return matched
        seen.add(key)
        return f'<dfn><a href="/glossary#{key}">{matched}</a></dfn>'

    if not _KEY_BY_TERM:
        return text
    return _TERM_PATTERN.sub(_wrap, text)


def gloss(text: str) -> Markup:
    """A prose run with its first mention of each glossary term linked to
    ``/glossary#{term}`` — the ONE place a page may explain "float" or "EVM" in
    passing rather than making the reader already know the word.

    Escapes plain input rather than trusting it (every technique field this is
    applied to is a plain string, never markup) and, for the input that is
    already ``Markup`` -- HTML this environment itself produced -- walks
    around every tag rather than through it: a term's letters inside an
    ``href``, an ``id`` or an existing ``<a>...</a>`` are never touched, only
    the text nodes between tags are candidates for wrapping.
    """
    source = text if isinstance(text, Markup) else escape(text)
    parts = _TAG.split(str(source))
    seen: set[str] = set()
    out: list[str] = []
    in_anchor = 0
    for part in parts:
        if part.startswith("<"):
            if re.match(r"<a[\s>]", part, re.IGNORECASE):
                in_anchor += 1
            elif part[:3].lower() == "</a":
                in_anchor = max(0, in_anchor - 1)
            out.append(part)
        elif in_anchor:
            out.append(part)
        else:
            out.append(_link_first(part, seen))
    return Markup("".join(out))


TEMPLATES = _Templates(env=_ENV, context_processors=_PAIR)
# ``humanize`` and ``technique_slug`` are registered here but DEFINED in
# ``driftless.naming``, which imports nothing: ``driftless.assess.model`` addresses the
# technique library with the slug and cannot import this module at module scope (web's
# package init imports the evaluators, which import the model). One function object
# behind the filter, the routers and the model — a copy here would be the drift the
# single formula exists to prevent.
TEMPLATES.env.filters["humanize"] = humanize
TEMPLATES.env.filters["technique_slug"] = technique_slug
TEMPLATES.env.filters["technique_name"] = technique_name
TEMPLATES.env.filters["artifact_slug"] = artifact_slug
TEMPLATES.env.filters["artifact_name"] = artifact_name
TEMPLATES.env.filters["extension_reason"] = extension_reason
TEMPLATES.env.filters["uncited_reason"] = uncited_reason
TEMPLATES.env.filters["gloss"] = gloss
TEMPLATES.env.filters["or_no_data"] = or_no_data
TEMPLATES.env.filters["money"] = money
TEMPLATES.env.filters["s"] = plural_s
# The sign-off decision vocabulary, on the environment rather than in three page
# contexts: ``_signoff.html``'s select is built FROM it, so a decision the store accepts
# cannot be hand-listed out of the UI (``waived`` was, for as long as the ledger existed).
TEMPLATES.env.globals["signoff_decisions"] = SIGNOFF_DECISIONS
# The glossary itself, on the environment rather than passed by every page that
# renders a ``see_also`` link: ``glossary.html`` looks another entry's ``term`` up
# by key from here, so a rename in ``GLOSSARY`` cannot leave a cross-reference
# showing the raw key while the term it names showing up correctly.
TEMPLATES.env.globals["glossary"] = GLOSSARY
