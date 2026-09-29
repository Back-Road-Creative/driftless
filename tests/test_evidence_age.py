"""``driftless.calc.evidence_age``: the newest evidence date behind a computed figure,
and its age against the page's own as-of — a pure function over plain dates."""

from datetime import date

from driftless.calc.evidence_age import evidence_age


def test_no_evidence_dates_is_none() -> None:
    assert evidence_age(date(2026, 9, 22), []) is None


def test_all_evidence_in_the_future_is_none() -> None:
    """A date after the page's own as-of is not evidence this page could have used."""
    assert evidence_age(date(2026, 9, 22), [date(2026, 9, 23)]) is None


def test_none_entries_are_skipped() -> None:
    """An absent reading (``None``) is not evidence dated the future — it is no
    evidence at all, and must not crash the newest-date sweep."""
    result = evidence_age(date(2026, 9, 22), [None, date(2026, 9, 10)])
    assert result is not None
    assert result.as_of == date(2026, 9, 10)
    assert result.age_days == 12


def test_newest_eligible_date_wins() -> None:
    dates = [date(2026, 9, 1), date(2026, 9, 20), date(2026, 8, 15)]
    result = evidence_age(date(2026, 9, 22), dates)
    assert result is not None
    assert result.as_of == date(2026, 9, 20)
    assert result.age_days == 2


def test_evidence_dated_the_page_as_of_is_zero_days_old() -> None:
    result = evidence_age(date(2026, 9, 22), [date(2026, 9, 22)])
    assert result is not None
    assert result.age_days == 0
