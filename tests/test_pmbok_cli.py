"""The ``driftless pmbok`` command lists and shows catalog processes.

Exercised through the top-level ``driftless`` CLI, so the registrar wiring is covered
too: filtering by area and group, a full-catalog listing, showing one process,
and a clean error on an unknown id — on stderr, exit 2, leaving stdout empty.

The two ITTO vocabularies are printed differently, on purpose. A technique is printed
as ``definitions.TECHNIQUES``' own ``display_name`` — the same words the web library,
``driftless assess`` and the report already use, taken from the registry rather than
spelled a second time here, so the PMBOK terms of art its overrides fix ("To-Complete
Performance Index") read right in the terminal too. An artifact kind is printed as its
catalog key, because no registry owns a display name for one and the key is itself
typed vocabulary: it is what ``driftless wizard apply --kind`` accepts, so a reader
copies it straight out of this listing.

A process's ``[group / area]`` header is the third vocabulary, and it is printed raw for
the same reason as the second rather than a different one: ``--group`` and ``--area``
accept exactly those spellings, so ``monitoring_controlling`` is a handle rather than
something a reader must decode. That is a fact about the parser, not an argument, and
the walk below rechecks it by running the CLI with every one of them.

Every count this module asserts is read out of ``catalog`` rather than written down.
The sizes themselves are pinned once, in ``tests/test_pmbok_catalog.py``'s
``EXPECTED_PER_AREA`` / ``EXPECTED_PER_GROUP`` and its whole-catalog test; restating
one here would be a second copy of a measured number, checked against the first only
by someone reading both.
"""

from __future__ import annotations

import pytest

from driftless import cli
from driftless.pmbok import catalog
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.pmbok.tt import TT_CATALOG

#: The catalog keys a reader could tell from ordinary English: only the underscore
#: distinguishes an identifier from the words for it, and a single-word key
#: (``meetings``, ``training``) is spelled exactly like its own display name, so no
#: walk can call that one a leak. This one does not pretend to — it is the same limit
#: ``tests/test_web_techniques.py`` documents for the pages. Derived from
#: ``TT_CATALOG``, never written down.
_IDENTIFIER_KEYS = sorted(key for key in TT_CATALOG if "_" in key)

#: The other registry values this CLI prints raw, each paired with the flag that takes
#: it back. ``TT_CATALOG`` is not the only vocabulary on these pages, and deriving the
#: forbidden set from it alone is exactly why ``monitoring_controlling`` reached a
#: reader unremarked while every technique key was being walked. Same single-word
#: limit as above, and walked from the enum members rather than listed here.
_ENUM_IDENTIFIERS: tuple[tuple[str, str], ...] = tuple(
    (member.value, flag)
    for enum, flag in ((ProcessGroup, "--group"), (KnowledgeArea, "--area"))
    for member in enum
    if "_" in member.value
)


def _capture(capsys: pytest.CaptureFixture[str], argv: list[str]) -> str:
    """One command's stdout, run through the top-level CLI the way a reader does."""
    assert cli.main(argv) == 0, argv
    return capsys.readouterr().out


def _every_reader_facing_output(
    capsys: pytest.CaptureFixture[str],
) -> list[tuple[list[str], str]]:
    """Every listing and detail this CLI can print, each argv paired with its stdout.

    Every filter value is walked rather than three exemplars, because a value that only
    ever appears under its own filter is precisely the one a sampled walk cannot see.
    """
    argvs: list[list[str]] = [["pmbok", "processes"]]
    argvs += [["pmbok", "processes", "--area", area.value] for area in KnowledgeArea]
    argvs += [["pmbok", "processes", "--group", group.value] for group in ProcessGroup]
    argvs += [["pmbok", "show", process.id] for process in catalog.PROCESSES]
    return [(argv, _capture(capsys, argv)) for argv in argvs]


def test_processes_lists_the_whole_catalog(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "processes"]) == 0
    out = capsys.readouterr().out
    assert f"{len(catalog.PROCESSES)} process(es)." in out
    assert "4.1  Develop Project Charter" in out


def test_processes_filters_by_area(capsys: pytest.CaptureFixture[str]) -> None:
    expected = catalog.by_area(KnowledgeArea.RISK)
    assert 0 < len(expected) < len(catalog.PROCESSES), "a filter that selects all or none"
    assert cli.main(["pmbok", "processes", "--area", "risk"]) == 0
    out = capsys.readouterr().out
    assert f"{len(expected)} process(es)." in out
    assert "11.1  Plan Risk Management" in out
    assert "Develop Project Charter" not in out


def test_processes_filters_by_group(capsys: pytest.CaptureFixture[str]) -> None:
    expected = catalog.by_group(ProcessGroup.PLANNING)
    assert 0 < len(expected) < len(catalog.PROCESSES), "a filter that selects all or none"
    assert cli.main(["pmbok", "processes", "--group", "planning"]) == 0
    out = capsys.readouterr().out
    assert f"{len(expected)} process(es)." in out


