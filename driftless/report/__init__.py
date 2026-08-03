"""The report engine: stored rows -> deterministic Markdown documents.

Documents render from an explicit ``as_of`` (never the wall clock) for
byte-identical output, are discovered not registered, and draw figures from
``driftless.calc`` via ``gather`` so a document and a screen cannot disagree."""

from driftless.report.engine import iter_documents, render_document

__all__ = ["iter_documents", "render_document"]
