"""Report documents. Each module here exposes ``SLUG``, ``TITLE`` and
``render(session, project, as_of) -> str``, and is found by
``driftless.report.engine.iter_documents`` — a document PR adds a module, never a
registry entry."""
