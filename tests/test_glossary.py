"""``driftless.pmbok.glossary.GLOSSARY`` -- the frozen registry, checked as a
whole rather than by a hand-picked entry: every key is a real address, every
``plain`` is one short sentence that stands on its own, and no entry is an
orphan -- a term no shipped surface actually uses would be a glossary page
explaining a word nobody reads.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import dataclasses

import pytest
from fastapi.testclient import TestClient

import test_web_pages
from driftless.naming import humanize
from driftless.pmbok import catalog
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY, GlossaryEntry

client = test_web_pages.client

_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless" / "web" / "templates"
_TECH_FIELDS = ("summary", "when_to_use", "when_to_avoid", "worked_example")
_TECH_TUPLES = ("steps", "outputs", "pitfalls", "further_reading")


def _shipped_corpus() -> str:
    """Every string a reader can actually meet: technique definitions, process
    names, artifact display names, and every template's own source -- the four
    sources the module docstring names, walked rather than sampled."""
    parts: list[str] = []
    for definition in TECHNIQUES.values():
        for field in _TECH_FIELDS:
            parts.append(getattr(definition, field) or "")
        for field in _TECH_TUPLES:
            parts.extend(getattr(definition, field))
        parts.append(definition.display_name)
    for process in catalog.PROCESSES:
        parts.append(process.name)
    for kind in ARTIFACT_KINDS:
        parts.append(humanize(kind))
    for path in glob.glob(str(_TEMPLATES / "*.html")):
        parts.append(Path(path).read_text())
    return "\n".join(parts).lower()


def test_glossary_is_non_empty() -> None:
    assert GLOSSARY, "vacuous: no glossary entries at all"


def test_every_key_is_its_own_lowercase_hyphenated_address() -> None:
    for key in GLOSSARY:
        assert key == key.lower(), key
        assert " " not in key, key


def test_every_entrys_plain_definition_is_one_short_sentence() -> None:
    """<=25 words, and never leans on ANOTHER glossary term to say what this one
    means -- walked over the whole registry, not one exemplar."""
    checked = 0
    for key, entry in GLOSSARY.items():
        words = entry.plain.split()
        assert len(words) <= 25, f"{key}: plain runs {len(words)} words: {entry.plain!r}"
        for other_key, other in GLOSSARY.items():
            if other_key == key:
                continue
            pattern = r"\b" + re.escape(other.term.lower()) + r"\b"
            assert not re.search(pattern, entry.plain.lower()), (
                f"{key}'s plain definition leans on {other_key!r}: {entry.plain!r}"
            )
            checked += 1
    assert checked > 0, "vacuous: no cross-term pair was ever checked"


def test_every_see_also_names_a_real_entry_and_never_itself() -> None:
    checked = 0
    for key, entry in GLOSSARY.items():
        for other in entry.see_also:
            assert other in GLOSSARY, f"{key} sees {other!r}, which GLOSSARY does not define"
            assert other != key, f"{key} lists itself in its own see_also"
            checked += 1
    assert checked > 0, "vacuous: no entry carries a see_also at all"


def test_no_glossary_entry_is_an_orphan() -> None:
    """Every entry's ``term`` must appear, whole-word and case-insensitive, in a
    shipped technique definition, a process name, an artifact display name, or a
    template -- walked over all four sources and every entry, never spot-checked."""
    corpus = _shipped_corpus()
    orphans = []
    for key, entry in GLOSSARY.items():
        pattern = r"\b" + re.escape(entry.term.lower()) + r"\b"
        if not re.search(pattern, corpus):
            orphans.append(key)
    assert not orphans, f"glossary entries no shipped surface uses: {orphans}"


def test_an_acronym_entrys_plain_is_the_expansion_not_the_letters_again() -> None:
    """A term written in all capitals (``EVM``, ``WBS``, ``PERT``, ``SLA``, ``RAG``)
    is an abbreviation, and its ``plain`` must say what the letters stand for
    rather than just restating them."""
    checked = 0
    for key, entry in GLOSSARY.items():
        if entry.term.isupper():
            assert entry.plain.strip() != entry.term, f"{key}: plain is just the acronym again"
            assert len(entry.plain.split()) > len(entry.term.split()), key
            checked += 1
    assert checked > 0, "vacuous: no acronym entry in the registry to check"


def test_glossary_entry_is_frozen() -> None:
    entry = next(iter(GLOSSARY.values()))
    assert isinstance(entry, GlossaryEntry)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.plain = "rewritten"  # type: ignore[misc]


def test_every_defined_on_path_is_a_real_page(client: TestClient) -> None:
    """``defined_on`` holds route paths, never free text -- every one of them
    must resolve to a real, parameterless page (200), so a renamed route fails
    here rather than silently 404ing a reader who clicks "Where you meet it"."""
    checked = 0
    for key, entry in GLOSSARY.items():
        for path in entry.defined_on:
            response = client.get(path)
            assert response.status_code == 200, f"{key}: {path} -> {response.status_code}"
            checked += 1
    assert checked > 0, "vacuous: no entry names a defined_on path at all"


def test_crosswalk_is_defined_and_its_see_also_names_real_entries() -> None:
    """``/methods`` uses "crosswalk" and "fully crosswalked" without ever saying
    what a crosswalk is; this entry is that definition."""
    assert "crosswalk" in GLOSSARY, "no glossary entry for the word /methods leans on"
    entry = GLOSSARY["crosswalk"]
    for other in entry.see_also:
        assert other in GLOSSARY, f"crosswalk sees {other!r}, which GLOSSARY does not define"
