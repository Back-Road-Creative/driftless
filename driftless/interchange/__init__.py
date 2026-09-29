"""Schedule interchange: importers that bring a dead tool's data into driftless's
own ``Task``/``TaskDependency``/``ProjectCalendar`` shape.

Every format-specific parser (``msproject``, ``xer``) produces the same small,
format-neutral :class:`~driftless.interchange.common.ImportedSchedule`, and
``common.write_imported_schedule`` is the one write path both use — it goes
through the same Pydantic schemas and ``driftless.api.records.insert`` the API
itself writes through, so an import lands in the ChangeLog exactly like an API
write does. Neither parser touches the database; only ``common`` does.
"""
