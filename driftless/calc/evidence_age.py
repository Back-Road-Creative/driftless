"""How stale the evidence behind a computed figure is, relative to the page's own as-of.

A page's ``as_of`` says when the figures on it were computed as of; it says nothing
about when the ROWS behind those figures were last dated. A status snapshot filed
three months ago and a cost entry posted yesterday can both feed the same RAG or EVM
reading, and a reader has no way to tell "fresh" from "stale" without opening the
underlying records. :func:`evidence_age` is the one place that distance is computed —
a pure function over plain dates, so a calling page or report never derives it twice
and never disagrees with itself about what counts as evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EvidenceAge:
    """The newest evidence date behind a computed figure, and its age in days
    against the page's own ``as_of``."""

    as_of: date
    age_days: int


def evidence_age(page_as_of: date, evidence_dates: Iterable[date | None]) -> EvidenceAge | None:
    """The newest of ``evidence_dates`` on or before ``page_as_of``, and its age.

    ``None`` entries are skipped — an absent reading is not evidence dated the
    future, it is no evidence at all — and so is any date strictly AFTER
    ``page_as_of``: a page cannot cite evidence from beyond its own as-of, and
    letting such a date through would understate the age rather than exclude
    the reading that produced it. Returns ``None`` when nothing eligible
    remains, meaning "no evidence yet" — never "zero days old", which would
    read as fresh for a figure that has nothing behind it at all.
    """
    eligible = [d for d in evidence_dates if d is not None and d <= page_as_of]
    if not eligible:
        return None
    newest = max(eligible)
    return EvidenceAge(as_of=newest, age_days=(page_as_of - newest).days)
