"""Refusal paths of the forecast module not exercised elsewhere.

``assess_contingency`` refuses a contingency rate outside 0..1: a rate of
150% (or a negative one) is a typo, and a made-up contingency figure is
worse than none.
"""

from datetime import date

import pytest

from driftless.calc import forecast as fc

AS_OF = date(2026, 3, 31)


@pytest.mark.parametrize("rate", [-0.1, 1.1])
def test_contingency_rate_outside_unit_interval_is_refused(rate: float) -> None:
    with pytest.raises(ValueError, match="contingency_rate"):
        fc.assess_contingency([], remaining_budget=100_000.0, as_of=AS_OF, contingency_rate=rate)
