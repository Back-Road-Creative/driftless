"""Cross-layer vocabulary pins.

``driftless.models`` declares each closed vocabulary as a tuple behind a CHECK
constraint, and ``driftless.calc.rollup`` re-declares the RAG one as a ``Literal``
so a rollup can be type-checked. They agree today and nothing in the code makes
them agree tomorrow: change either side alone and the stored vocabulary quietly
stops being the one the rollup understands.

The same drift threatens ``driftless.report.gather``, which hard-codes *subsets* of
those vocabularies — the risk statuses it counts as open, and the milestone
statuses it paints with a RAG colour — and which both the report engine and the
dashboard now share. A rename in the model would silently strand each subset, so
its membership is pinned here too.

This is a test rather than the import-time assert ``driftless.api.schemas`` uses,
because an assert inside a model module would need ``driftless.models`` to import
``driftless.calc`` at runtime. Models knowing nothing about calc is worth more than
failing a few milliseconds earlier — the suite catches the drift either way,
and it catches it before the change ships.

Order is not pinned, only membership: the tuple is a CHECK vocabulary and the
``Literal`` a type, and neither reads the other positionally.
"""

from typing import get_args

import driftless.api.app  # noqa: F401 -- import first to break the driftless.web/api cycle
from driftless.assess.model import SEVERITY_WEIGHT
from driftless.calc import rollup
from driftless.models import (
    MILESTONE_STATUSES,
    RAG_STATUSES,
    RISK_STATUSES,
    SIGNOFF_DECISIONS,
    SUPPRESSING_DECISIONS,
)
from driftless.pmbok import state
from driftless.report import gather


def test_rag_vocabulary_matches_the_rollup_literal() -> None:
    # ``unknown`` is a derived-only leaf state (a project with nothing to assess);
    # it is never stored, so the CHECK vocabulary is the rollup type minus it.
    assert set(RAG_STATUSES) == set(get_args(rollup.RagStatus)) - {"unknown"}


def test_severity_weight_covers_exactly_the_rag_statuses() -> None:
    assert set(SEVERITY_WEIGHT) == set(get_args(rollup.RagStatus))


def test_severity_weight_values_derive_from_the_rollup_severity() -> None:
    # SEVERITY_WEIGHT is built from rollup.RAG_SEVERITY (see assess.model), so this
    # is an identity check by construction: it fails only if that derivation is
    # ever replaced with a second hand-written literal that could disagree.
    assert SEVERITY_WEIGHT == {
        status: float(weight) for status, weight in rollup.RAG_SEVERITY.items()
    }


def test_process_done_decisions_are_a_subset_of_the_sign_off_vocabulary() -> None:
    # _DONE_DECISIONS (state) and SUPPRESSING_DECISIONS (governance) are policy
    # subsets of SIGNOFF_DECISIONS living in other modules; pin them so a rename
    # of the master vocabulary cannot silently strand them.
    assert set(state._DONE_DECISIONS) <= set(SIGNOFF_DECISIONS)
    assert set(SUPPRESSING_DECISIONS) <= set(SIGNOFF_DECISIONS)


def test_gather_open_risks_subset_of_risk_statuses() -> None:
    assert set(gather.OPEN_RISKS) <= set(RISK_STATUSES)


def test_gather_milestone_rag_keys_subset_of_milestone_statuses() -> None:
    assert set(gather.MILESTONE_RAG) <= set(MILESTONE_STATUSES)


def test_gather_milestone_rag_values_are_valid_rag_statuses() -> None:
    assert set(gather.MILESTONE_RAG.values()) <= set(RAG_STATUSES)
