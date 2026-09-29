"""Shared plain-language primitives for the reader-facing summary field of a
PMBOK registry: ``ARTIFACTS``' and ``PROCESS_DEFINITIONS``' ``plain_summary``
and ``TECHNIQUES``' ``summary``. That field is the ONE sentence a newcomer
meets before anything else on the page: exactly one sentence, at most
``MAX_SUMMARY_WORDS`` words, no raw snake_case identifier, no bare acronym.
``tests/test_artifact_totality.py``, ``tests/test_process_totality.py`` and
``tests/test_technique_totality.py`` used to each restate parts of this as a
private regex; they now call the functions here, so the rule has one definition.

``TECHNIQUES``' deeper fields (``steps``, ``pitfalls``, ``worked_example``, ...)
are deliberately NOT walked by ``violations`` -- they are deep-dive prose,
dense in places with the technique's own formula notation, that re-expanding on
every sentence would make unreadable; every acronym there is a glossary key
instead. ``tests/test_technique_totality.py`` still uses ``snake_identifiers``
on every technique field: a raw identifier leaking into prose is a bug regardless."""

from __future__ import annotations

import re

#: The maximum a plain-language summary sentence may run to.
MAX_SUMMARY_WORDS = 25

#: Sentence-ending punctuation.
_SENTENCE_END = re.compile(r"[.!?]")

#: An all-caps run of 2-5 letters -- an acronym, not a sentence-initial "I".
_ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")

#: A raw snake_case identifier leaking into prose meant to read as words.
_SNAKE_CASE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def sentences(text: str) -> list[str]:
    """``text``'s sentences, split on terminal punctuation, stripped, empty
    splits dropped."""
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def word_count(text: str) -> int:
    """The word count ``MAX_SUMMARY_WORDS`` is measured against."""
    return len(text.split())


def acronyms(text: str) -> list[str]:
    """Every all-caps 2-5 letter token in ``text``, in order."""
    return _ACRONYM.findall(text)


def snake_identifiers(text: str) -> list[str]:
    """Every raw snake_case identifier in ``text``."""
    return _SNAKE_CASE.findall(text)


def violations(text: str, *, glossary_keys: frozenset[str]) -> list[str]:
    """Every plain-language rule ``text`` breaks, as human-readable strings
    naming the offending token or count -- empty if ``text`` passes: exactly
    one sentence, at most ``MAX_SUMMARY_WORDS`` words, no raw snake_case
    identifier, no acronym at all -- a summary sends a reader nowhere else to
    look a term up, so even a glossary-defined acronym is barred here;
    ``glossary_keys`` only sharpens which message a barred acronym gets."""
    found: list[str] = []

    sentence_count = len(sentences(text))
    if sentence_count != 1:
        found.append(f"must be exactly one sentence, found {sentence_count}")

    words = word_count(text)
    if words > MAX_SUMMARY_WORDS:
        found.append(f"runs {words} words (max {MAX_SUMMARY_WORDS})")

    found.extend(f"contains a raw identifier {token!r}" for token in snake_identifiers(text))

    for token in acronyms(text):
        if token.lower() in glossary_keys:
            found.append(f"contains {token!r}, a glossary term -- spell it out instead")
        else:
            found.append(f"contains undefined acronym {token!r}")

    return found
