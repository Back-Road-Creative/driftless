"""Pins that ``PROCESS_DEFINITIONS`` is built *from* ``catalog.PROCESSES``, so a
process can never exist in one without the other by construction, not by
developer diligence — these tests guard the mechanism, mirroring
``tests/test_technique_definitions.py``.

Fails on import before ``driftless.pmbok.process_definitions`` exists.
"""

from __future__ import annotations

from driftless.pmbok import catalog
from driftless.pmbok.model import Process
from driftless.pmbok.process_definitions import (
    PROCESS_DEFINITIONS,
    ProcessDefinition,
    get,
)


def test_catalog_and_definitions_match_in_both_directions() -> None:
    assert set(PROCESS_DEFINITIONS) == {process.id for process in catalog.PROCESSES}


def test_every_definition_wraps_the_same_process_object_the_catalog_holds() -> None:
    """Composition, not a copy: ``process_definitions.py`` must not widen
    ``Process`` itself — ``tests/test_pmbok_catalog.py`` pins that dataclass
    byte-for-byte — so each definition's ``process`` field is the exact catalog
    object, not a reconstruction of it."""
    for process in catalog.PROCESSES:
        definition = PROCESS_DEFINITIONS[process.id]
        assert isinstance(definition, ProcessDefinition)
        assert definition.process is process


def test_get_returns_the_same_definition_the_dict_holds() -> None:
    for process_id, definition in PROCESS_DEFINITIONS.items():
        assert get(process_id) is definition


def test_get_raises_key_error_for_an_unknown_process_id() -> None:
    try:
        get("not-a-process")
    except KeyError as error:
        assert "not-a-process" in str(error)
    else:
        raise AssertionError("get() did not raise for an unknown process id")


def test_process_dataclass_is_untouched_by_this_unit() -> None:
    """Nothing about ``Process`` itself grew a plain-language field — the
    identity dataclass stays exactly what ``tests/test_pmbok_catalog.py``
    already pins."""
    assert set(Process.__dataclass_fields__) == {
        "id",
        "name",
        "group",
        "area",
        "inputs",
        "tools_techniques",
        "outputs",
        "optional_outputs",
    }