def test_processes_filters_by_area_and_group(capsys: pytest.CaptureFixture[str]) -> None:
    integration = catalog.by_area(KnowledgeArea.INTEGRATION)
    expected = [p for p in integration if p.group is ProcessGroup.CLOSING]
    assert 0 < len(expected) < len(integration), "not a real narrowing"
    assert cli.main(["pmbok", "processes", "--area", "integration", "--group", "closing"]) == 0
    out = capsys.readouterr().out
    assert f"{len(expected)} process(es)." in out
    assert "4.7  Close Project or Phase" in out


def test_show_prints_one_process_with_its_ittos(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "show", "4.1"]) == 0
    out = capsys.readouterr().out
    assert "Develop Project Charter" in out
    assert "inputs:" in out and "outputs:" in out
    assert "project_charter" in out  # an artifact kind: the key IS the reader's handle
    assert "Expert Judgment" in out  # a technique: the registry's words, not its key
    assert "expert_judgment" not in out


def test_show_rejects_an_unknown_id_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "show", "99.9"]) == 2
    captured = capsys.readouterr()
    assert "error: no process with id '99.9'" in captured.err
    assert captured.out == ""


def test_an_invalid_area_choice_is_an_argparse_error() -> None:
    with pytest.raises(SystemExit):
        cli.main(["pmbok", "processes", "--area", "nonsense"])


def test_support_prints_the_coverage_summary_build_coverage_computes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No number here is typed: every figure the command prints is read straight back
    off a fresh ``build_coverage()`` call, so the assertion cannot drift from the
    summary it is checking."""
    from driftless.pmbok.support import build_coverage

    summary = build_coverage()
    assert cli.main(["pmbok", "support"]) == 0
    out = capsys.readouterr().out
    assert f"{summary.explained_technique_count}/{summary.technique_count}" in out
    assert f"{summary.assessable_process_count}/{summary.process_count}" in out
    assert f"{summary.producible_process_count}/{summary.process_count}" in out


def test_no_command_prints_a_raw_technique_identifier_anywhere_a_reader_reads(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The whole catalog, key by key, over every output this CLI has — not one exemplar.

    ``tests/test_pmbok_cli.py`` used to assert the opposite for the technique column, and
    that assertion is what kept the leak alive while every other reader-facing surface in
    the product moved to the registry's words. It is reversed above rather than deleted
    quietly, because it encoded a decision the product has since reversed everywhere else.

    Nothing parses this CLI: no doc describes its output as machine-readable and no test
    or script outside this module invokes it, so widening the technique column costs no
    consumer. Artifact kinds are out of scope here by design — see the module docstring.
    """
    for argv, text in _every_reader_facing_output(capsys):
        leaked = [key for key in _IDENTIFIER_KEYS if key in text]
        assert not leaked, f"{argv} prints raw identifiers a reader must decode: {leaked}"
    assert _IDENTIFIER_KEYS, "vacuous walk: no catalog key is an identifier at all"


def test_every_raw_group_or_area_value_a_reader_sees_is_one_the_cli_takes_back(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The third vocabulary, which no walk in this repo covered until now.

    ``_format`` prints ``process.group.value`` and ``process.area.value`` verbatim, so
    ``monitoring_controlling`` reaches the terminal. Both identifier-leak guards in the
    suite derived their forbidden set from ``TT_CATALOG`` alone, so neither could ever
    have seen it, and the standing claim that no raw snake_case identifier reaches a
    reader was checked over one vocabulary out of three.

    What makes these raw values defensible is the same thing that makes an artifact kind
    defensible: the reader can type one straight back. That justification is a property
    of the parser, so it is rechecked here by running the CLI with each value rather than
    argued in a comment that nothing revisits. Drop ``--group``, respell a choice, or add
    an enum member no flag accepts, and this fails — instead of a handle quietly becoming
    a leak the way ``monitoring_controlling`` almost did.
    """
    assert _ENUM_IDENTIFIERS, "vacuous walk: no group or area value is an identifier at all"
    outputs = _every_reader_facing_output(capsys)
    unaccepted: list[tuple[str, str, list[str]]] = []
    for value, flag in _ENUM_IDENTIFIERS:
        printed_by = [argv for argv, text in outputs if value in text]
        if not printed_by:
            continue
        try:
            accepted = cli.main(["pmbok", "processes", flag, value]) == 0
        except SystemExit:
            accepted = False
        capsys.readouterr()
        if not accepted:
            unaccepted.append((value, flag, printed_by[0]))
    assert not unaccepted, (
        "printed to a reader but not accepted back through its own flag — a raw "
        f"identifier with nothing to type it into: {unaccepted}"
    )


def test_every_technique_a_process_names_is_printed_as_the_registrys_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The other half: absence of the key is not presence of the name.

    Walked over ``catalog.PROCESSES`` and read out of ``TECHNIQUES``, so a technique added
    to a family in ``tt.py`` is required here without anyone editing this file.
    """
    seen = 0
    for process in catalog.PROCESSES:
        listing = _capture(capsys, ["pmbok", "show", process.id])
        for key in process.tools_techniques:
            assert TECHNIQUES[key].display_name in listing, f"{process.id}: {key}"
            seen += 1
    assert seen > 0, "vacuous walk: no process names a technique"
