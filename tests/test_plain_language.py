"""Unit tests for the shared plain-language primitives that
``tests/test_artifact_totality.py`` and ``tests/test_process_totality.py``
both call against their ``plain_summary`` field -- see
``driftless.pmbok.plain_language``'s module docstring for scope."""

from __future__ import annotations

from driftless.pmbok import plain_language as pl


def test_sentences_splits_and_drops_empty_trailing_splits() -> None:
    assert pl.sentences("One. Two! Three?") == ["One", "Two", "Three"]
    assert pl.sentences("") == []


def test_word_count_counts_whitespace_separated_words() -> None:
    assert pl.word_count("four little words") == 3


def test_acronyms_finds_runs_of_two_to_five_capitals_only() -> None:
    assert pl.acronyms("The WBS feeds the PMIS, not I nor STAKEHOLDER.") == ["WBS", "PMIS"]


def test_snake_identifiers_finds_a_raw_underscore_joined_token() -> None:
    assert pl.snake_identifiers("it sets resulting_baseline_id here") == ["resulting_baseline_id"]
    assert pl.snake_identifiers("a project has a cost rate") == []


def test_violations_passes_a_clean_one_sentence_summary() -> None:
    text = "A project is a temporary effort with a start and an end."
    assert pl.violations(text, glossary_keys=frozenset()) == []


def test_violations_flags_more_than_one_sentence() -> None:
    found = pl.violations("First sentence. Second sentence.", glossary_keys=frozenset())
    assert any("one sentence" in v for v in found)


def test_violations_flags_too_many_words() -> None:
    text = " ".join(["word"] * (pl.MAX_SUMMARY_WORDS + 1)) + "."
    assert any("words" in v for v in pl.violations(text, glossary_keys=frozenset()))


def test_violations_flags_a_raw_snake_case_identifier() -> None:
    found = pl.violations("It reads resulting_baseline_id from the row.", glossary_keys=frozenset())
    assert any("resulting_baseline_id" in v for v in found)


def test_violations_flags_an_undefined_acronym() -> None:
    found = pl.violations("The PMIS holds the record.", glossary_keys=frozenset())
    assert any("undefined acronym" in v and "PMIS" in v for v in found)


def test_violations_flags_an_acronym_that_is_a_glossary_key_too() -> None:
    found = pl.violations("The WBS breaks work down.", glossary_keys=frozenset({"wbs"}))
    assert any("WBS" in v and "glossary term" in v for v in found)
