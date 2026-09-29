"""``driftless.pmbok.methods.METHODS``: plain language and crosswalk integrity,
walked over every practice of every profile rather than sampled."""

from __future__ import annotations

import re

from driftless.pmbok import catalog
from driftless.pmbok.methods import METHODS, MethodProfile, Practice, PracticeKind
from driftless.pmbok.tt import TT_CATALOG

_MAX_WORDS = 25
_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")
_PROCESS_IDS: frozenset[str] = frozenset(p.id for p in catalog.PROCESSES)


def _all_practices() -> list[tuple[str, Practice]]:
    return [
        (f"{method.key}.{practice.key}", practice)
        for method in METHODS.values()
        for practice in method.practices
    ]


def test_the_registry_is_not_empty() -> None:
    assert set(METHODS) == {"scrum", "kanban"}
    for method in METHODS.values():
        assert method.practices


def _check_plain_summary(label: str, text: str, errors: list[str]) -> None:
    if not text.strip():
        errors.append(f"{label}: plain_summary is blank")
        return
    if text.count(".") > 1 or not text.rstrip().endswith("."):
        errors.append(f"{label}: not exactly one sentence: {text!r}")
    if len(text.split()) > _MAX_WORDS:
        errors.append(f"{label}: over {_MAX_WORDS} words: {text!r}")
    if "_" in text:
        errors.append(f"{label}: leaks a snake_case identifier: {text!r}")
    if _ACRONYM.search(text):
        errors.append(f"{label}: carries an acronym: {text!r}")


def test_every_plain_summary_is_one_plain_sentence_of_at_most_25_words() -> None:
    errors: list[str] = []
    for method in METHODS.values():
        _check_plain_summary(method.key, method.plain_summary, errors)
        for practice in method.practices:
            _check_plain_summary(f"{method.key}.{practice.key}", practice.plain_summary, errors)
    assert not errors, "\n".join(errors)


def test_every_crosswalk_entry_names_a_real_process_or_technique() -> None:
    bad, checked = [], 0
    for label, practice in _all_practices():
        for entry in practice.crosswalk:
            checked += 1
            if entry not in _PROCESS_IDS and entry not in TT_CATALOG:
                bad.append(f"{label}: {entry!r} names neither a process nor a technique")
    assert not bad, "\n".join(bad)
    assert checked > 0, "vacuous walk: no practice carries a crosswalk entry at all"


def test_an_empty_crosswalk_always_carries_a_reason_and_a_full_one_never_does() -> None:
    empty_without_reason, full_with_reason, saw_empty = [], [], False
    for label, practice in _all_practices():
        if practice.crosswalk:
            if practice.crosswalk_reason:
                full_with_reason.append(label)
        else:
            saw_empty = True
            if not practice.crosswalk_reason.strip():
                empty_without_reason.append(label)
    assert not empty_without_reason, f"{empty_without_reason} carry no crosswalk and no reason"
    assert not full_with_reason, f"{full_with_reason} carry both a crosswalk and a reason"
    assert saw_empty, "vacuous: no practice in the registry has an empty crosswalk"


def test_every_practice_kind_is_a_real_enum_member() -> None:
    for label, practice in _all_practices():
        assert isinstance(practice.kind, PracticeKind), label


def test_every_method_names_its_source_and_a_pinned_edition() -> None:
    for method in METHODS.values():
        assert isinstance(method, MethodProfile)
        assert method.source.strip()
        assert method.source_version.strip()
