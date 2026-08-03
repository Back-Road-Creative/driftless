"""The Jinja2 environment and the document-discovery mechanism.

Autoescape is OFF (Markdown, not HTML) and the block flags pin whitespace.
``iter_documents`` walks ``driftless.report.documents`` in name order, so a
document PR and the CLI never share a registry file.

``undefined=StrictUndefined`` is what makes a document trustworthy. Under Jinja's
default a name no document passed — a misspelt ``{{ completness }}``, a field a
render path forgot — renders as the **empty string**: the figure silently leaves
the document and every test still passes, because a report nobody diffs looks fine
with a blank in it. Strict turns that into an ``UndefinedError`` at render time,
for every template at once and for templates not written yet, instead of one
pinned assertion per document chasing the symptom after the fact. A name that is
legitimately absent is passed explicitly (``None``) or guarded in the template;
there is no exemption list and no second, laxer environment."""

import importlib
import pkgutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy.orm import Session

from driftless.models import Project

_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=False,  # Markdown output, not HTML — escaping would corrupt prose
    auto_reload=False,  # packaged templates move only with a deploy; no os.stat per render
    undefined=StrictUndefined,  # a name nobody passed raises; it never renders blank
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render(template_name: str, context: dict[str, Any]) -> str:
    """Render ``template_name`` from ``templates/`` with ``context``."""
    return _ENV.get_template(template_name).render(context)


def iter_documents() -> Iterator[ModuleType]:
    """Yield each document module (``SLUG``, ``TITLE``, ``render``) in name order."""
    from driftless.report import documents

    for info in sorted(pkgutil.iter_modules(documents.__path__), key=lambda m: m.name):
        yield importlib.import_module(f"{documents.__name__}.{info.name}")


def render_document(slug: str, session: Session, project: Project, as_of: date) -> str:
    """Render the discovered document whose ``SLUG`` matches — the CLI's entry point."""
    for module in iter_documents():
        if getattr(module, "SLUG", None) == slug:
            rendered = module.render(session, project, as_of)
            assert isinstance(rendered, str)  # the module contract; never None
            return rendered
    raise KeyError(f"no report document with slug {slug!r}")
